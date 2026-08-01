"""Bikin indeks obat ringkas dari CSV registri BPOM.

SUMBER
------
`APP - Master Produk Komoditi Obat-<tanggal>.csv` -- unduhan Master Produk
Komoditi Obat dari BPOM. 23.437 baris, 4,8 MB.

KENAPA DI-INDEKS, BUKAN DIBACA LANGSUNG
---------------------------------------
CSV mentahnya kegedean buat dibuka tiap kali user ngetik nama obat, dan 60%
kolomnya nggak kepakai app ini (tanggal terbit, kemasan, nama aplikasi,
diterbitkan oleh). Indeks ini cuma nyimpen yang beneran dipakai buat validasi,
dan nge-dedup 23.437 baris jadi ~9.000 nama unik.

CARA JALANIN (cuma perlu diulang kalau CSV-nya di-update):

    python tools/build_bpom_index.py

ARTI KODE NIE (Nomor Izin Edar)
-------------------------------
Huruf ke-2 nentuin golongan obat -- ini yang bikin app bisa bilang "ini obat
keras, harus pakai resep" tanpa nebak:

    B = Bebas             T = Bebas Terbatas    K = Keras
    P = Psikotropika      N = Narkotika

Huruf ke-3: L = Lokal, I = Impor, E = Ekspor.
"""
from __future__ import annotations

import csv
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "app" / "data" / "bpom_index.json"

# Aturan normalisasi diimpor dari modul runtime-nya, BUKAN disalin ke sini.
# Kalau dua-duanya punya salinan sendiri, indeks dan pencarian bisa diam-diam
# pakai aturan beda dan hasilnya nggak pernah nyocok.
from app.core.bpom import indonesianise, normalise, strip_strength  # noqa: E402

GOLONGAN = {
    "B": "Bebas",
    "T": "Bebas Terbatas",
    "K": "Keras",
    "P": "Psikotropika",
    "N": "Narkotika",
}

# Kata garam/pengisi yang muncul di hampir semua komposisi. Kalau ikut
# diindeks, ngetik "hidroklorid" bakal balikin ratusan obat acak -- dan
# tebakan ejaan jadi nyasar ke situ.
SALT_WORDS = {
    "HIDROKLORID", "HIDROBROMID", "HIDROKSID", "KLORID", "BROMID", "MALEAT",
    "SULFAT", "FOSFAT", "NITRAT", "MONONITRAT", "SITRAT", "TARTRAT", "ASETAT",
    "LACTAT", "LAKTAT", "SUKSINAT", "FUMARAT", "BESILAT", "MESILAT",
    "SODIUM", "POTASSIUM", "KALSIUM", "MAGNESIUM", "AMMONIUM", "ALUMINIUM",
    "ANHIDROUS", "MONOHIDRAT", "DIHIDRAT", "HEMIHIDRAT", "TRIHIDRAT",
    "KOMBINASI", "MICRONIZED", "EKSTRACT", "EKSTRAK", "EMULSION", "DRIED",
    "ASID", "ACID", "BASE", "GARAM", "SERBUK", "LIKE", "VIRUS",
}


def main() -> None:
    # DATASET/ itu tempat resmi semua data mentah. Root ikut dicek buat
    # kompatibilitas file yang dulu ditaruh di situ.
    matches = sorted(
        glob.glob(str(ROOT / "DATASET" / "*Master Produk Komoditi Obat*.csv"))
        + glob.glob(str(ROOT / "*Master Produk Komoditi Obat*.csv"))
    )
    if not matches:
        raise SystemExit(
            "CSV BPOM nggak ketemu.\n"
            "Taruh file 'APP - Master Produk Komoditi Obat-<tanggal>.csv' di folder DATASET/."
        )
    src = Path(matches[-1])
    print(f"sumber : {src.name}")

    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    print(f"baris  : {len(rows):,}")

    # Dedup per nama: simpen yang MASA BERLAKU-nya paling jauh. Satu nama obat
    # sering punya banyak NIE (beda kekuatan/kemasan) -- yang paling relevan
    # buat user itu yang registrasinya paling lama masih hidup.
    best: dict[str, dict] = {}
    for row in rows:
        key = normalise(row["NAMA PRODUK"])
        if not key:
            continue
        nie = (row.get("NIE") or "").strip().upper()
        entry = {
            "n": row["NAMA PRODUK"].strip(),
            "nie": nie,
            "g": GOLONGAN.get(nie[1] if len(nie) > 1 else "", ""),
            "b": (row.get("BENTUK SEDIAAN") or "").strip(),
            "k": (row.get("KOMPOSISI") or "").strip(),
            "s": (row.get("MASA BERLAKU") or "").strip(),
            "p": (row.get("PENDAFTAR") or "").strip().replace(" - Indonesia", ""),
        }
        prev = best.get(key)
        if prev is None or entry["s"] > prev["s"]:
            best[key] = entry

    # Peta zat aktif -> nama dagang, biar user yang ngetik nama generik
    # ("metilfenidat") tetap ketemu.
    #
    # Dikunci pakai ejaan yang UDAH DISERAGAMKAN, jadi "methylphenidate" dan
    # "metilfenidat" jatuh ke kunci yang sama.
    #
    # DUA HAL YANG GAMPANG KELEWAT DI DATA INI:
    # 1. Pemisah komposisinya `<br>` (sisa HTML) dan TITIK -- bukan koma.
    #    Tanpa dipecah bener, "AMMONIUM CHLORIDE<br>DIPHENHYDRAMINE ..." jadi
    #    satu kunci raksasa yang nggak akan pernah kecocokan sama apa pun.
    # 2. Nama zat hampir selalu bawa embel-embel garam ("METILFENIDAT
    #    HIDROKLORID"). User ngetik zat aktifnya doang, jadi tiap KATA
    #    penting ikut diindeks -- bukan cuma frasa utuhnya.
    by_ingredient: dict[str, list[str]] = {}

    def add(token: str, key: str) -> None:
        if len(token) < 5 or token in SALT_WORDS:
            return
        bucket = by_ingredient.setdefault(token, [])
        if key not in bucket and len(bucket) < 12:
            bucket.append(key)

    for key, entry in best.items():
        for part in re.split(r"<br>|[.;,/+]", entry["k"]):
            phrase = indonesianise(part)
            if not phrase:
                continue
            add(phrase, key)                      # frasa utuh
            for word in phrase.split():           # tiap kata penting
                add(word, key)

    # Nama tanpa angka kekuatan -> nama penuh. Ini yang bikin "Concerta 18mg"
    # nyambung ke "CONCERTA".
    stripped: dict[str, str] = {}
    for key in best:
        bare = strip_strength(key)
        if bare and bare != key and bare not in best:
            stripped.setdefault(bare, key)

    payload = {
        "sumber": src.name,
        "baris_asli": len(rows),
        "obat": best,
        "zat_aktif": by_ingredient,
        "tanpa_kekuatan": stripped,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"nama unik      : {len(best):,}")
    print(f"zat aktif      : {len(by_ingredient):,}")
    print(f"alias tanpa mg : {len(stripped):,}")
    print(f"keluar         : {OUT.relative_to(ROOT)}  ({OUT.stat().st_size/1024/1024:.2f} MB)")


if __name__ == "__main__":
    main()
