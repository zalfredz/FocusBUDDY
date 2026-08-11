"""Prediksi mood personal dengan fallback saat histori belum cukup."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import wraps
from threading import RLock
from typing import Any, Optional

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from app import clock, storage
from models import fitur as F
from models import riwayat

MIN_POLA = 5
MIN_MODEL = 10

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


@dataclass
class RamalanMood:
    siap: bool
    skor: Optional[float] = None
    sumber: str = ""
    n_data: int = 0
    alasan: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if not self.siap or self.skor is None:
            return "belum kebaca"
        if self.skor <= 2.2:
            return "berat"
        if self.skor >= 4.0:
            return "lumayan"
        return "biasa aja"


def rata_per_hari(logs: list[dict]) -> dict[int, float]:
    kelompok: dict[int, list[float]] = {}
    for log in logs:
        wd = log.get("weekday")
        if wd is None:
            try:
                from datetime import date

                wd = date.fromisoformat(log["date"]).weekday()
            except (KeyError, ValueError, TypeError):
                continue
        kelompok.setdefault(int(wd), []).append(float(log["score"]))
    return {k: sum(v) / len(v) for k, v in kelompok.items()}


_model: Optional[RandomForestRegressor] = None
_n_latih: int = 0
_tanda: str = ""
_MODEL_LOCK = RLock()


def _locked(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with _MODEL_LOCK:
            return fn(*args, **kwargs)
    return wrapper


@_locked
def reset_model() -> None:
    global _model, _n_latih, _tanda
    _model = None
    _n_latih = 0
    _tanda = ""


def _latih(day: Any = None) -> bool:
    global _model, _n_latih, _tanda
    X, meta = riwayat.baris_harian(day=day)
    if len(X) < MIN_MODEL:
        return False

    tanda = riwayat.sidik_jari(X, meta)
    if _model is not None and _tanda == tanda:
        return True

    Xa, y = [], []
    for i in range(len(X) - 1):
        Xa.append(X[i])
        y.append(meta[i + 1]["skor"])
    if len(Xa) < MIN_MODEL - 1:
        return False

    _model = RandomForestRegressor(
        100, max_depth=6, min_samples_leaf=2, random_state=42
    ).fit(np.array(Xa, dtype=float), np.array(y, dtype=float))
    _n_latih = len(Xa)
    _tanda = tanda
    return True


@_locked
def ramal(f: Optional[F.Fitur] = None) -> RamalanMood:
    f = f or F.bangun_fitur()
    logs = f.catatan.get("logs") or []
    day = f.catatan.get("day")
    n = len(logs)

    if n < MIN_POLA:
        return RamalanMood(siap=False, n_data=n)

    hari_ini = clock.today().weekday()
    rata = rata_per_hari(logs)
    dasar = rata.get(hari_ini)

    if not _latih(day) or dasar is None:
        if dasar is None:
            dasar = sum(l["score"] for l in logs) / n
            alasan = ["dari rata-rata catatan kamu"]
        else:
            alasan = [f"{HARI[hari_ini]} biasanya segini buat kamu"]
        return RamalanMood(siap=True, skor=float(dasar), sumber="rata_hari",
                           n_data=n, alasan=alasan)

    baris = riwayat.baris_hari_ini(f)
    p = float(_model.predict([baris])[0])

    w = _n_latih / (_n_latih + 15.0)
    gabung = w * p + (1 - w) * dasar

    alasan = [f"{HARI[hari_ini]} biasanya segini buat kamu"]
    if f["streak_abai"] >= 2:
        alasan.append("beberapa hari makan/istirahat kelewat")
    if f["n_sos_7h"] >= 2:
        alasan.append("minggu ini beberapa kali butuh jeda")
    if f["tren_mood"] <= -0.5:
        alasan.append("tren mood kamu lagi turun")

    return RamalanMood(
        siap=True, skor=max(1.0, min(gabung, 5.0)), sumber="model",
        n_data=_n_latih, alasan=alasan[:3],
    )


@_locked
def status() -> dict:
    logs = [l for l in storage.get_mood_logs() if l.get("score") is not None]
    return {
        "n_catatan": len(logs),
        "siap_pola": len(logs) >= MIN_POLA,
        "siap_model": _latih(),
        "n_latih": _n_latih,
    }
