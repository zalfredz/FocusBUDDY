"""Validasi nama obat lewat registri BPOM -- OFFLINE, dari data resmi.

INI GANTIIN SELURUH LAPISAN AI DI FITUR OBAT
--------------------------------------------
Sebelumnya urusan obat nebeng ke Gemini dua kali: nebak ejaan nama, dan
njelasin obatnya buat apa. Dua-duanya sekarang DIBUANG, diganti registri
Master Produk Komoditi Obat BPOM: 23.437 baris, ~8.960 nama obat unik, plus
nomor izin edar (NIE), golongan, komposisi, dan masa berlakunya.

Alasannya bukan cuma teknis. Urusan obat itu tempat paling nggak pantes buat
jawaban yang "kedengeran meyakinkan tapi bisa keliru": model bisa ngarang obat
yang nggak beredar di Indonesia, dan nggak ada yang bisa dipertanggungjawabkan
kalau salah. Registri resmi nggak punya masalah itu -- dan bonusnya jalan
offline, instan, dan nggak makan kuota API sama sekali.

APA YANG BISA DIBILANG DARI NIE
-------------------------------
Huruf ke-2 nomor izin edar nentuin golongan obat. Jadi app bisa bilang
"Concerta itu psikotropika, wajib resep dokter" sebagai FAKTA dari registri,
bukan tebakan model.

BATAS YANG TETAP DIPEGANG
-------------------------
Ketemu di registri artinya obatnya TERDAFTAR -- bukan artinya cocok buat user,
bukan pembenaran dosis, dan bukan anjuran. Nama yang NGGAK ketemu tetap boleh
disimpan: racikan apotek dan obat baru yang belum masuk unduhan ini nyata ada,
dan nolak nyimpen bakal ngunci pengingat dari orang yang justru paling butuh.

APA YANG *NGGAK* ADA DI DATASET INI
-----------------------------------
Master Produk Komoditi OBAT cuma nyakup obat. JAMU, HERBAL, dan SUPLEMEN
didaftarin BPOM di daftar terpisah (nomor TR/SD/POM). Jadi "Tolak Angin" dan
"Imboost" bakal balik "nggak ketemu" -- itu BENAR, bukan bug. UI-nya
ngejelasin ini biar user nggak ngira dia salah ketik.

BATAS PENCOCOKAN LONGGAR
------------------------
Tebakan salah ketik bisa nunjuk obat yang salah kalau namanya kebetulan mirip
-- mis. "Antangin" (jamu) nyaris nyocok ke "ANTRAIN" (metamizol, obat keras).
Makanya hasilnya SELALU disajikan sebagai pertanyaan ("Maksudnya X?") yang
gampang diabaikan, nggak pernah otomatis nimpa ketikan user.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app import clock

INDEX_PATH = Path(__file__).resolve().parent.parent / "data" / "bpom_index.json"

# Ambang kemiripan buat nyaranin ejaan -- diukur, bukan ditebak.
#
#   "CONSENTA" vs "CONCERTA"  = 0.750   <- salah ketik yang harus kena
#   "ALPRAZOLAN" vs "...LAM"  = 0.900
#
# Di 0.72 semua salah ketik uji kena, dan 8 masukan sampah ("asdfghjkl",
# "tugas kuliah", dst) tetap nggak nyocok ke apa pun. Turun sampai 0.65 pun
# sampahnya masih nol, tapi 0.72 disisain sebagai margin aman.
FUZZY_CUTOFF = 0.72

# Ambang terpisah & lebih ketat buat nebak salah ketik NAMA ZAT AKTIF.
# Nama zat banyak yang mirip antar kelas obat yang beda jauh ("RITALIN" vs
# "SERTRALIN" = 0.73), dan salah nebak golongan obat lebih bahaya daripada
# jujur bilang "nggak ketemu".
INGREDIENT_CUTOFF = 0.88

# Golongan yang wajib resep dokter -- dipakai buat nada pesannya.
RESEP_WAJIB = {"Keras", "Psikotropika", "Narkotika"}


@dataclass
class DrugMatch:
    found: bool
    exact: bool = False              # True = persis, False = hasil pencocokan longgar
    # Ketemunya LEWAT APA -- ini nentuin app harus ngomong apa:
    #   "nama"  -> nama dagang cocok. Aman bilang "obat ini terdaftar".
    #   "zat"   -> yang diketik itu ZAT AKTIF, bukan merek. Jangan bilang
    #              "maksudnya PARAMOL?" -- user ngetik "parasetamol", dan
    #              PARAMOL cuma salah satu dari puluhan produk yang ngandung.
    #   "mirip" -> tebakan salah ketik.
    matched_by: str = "nama"
    name: str = ""                   # nama resmi di registri
    nie: str = ""
    golongan: str = ""               # Bebas | Bebas Terbatas | Keras | Psikotropika | Narkotika
    bentuk: str = ""
    komposisi: str = ""
    berlaku_sampai: str = ""
    pendaftar: str = ""
    suggestions: list[str] = field(default_factory=list)   # kalau nggak ketemu persis

    @property
    def butuh_resep(self) -> bool:
        return self.golongan in RESEP_WAJIB

    @property
    def registrasi_kedaluwarsa(self) -> bool:
        """True kalau masa berlaku NIE-nya udah lewat.

        BUKAN berarti obatnya kedaluwarsa -- ini soal izin edarnya yang belum
        diperpanjang. Sering kejadian buat obat yang masih beredar normal,
        jadi ditulis sebagai catatan kecil, bukan peringatan.
        """
        if not self.berlaku_sampai:
            return False
        try:
            return date.fromisoformat(self.berlaku_sampai) < clock.today()
        except ValueError:
            return False


def normalise(name: str) -> str:
    text = (name or "").upper().strip()
    text = text.replace("®", "").replace("™", "")
    text = re.sub(r"[^A-Z0-9\s]", " ", text)
    # Angka yang nempel ke huruf dipisah: "CONCERTA18MG" -> "CONCERTA 18MG".
    # Orang sering ngetik tanpa spasi, dan tanpa ini kekuatannya nggak
    # kepotong sehingga nama obatnya nggak pernah ketemu.
    text = re.sub(r"(?<=[A-Z])(?=\d)", " ", text)
    text = re.sub(r"(?<=\d)(?=[A-Z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_strength(name: str) -> str:
    """Buang angka kekuatan sediaan: 'CONCERTA 18 MG' -> 'CONCERTA'."""
    text = normalise(name)
    text = re.sub(r"\b\d+([.,]\d+)?\s?(MG|ML|MCG|G|IU|%)\b", " ", text)
    text = re.sub(r"\b(MG|ML|MCG|IU)\b", " ", text)
    text = re.sub(r"\b\d+([.,]\d+)?\b\s*$", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Ejaan INN internasional -> ejaan Indonesia. Ini transformasi yang KONSISTEN,
# bukan daftar hafalan: farmakope Indonesia memang menyerap nama zat dengan
# aturan tetap.
#
#   METHYLPHENIDATE -> METILFENIDAT      PARACETAMOL   -> PARASETAMOL
#   FLUOXETINE      -> FLUOKSETIN        AMOXICILLIN   -> AMOKSISILIN
#
# Query DAN kunci indeks sama-sama dilewatin fungsi ini, jadi user boleh
# ngetik pakai ejaan mana pun. Tanpa ini, "metilfenidat" malah nyasar ke
# "FENIDA" gara-gara kecocokan substring yang skornya kebetulan lebih tinggi.
_ID_RULES = [
    (r"PH", "F"),
    (r"TH", "T"),
    (r"CH", "K"),
    (r"OE", "E"),
    (r"AE", "E"),
    (r"C(?=[AOU])", "K"),
    (r"C(?=[EI])", "S"),
    (r"X", "KS"),
    (r"Y", "I"),
    (r"E\b", ""),
]


def indonesianise(text: str) -> str:
    """Samain ejaan internasional & Indonesia ke satu bentuk."""
    out = normalise(text)
    for pattern, repl in _ID_RULES:
        out = re.sub(pattern, repl, out)
    return re.sub(r"\s+", " ", out).strip()


# Alias privat supaya kode di bawah tetap kebaca.
_normalise = normalise
_strip_strength = strip_strength


@lru_cache(maxsize=1)
def _index() -> dict:
    """Muat indeks sekali, terus disimpen di memori.

    Return dict kosong kalau file-nya nggak ada -- app tetap jalan penuh,
    validasinya aja yang nggak aktif. Bikin ulang: python tools/build_bpom_index.py
    """
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def available() -> bool:
    return bool(_index().get("obat"))


def index_info() -> dict:
    idx = _index()
    return {
        "sumber": idx.get("sumber", ""),
        "baris_asli": idx.get("baris_asli", 0),
        "jumlah_obat": len(idx.get("obat", {})),
    }


def _build(key: str, entry: dict, exact: bool, matched_by: str = "nama") -> DrugMatch:
    return DrugMatch(
        found=True,
        exact=exact,
        matched_by=matched_by,
        name=entry.get("n", key),
        nie=entry.get("nie", ""),
        golongan=entry.get("g", ""),
        bentuk=entry.get("b", ""),
        komposisi=entry.get("k", ""),
        berlaku_sampai=entry.get("s", ""),
        pendaftar=entry.get("p", ""),
    )


def lookup(typed: str) -> DrugMatch:
    """Cari nama obat di registri. Empat lapis, dari yang paling ketat.

    1. Cocok persis.
    2. Cocok setelah angka kekuatan dibuang ("Concerta 18mg" -> "CONCERTA").
    3. Cocok ke nama zat aktif ("metilfenidat" -> merek yang ngandung itu).
    4. Pencocokan longgar buat salah ketik ("Consenta" -> "CONCERTA").
    """
    idx = _index()
    obat = idx.get("obat")
    if not obat:
        return DrugMatch(found=False)

    key = _normalise(typed)
    if not key:
        return DrugMatch(found=False)

    # 1. persis
    if key in obat:
        return _build(key, obat[key], exact=True)

    # 2. tanpa angka kekuatan
    bare = _strip_strength(key)
    if bare and bare in obat:
        return _build(bare, obat[bare], exact=True)
    alias = idx.get("tanpa_kekuatan", {}).get(bare)
    if alias and alias in obat:
        return _build(alias, obat[alias], exact=True)

    zat = idx.get("zat_aktif", {})
    target = bare or key
    target_id = indonesianise(target)

    def by_ingredient(merek: list[str]) -> DrugMatch:
        first = merek[0]
        match = _build(first, obat[first], exact=False, matched_by="zat")
        match.suggestions = [obat[m]["n"] for m in merek[:6] if m in obat]
        return match

    # 3. nama zat aktif, PERSIS. Dicek lewat ejaan yang udah diseragamkan,
    #    jadi "metilfenidat" dan "methylphenidate" sama-sama nyampe.
    merek = zat.get(target_id) or zat.get(target)
    if merek:
        return by_ingredient(merek)

    # 4. salah ketik NAMA DAGANG -- didahulukan dari tebakan zat aktif.
    #    Urutannya penting: user yang salah ngetik nama obatnya hampir selalu
    #    lagi ngetik MEREK, bukan zat. Waktu langkah ini ditaruh belakangan,
    #    "Consenta" (salah ketik Concerta) malah nyasar ke obat pencahar
    #    gara-gara kebetulan mirip sama satu nama zat.
    close = difflib.get_close_matches(target, list(obat.keys()), n=5, cutoff=FUZZY_CUTOFF)
    if close:
        match = _build(close[0], obat[close[0]], exact=False, matched_by="mirip")
        match.suggestions = [obat[c]["n"] for c in close]
        return match

    # 5. terakhir: salah ketik nama ZAT, ambangnya lebih ketat.
    #    Nama zat aktif banyak yang mirip-mirip satu sama lain, jadi tebakan
    #    longgar di sini gampang banget nunjuk obat yang salah kelas -- dan
    #    salah nebak golongan obat jauh lebih bahaya daripada bilang
    #    "nggak ketemu".
    dekat = difflib.get_close_matches(target_id, list(zat.keys()), n=1, cutoff=INGREDIENT_CUTOFF)
    if dekat:
        return by_ingredient(zat[dekat[0]])

    return DrugMatch(found=False)


def summary(match: DrugMatch) -> str:
    """Satu kalimat ringkas buat ditampilin di bawah kolom nama obat."""
    if not match.found:
        return ""
    bits = [match.golongan] if match.golongan else []
    if match.bentuk:
        bits.append(match.bentuk.split(";")[0].strip().title())
    if match.komposisi:
        bits.append(match.komposisi.title())
    head = " · ".join(b for b in bits if b)
    return f"{head} · NIE {match.nie}" if head else f"NIE {match.nie}"


def suggestion_for(typed: str, match: DrugMatch) -> Optional[str]:
    """Nama resmi yang disaranin -- HANYA buat dugaan salah ketik.

    Sengaja balik None kalau ketemunya lewat zat aktif. User yang ngetik
    "parasetamol" nggak lagi salah ketik; nyaranin "maksudnya PARAMOL?"
    itu jawaban yang salah buat pertanyaan yang nggak dia ajukan.
    """
    if not match.found or match.exact or match.matched_by != "mirip":
        return None
    if not match.name:
        return None
    if _normalise(match.name) == _strip_strength(typed):
        return None
    return match.name


def ingredient_note(match: DrugMatch) -> str:
    """Kalimat buat kasus "yang diketik itu zat aktif, bukan merek"."""
    if not match.found or match.matched_by != "zat":
        return ""
    n = len(match.suggestions)
    contoh = ", ".join(match.suggestions[:3])
    if n > 3:
        return f"Itu nama zat aktifnya. Di Indonesia ada beberapa mereknya — mis. {contoh}."
    return f"Itu nama zat aktifnya. Merek yang ngandung: {contoh}."
