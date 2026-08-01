"""MODEL DURASI TUGAS -- "ini kira-kira makan waktu berapa lama?"

MASALAH YANG DIJAWAB
--------------------
*Time blindness* itu gejala inti ADHD, bukan efek samping. Perkiraan waktu
meleset lebih sering dan lebih jauh, dan akibatnya dua-duanya buruk: tugas 20
menit ditunda berhari-hari karena kerasa "gede", atau lima tugas dijejelin ke
sore yang cuma muat dua.

SUMBER DATA
-----------
`DATASET/task_duration_dataset_id_lengkap.csv` -- 549 tugas berbahasa
Indonesia + durasi aslinya. Kolomnya: `tugas` (judul bebas),
`jatuh_tempo_hari`, `tingkat_kepentingan_1_10`, `durasi_jam`.

Datanya judul BEBAS, bukan kategori+jumlah. Itu justru cocok sama cara orang
beneran nulis tugas -- makanya modelnya baca TEKSNYA, bukan minta user milih
kategori dulu.

KENAPA NGELUARIN RENTANG, BUKAN SATU ANGKA
------------------------------------------
Ini keputusan paling penting di modul ini, dan dasarnya pengukuran (5-fold CV):

    baseline (selalu tebak median 30 mnt)   MAE_log 0.952
    TFIDF kata  + RandomForest              MAE_log 0.777
    TFIDF huruf + RF, semua fitur           MAE_log 0.738   36.7 s
    TFIDF huruf + RF, max_features=300      MAE_log 0.755    5.6 s   <- dipakai

MAE_log 0.755 artinya tebakan khasnya meleset sekitar FAKTOR 2x. Nampilin
"45 menit" dari model segitu itu bohong yang keliatan presisi -- dan buat
orang ADHD, angka pasti yang meleset bikin rasa gagal yang nggak perlu.

`max_features=300` dipilih sadar: akurasinya nyaris sama sama versi penuh
(0.755 vs 0.738) tapi 6x lebih cepat dilatih. Buat selisih sekecil itu,
kecepatan lebih berharga.

PITA-NYA DARI SEBARAN ANTAR-POHON
---------------------------------
Tiap pohon di hutan ngasih tebakan sendiri. Persentil 25-75 dari 300 tebakan
itu = seberapa nggak yakin modelnya. Diuji kalibrasinya:

    pita 25-75%  -> 50% data asli jatuh di dalamnya (target 50%)  ✓ pas

Modelnya jujur soal ketidaktahuannya sendiri. "Biasanya 20-50 menit" itu
janji yang bisa ditepati; "45 menit" nggak.

GABUNGAN SAMA KECEPATAN ASLI USER
---------------------------------
    durasi = 0.6 x model_umum + 0.4 x rata2_personal_kategori_itu

Kalau user belum punya histori, rasionya balik ke 100% model umum -- pola
"jangan ngarang kalau data belum cukup" yang sama kayak `model_mood`.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET = ROOT / "DATASET" / "task_duration_dataset_id_lengkap.csv"
# Model yang udah dilatih, disimpen biar app nggak perlu latih ulang tiap
# dibuka (~1 detik, kerasa banget kalau pas user lagi nambah tugas).
# Bikin: python tools/latih_model_durasi.py
MODEL_PATH = ROOT / "app" / "data" / "model_durasi.joblib"

# Jumlah fitur teks. Lihat catatan di docstring soal 300 vs semua fitur.
MAX_FITUR_TEKS = 300
N_POHON = 300

# Bobot penggabungan model umum vs kecepatan asli user.
W_MODEL, W_PERSONAL = 0.6, 0.4

# Minimal sesi di satu kategori sebelum rata-rata personal dipercaya.
MIN_PERSONAL = 2

# Batas waras -- nggak ada gunanya nyaranin 2 menit atau 8 jam.
MIN_MENIT, MAX_MENIT = 5, 300

# Kuantil buat pita. 0.25/0.75 dipilih karena kalibrasinya paling pas
# (47% aktual vs 50% target). Pita yang lebih lebar kelihatan lebih "aman"
# tapi jadi nggak berguna: "10 sampai 200 menit" nggak nolong siapa pun.
Q_BAWAH, Q_ATAS = 0.25, 0.75

# Kategori opsional -- dipakai buat NYAMBUNGIN sesi ke rata-rata personal.
# Tetap ada karena judul tugas user seringkali terlalu pendek buat model teks
# ("bab 1"), sementara kategori bikin sesinya tetap bisa dipelajari.
KATEGORI = {
    "baca":    {"label": "Baca / pelajari", "satuan": "halaman"},
    "nulis":   {"label": "Nulis",           "satuan": "kata"},
    "soal":    {"label": "Ngerjain soal",   "satuan": "soal"},
    "koding":  {"label": "Koding",          "satuan": "bagian"},
    "revisi":  {"label": "Revisi / edit",   "satuan": "halaman"},
    "riset":   {"label": "Cari referensi",  "satuan": "sumber"},
    "admin":   {"label": "Admin / balas",   "satuan": "item"},
    "desain":  {"label": "Desain / slide",  "satuan": "slide"},
    "beberes": {"label": "Beberes",         "satuan": "area"},
}


@dataclass
class Perkiraan:
    menit: int                 # titik tengah, buat nyetel timer
    bawah: int                 # batas bawah pita
    atas: int                  # batas atas pita
    sumber: str                # "gabungan" | "model" | "kasar"
    n_personal: int = 0
    catatan: str = ""
    faktor_personal: float = 1.0

    @property
    def rentang(self) -> str:
        return f"{self.bawah}–{self.atas} menit"

    @property
    def sesi(self) -> int:
        """Berapa sesi fokus 25 menit kira-kira dibutuhin."""
        return max(1, math.ceil(self.menit / 25))


# ------------------------------------------------------------- pelatihan

_vec: Optional[TfidfVectorizer] = None
_hutan: Optional[RandomForestRegressor] = None
_n_latih: int = 0
_asal: str = ""


def _baca_dataset() -> tuple[list[str], np.ndarray, np.ndarray]:
    teks: list[str] = []
    num: list[list[float]] = []
    menit: list[float] = []
    if not DATASET.exists():
        return teks, np.zeros((0, 2)), np.zeros(0)
    with open(DATASET, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            judul = (row.get("tugas") or "").strip()
            try:
                jam = float(row["durasi_jam"])
                tempo = float(row.get("jatuh_tempo_hari") or 7)
                penting = float(row.get("tingkat_kepentingan_1_10") or 5)
            except (KeyError, TypeError, ValueError):
                continue
            if not judul or jam <= 0:
                continue
            teks.append(judul)
            num.append([tempo, penting])
            menit.append(jam * 60)
    return teks, np.array(num, dtype=float), np.array(menit, dtype=float)


def latih_dari_dataset() -> tuple[Optional[TfidfVectorizer], Optional[RandomForestRegressor], int]:
    """Latih dari CSV. Dipakai runtime DAN skrip pra-latih di tools/."""
    teks, num, menit = _baca_dataset()
    if len(teks) < 50:
        return None, None, 0

    # Target di ruang log: durasi tugas sebarannya menceng berat (2 menit
    # sampai 25 jam). Tanpa log, model bakal dikuasai segelintir tugas raksasa
    # dan salah total di tugas kecil -- yang justru paling sering dipakai.
    y = np.log1p(menit)

    # char_wb n-gram, bukan kata: judul tugas pendek dan penuh variasi bentuk
    # ("bersihkan"/"bersihin"/"beresin"). N-gram huruf nangkep akar katanya
    # tanpa perlu stemmer bahasa Indonesia.
    vec = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=2,
        sublinear_tf=True, max_features=MAX_FITUR_TEKS,
    )
    X = hstack([vec.fit_transform(teks), csr_matrix(num)]).toarray()
    hutan = RandomForestRegressor(
        N_POHON, min_samples_leaf=2, random_state=42, n_jobs=-1
    ).fit(X, y)
    return vec, hutan, len(teks)


def _latih() -> bool:
    """Siapin model: muat yang udah dilatih kalau ada, kalau nggak latih baru."""
    global _vec, _hutan, _n_latih, _asal
    if _hutan is not None:
        return True

    if MODEL_PATH.exists():
        try:
            import joblib

            paket = joblib.load(MODEL_PATH)
            _vec, _hutan, _n_latih = paket["vec"], paket["hutan"], paket["n"]
            _asal = "model pra-latih"
            return True
        except Exception:
            # File rusak / versi sklearn beda -> latih ulang, jangan mati.
            _vec = _hutan = None

    _vec, _hutan, _n_latih = latih_dari_dataset()
    _asal = "dilatih saat jalan" if _hutan is not None else ""
    return _hutan is not None


def reset_model() -> None:
    global _vec, _hutan, _n_latih, _asal
    _vec = _hutan = None
    _n_latih = 0
    _asal = ""


def status() -> dict:
    siap = _latih()
    return {
        "siap": siap,
        "n_latih": _n_latih,
        "asal": _asal,
        "sumber": DATASET.name if siap else "(dataset nggak ketemu)",
    }


def _batas(nilai: float) -> int:
    return int(max(MIN_MENIT, min(round(nilai), MAX_MENIT)))


def _prediksi_umum(judul: str, tempo_hari: float, penting: float) -> tuple[int, int, int]:
    if not _latih():
        # Cadangan kasar kalau datasetnya hilang: 30 menit, pita lebar.
        return 15, 30, 60
    X = hstack([_vec.transform([judul]), csr_matrix([[tempo_hari, penting]])]).toarray()
    # Tiap pohon punya tebakan sendiri; sebarannya = ketidakyakinan model.
    # Ini kenapa pita-nya melebar buat tugas yang bentuknya asing, dan
    # menyempit buat yang mirip banyak contoh di dataset.
    per_pohon = np.array([p.predict(X)[0] for p in _hutan.estimators_])
    lo = float(np.expm1(np.percentile(per_pohon, Q_BAWAH * 100)))
    mid = float(np.expm1(per_pohon.mean()))
    hi = float(np.expm1(np.percentile(per_pohon, Q_ATAS * 100)))
    lo, mid, hi = sorted([lo, mid, hi])
    return _batas(lo), _batas(mid), _batas(hi)


# --------------------------------------------------- kecepatan personal


def rata_personal(records: list[dict], kategori: str, jumlah: float) -> tuple[int, int]:
    """(menit rata-rata user, jumlah sampel) buat kategori ini.

    Diskalain per-unit pakai pangkat < 1, bukan dirata-rata mentah: kalau
    user biasanya 30 menit buat 10 soal, tugas 20 soal harusnya naik -- tapi
    NGGAK dua kali lipat, karena ada ongkos mulai yang cuma dibayar sekali.
    """
    if not kategori or jumlah <= 0:
        return 0, 0
    laju = []
    for r in records:
        if r.get("kategori") != kategori:
            continue
        try:
            unit = float(r["jumlah_unit"])
            menit = float(r["menit"])
        except (KeyError, TypeError, ValueError):
            continue
        if unit > 0 and menit > 0:
            laju.append(menit / (unit ** 0.82))
    if len(laju) < MIN_PERSONAL:
        return 0, len(laju)
    return _batas(_median(laju) * (jumlah ** 0.82)), len(laju)


def _median(nilai: list[float]) -> float:
    urut = sorted(nilai)
    n = len(urut)
    return urut[n // 2] if n % 2 else (urut[n // 2 - 1] + urut[n // 2]) / 2


# ------------------------------------------------------------- publik


def perkirakan(
    judul: str,
    tempo_hari: float = 7,
    penting: float = 5,
    kategori: str = "",
    jumlah: float = 0,
    records: Optional[list[dict]] = None,
    kalibrasi: Optional[float] = None,
    energi: Optional[int] = None,
) -> Perkiraan:
    """Perkiraan durasi akhir buat satu tugas.

    `kalibrasi` = faktor time-blindness user. Kalau nggak dioper, dihitung
    sendiri dari `records` -- dan kalau `energi` juga dikasih, faktornya
    diambil dari sesi-sesi user DI PITA ENERGI YANG SAMA.

    Itu cara app ini belajar hubungan energi-kecepatan: dari sesi user
    sendiri, bukan dari kolom karangan di dataset. Lihat penjelasan panjang
    di `fitur.kalibrasi_waktu()`.
    """
    if kalibrasi is None:
        from app.kalem_ml import fitur as _f

        kalibrasi = _f.kalibrasi_waktu(records or [], energi)
    lo, mid, hi = _prediksi_umum(judul or "tugas", tempo_hari, penting)

    # Kalibrasi personal digeser pelan (setengah jalan), bukan langsung penuh.
    # Faktor dari sedikit sesi gampang ekstrem, dan pergeseran mendadak bikin
    # angkanya keliatan nggak stabil.
    geser = 1.0 + (kalibrasi - 1.0) * 0.5
    lo, mid, hi = _batas(lo * geser), _batas(mid * geser), _batas(hi * geser)

    personal, n = rata_personal(records or [], kategori, jumlah)
    if personal:
        gabung = W_MODEL * mid + W_PERSONAL * personal
        # Pita ikut digeser sebanding, biar tetap kepusat di angka gabungan.
        rasio = gabung / mid if mid else 1.0
        lo, mid, hi = _batas(lo * rasio), _batas(gabung), _batas(hi * rasio)
        selisih = personal - int(gabung)
        if abs(selisih) >= 10:
            arah = "lebih lama" if selisih > 0 else "lebih cepat"
            catatan = (
                f"Dari {n} sesi kamu di kategori ini, kamu biasanya {arah} "
                "dari perkiraan umum — angkanya udah aku sesuaiin."
            )
        else:
            catatan = f"Cocok sama {n} sesi kamu sebelumnya."
        return Perkiraan(menit=int(mid), bawah=lo, atas=hi, sumber="gabungan",
                         n_personal=n, catatan=catatan, faktor_personal=geser)

    catatan = (
        "Perkiraan umum — Kalem belum punya catatan kecepatan kamu di sini. "
        "Makin sering dipakai, makin nyesuain."
    )
    if abs(geser - 1.0) >= 0.08:
        arah = "lebih lama" if geser > 1 else "lebih cepat"
        catatan = (
            f"Perkiraan umum, digeser dikit: sesi kamu biasanya {arah} dari "
            "yang diperkirakan."
        )
    return Perkiraan(menit=mid, bawah=lo, atas=hi, sumber="model",
                     n_personal=0, catatan=catatan, faktor_personal=geser)


def label_kategori(key: str) -> str:
    return KATEGORI.get(key, {}).get("label", key.title())


def satuan_kategori(key: str) -> str:
    return KATEGORI.get(key, {}).get("satuan", "unit")
