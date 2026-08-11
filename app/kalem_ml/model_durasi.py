"""Estimasi rentang durasi tugas dari teks dan histori personal."""
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
MODEL_PATH = ROOT / "app" / "data" / "model_durasi.joblib"

MAX_FITUR_TEKS = 300
N_POHON = 300

W_MODEL, W_PERSONAL = 0.6, 0.4

MIN_PERSONAL = 2

MIN_MENIT, MAX_MENIT = 5, 300

Q_BAWAH, Q_ATAS = 0.25, 0.75

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
    menit: int
    bawah: int
    atas: int
    sumber: str
    n_personal: int = 0
    catatan: str = ""
    faktor_personal: float = 1.0

    @property
    def rentang(self) -> str:
        return f"{self.bawah}–{self.atas} menit"

    @property
    def sesi(self) -> int:
        return max(1, math.ceil(self.menit / 25))


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
    teks, num, menit = _baca_dataset()
    if len(teks) < 50:
        return None, None, 0

    y = np.log1p(menit)

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
        return 15, 30, 60
    X = hstack([_vec.transform([judul]), csr_matrix([[tempo_hari, penting]])]).toarray()
    per_pohon = np.array([p.predict(X)[0] for p in _hutan.estimators_])
    lo = float(np.expm1(np.percentile(per_pohon, Q_BAWAH * 100)))
    mid = float(np.expm1(per_pohon.mean()))
    hi = float(np.expm1(np.percentile(per_pohon, Q_ATAS * 100)))
    lo, mid, hi = sorted([lo, mid, hi])
    return _batas(lo), _batas(mid), _batas(hi)


def rata_personal(records: list[dict], kategori: str, jumlah: float) -> tuple[int, int]:
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
    if kalibrasi is None:
        from app.kalem_ml import fitur as _f

        kalibrasi = _f.kalibrasi_waktu(records or [], energi)
    lo, mid, hi = _prediksi_umum(judul or "tugas", tempo_hari, penting)

    geser = 1.0 + (kalibrasi - 1.0) * 0.5
    lo, mid, hi = _batas(lo * geser), _batas(mid * geser), _batas(hi * geser)

    personal, n = rata_personal(records or [], kategori, jumlah)
    if personal:
        gabung = W_MODEL * mid + W_PERSONAL * personal
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


def satuan_kategori(key: str) -> str:
    return KATEGORI.get(key, {}).get("satuan", "unit")
