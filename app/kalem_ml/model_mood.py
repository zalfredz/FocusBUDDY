"""MODEL MOOD -- "hari ini kemungkinan bakal kayak gimana?"

Yang diramal: skor mood hari ini (1-5), SEBELUM user check-in. Dipakai
Morning Brief buat nyusun ramalan, dan `model_energi` buat nentuin beban
kerja yang masuk akal.

TIGA TAHAP, JUJUR SOAL TAHAPNYA
-------------------------------
    < 5 catatan    ->  nggak meramal sama sekali. Kalem bilang apa adanya
                       "belum cukup data" -- ini yang bikin kepercayaan
                       kebangun, dan sekali dilanggar susah balik.
    5-9 catatan    ->  rata-rata hari yang sama (mis. rata-rata Selasa).
    >= 10 catatan  ->  RandomForest dari riwayat user sendiri, dicampur
                       rata-rata hari biar nggak liar.

BEDA SAMA `energy_predictor`
----------------------------
`model_energi` dilatih dari data SINTETIS -- dia nebak beban kerja yang
wajar buat kondisi apa pun, termasuk buat user yang baru instal. Yang ini
cuma belajar dari data USER SENDIRI, dan diam kalau datanya belum ada.
Dua peran yang beda, sengaja nggak digabung.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import wraps
from threading import RLock
from typing import Any, Optional

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from app import clock, storage
from app.kalem_ml import fitur as F
from app.kalem_ml import riwayat

MIN_POLA = 5      # sebelum ini: nggak meramal
MIN_MODEL = 10    # sebelum ini: rata-rata hari yang sama

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


@dataclass
class RamalanMood:
    siap: bool
    skor: Optional[float] = None
    sumber: str = ""              # "" | "rata_hari" | "model"
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

    # Kunci cache dari ISI data, bukan jumlah barisnya -- lihat penjelasan
    # panjang di `riwayat.sidik_jari()`. Versi lama (`f"{len(X)}"`) bikin dua
    # user beda yang sama-sama punya N catatan dianggap identik.
    tanda = riwayat.sidik_jari(X, meta)
    if _model is not None and _tanda == tanda:
        return True

    # Target = skor HARI BERIKUTNYA. Ini yang bikin modelnya meramal, bukan
    # ngapalin: kalau targetnya skor hari itu sendiri, kolom "skor" di fitur
    # adalah jawabannya (kebocoran total, akurasi 100% tapi gunanya nol).
    Xa, y = [], []
    for i in range(len(X) - 1):
        Xa.append(X[i])
        y.append(meta[i + 1]["skor"])
    if len(Xa) < MIN_MODEL - 1:
        return False

    # 100 pohon, TANPA n_jobs=-1 -- diukur: predict() 1 baris kena overhead
    # spin-up joblib parallel yang lebih mahal dari kerjaannya sendiri buat
    # kerjaan sekecil ini (48ms -> 23ms cuma dari buang n_jobs, -> 12ms lagi
    # dari 200 ke 100 pohon, hasil prediksi nggak berubah di data uji).
    # `decide()`/`build_morning_brief()` motong bagian ini tiap kali halaman
    # dibuka, jadi latensi predict-nya kerasa langsung ke user.
    _model = RandomForestRegressor(
        100, max_depth=6, min_samples_leaf=2, random_state=42
    ).fit(np.array(Xa, dtype=float), np.array(y, dtype=float))
    _n_latih = len(Xa)
    _tanda = tanda
    return True


@_locked
def ramal(f: Optional[F.Fitur] = None) -> RamalanMood:
    f = f or F.bangun_fitur()
    # Catatan diambil dari snapshot yang dioper, BUKAN baca storage lagi.
    # Kalau baca ulang, `f` yang dibangun dari DayState buatan bakal
    # diam-diam dicampur data storage yang lagi aktif.
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
            # Belum pernah check-in di hari ini -> pakai rata-rata semua.
            dasar = sum(l["score"] for l in logs) / n
            alasan = ["dari rata-rata catatan kamu"]
        else:
            alasan = [f"{HARI[hari_ini]} biasanya segini buat kamu"]
        return RamalanMood(siap=True, skor=float(dasar), sumber="rata_hari",
                           n_data=n, alasan=alasan)

    baris = riwayat.baris_hari_ini(f)
    p = float(_model.predict([baris])[0])

    # Dicampur rata-rata hari. Bobot model naik pelan seiring data numpuk.
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
