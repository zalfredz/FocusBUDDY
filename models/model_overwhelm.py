"""Prediksi risiko overwhelm dari fitur harian dan histori Reset."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import wraps
from threading import RLock
from typing import Any, Optional

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from models import fitur as F
from models import riwayat
from app.runtime_policy import runtime_training_allowed

MIN_HARI = 10
MIN_PER_KELAS = 2

AMBANG_WASPADA, AMBANG_BERAT = 0.35, 0.60


@dataclass
class Risiko:
    skor: float
    tingkat: str
    sumber: str
    alasan: list[str] = field(default_factory=list)
    n_data: int = 0

    @property
    def perlu_diringankan(self) -> bool:
        return self.tingkat in ("waspada", "berat")


def _prior(f: F.Fitur) -> tuple[float, list[str]]:
    skor = 0.0
    alasan: list[str] = []

    if f["n_sos_3h"] >= 2:
        skor += 0.30
        alasan.append("beberapa hari terakhir kamu butuh jeda berulang")
    elif f["n_sos_7h"] >= 2:
        skor += 0.15
        alasan.append("minggu ini udah beberapa kali ambil jeda")

    if f["skor_3h"] and f["skor_3h"] <= 2.5:
        skor += 0.25
        alasan.append("mood kamu lagi rendah beberapa hari ini")
    elif f["tren_mood"] <= -0.8:
        skor += 0.12
        alasan.append("mood kamu lagi turun dibanding biasanya")

    if f["streak_abai"] >= 3:
        skor += 0.20
        alasan.append(f"{int(f['streak_abai'])} hari makan/istirahat kelewat")
    elif f["streak_abai"] >= 1:
        skor += 0.08

    if f["tidur_jam"] < 5.5:
        skor += 0.10
        alasan.append("pola tidur kamu lagi berantakan")

    if f["obat_kelewat"] >= 2:
        skor += 0.10
        alasan.append(f"obat belum keabsen {int(f['obat_kelewat'])} hari")

    if f["n_mendesak"] >= 3:
        skor += 0.15
        alasan.append(f"{int(f['n_mendesak'])} tugas mendesak hari ini")
    elif f["n_belum_selesai"] >= 5:
        skor += 0.10
        alasan.append(f"{int(f['n_belum_selesai'])} tugas numpuk")

    if f["umur_tugas_tertua"] >= 14:
        skor += 0.08
        alasan.append("ada tugas yang udah lama ngendon")

    if f["di_jam_capek"]:
        skor += 0.05

    return min(skor, 1.0), alasan


_model: Optional[LogisticRegression] = None
_scaler: Optional[StandardScaler] = None
_n_latih: int = 0
_terlatih_dari: str = ""
_MODEL_LOCK = RLock()


def _locked(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with _MODEL_LOCK:
            return fn(*args, **kwargs)
    return wrapper


@_locked
def reset_model() -> None:
    global _model, _scaler, _n_latih, _terlatih_dari
    _model = _scaler = None
    _n_latih = 0
    _terlatih_dari = ""


def _latih(day: Any = None) -> bool:
    global _model, _scaler, _n_latih, _terlatih_dari
    if not runtime_training_allowed():
        return False

    X, meta = riwayat.baris_harian(day=day)
    if len(X) < MIN_HARI:
        return False
    y = np.array([1 if m["ada_sos"] else 0 for m in meta])
    if y.sum() < MIN_PER_KELAS or (len(y) - y.sum()) < MIN_PER_KELAS:
        return False

    tanda = riwayat.sidik_jari(X, meta)
    if _model is not None and _terlatih_dari == tanda:
        return True

    Xa = np.array(X, dtype=float)
    _scaler = StandardScaler().fit(Xa)
    _model = LogisticRegression(
        max_iter=1000, class_weight="balanced", C=0.5, random_state=42
    ).fit(_scaler.transform(Xa), y)
    _n_latih = len(X)
    _terlatih_dari = tanda
    return True


def _bobot_teratas(baris: list[float], n: int = 2) -> list[str]:
    if _model is None or _scaler is None:
        return []
    z = _scaler.transform([baris])[0]
    kontrib = _model.coef_[0] * z
    urut = np.argsort(kontrib)[::-1]
    nama = {
        "skor": "mood kamu hari ini",
        "energi": "energi kamu",
        "makan": "makan kamu hari ini",
        "istirahat": "istirahat kamu semalam",
        "weekday": "hari ini di minggu kamu",
        "is_weekend": "weekend/hari kerja",
        "sos_7h_sebelum": "seringnya kamu ambil jeda minggu ini",
        "streak_abai": "makan & istirahat yang kelewat",
        "n_tugas": "jumlah tugas hari ini",
        "n_mendesak": "tugas yang mendesak",
    }
    out = []
    for i in urut[:n]:
        if kontrib[i] <= 0.05:
            break
        out.append(nama.get(riwayat.KOLOM[i], riwayat.KOLOM[i]))
    return out


@_locked
def nilai(f: Optional[F.Fitur] = None) -> Risiko:
    f = f or F.bangun_fitur()
    skor_prior, alasan = _prior(f)

    if not _latih(f.catatan.get("day")):
        return Risiko(
            skor=skor_prior,
            tingkat=_tingkat(skor_prior),
            sumber="prior",
            alasan=alasan[:3],
            n_data=int(f["n_catatan"]),
        )

    baris = riwayat.baris_hari_ini(f)
    p = float(_model.predict_proba(_scaler.transform([baris]))[0][1])

    w = _n_latih / (_n_latih + 20.0)
    gabung = w * p + (1 - w) * skor_prior

    belajar = _bobot_teratas(baris)
    semua = alasan[:2] + [a for a in belajar if a not in alasan][:1]

    return Risiko(
        skor=gabung,
        tingkat=_tingkat(gabung),
        sumber="belajar",
        alasan=semua[:3],
        n_data=_n_latih,
    )


def _tingkat(skor: float) -> str:
    if skor >= AMBANG_BERAT:
        return "berat"
    if skor >= AMBANG_WASPADA:
        return "waspada"
    return "tenang"


@_locked
def status() -> dict:
    siap = _latih()
    return {"siap": siap, "n_latih": _n_latih, "min_hari": MIN_HARI}
