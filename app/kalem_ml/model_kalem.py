"""ML_KALEM -- kalibrasi lokal untuk seberapa kecil next action perlu dibuat.

Model ini TIDAK mengganti prioritas obat, krisis, Reset, atau pemilihan tugas.
Ia hanya belajar dari keputusan `focus` yang ditampilkan lalu dipencet/tidak,
dan bila sinyal keterlibatannya rendah ia boleh MENURUNKAN durasi fokus satu
tingkat. Jadi kegagalan model paling buruk hanya membuat target lebih ringan.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import wraps
from threading import RLock
from typing import Any, Optional

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

MIN_RECORDS = 20
MIN_PER_CLASS = 5
LOW_ENGAGEMENT = 0.35

FEATURES = (
    "skor_3h", "energi_terakhir", "streak_abai", "n_sos_7h",
    "n_belum_selesai", "n_mendesak", "beban_menit", "rasio_selesai_7h",
    "di_jam_produktif", "di_jam_capek", "jam", "weekday", "is_weekend",
    "obat_kelewat", "hari_sejak_checkin",
)


@dataclass(frozen=True)
class SinyalKalem:
    skor: float = 0.5
    siap: bool = False
    n_latih: int = 0
    sumber: str = "belum_cukup_data"

    @property
    def perlu_diringankan(self) -> bool:
        return self.siap and self.skor < LOW_ENGAGEMENT


_model: Optional[LogisticRegression] = None
_scaler: Optional[StandardScaler] = None
_fingerprint = ""
_n_latih = 0
_MODEL_LOCK = RLock()


def _locked(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with _MODEL_LOCK:
            return fn(*args, **kwargs)
    return wrapper


def _records_layak(records: list[dict]) -> list[dict]:
    """Hanya keputusan fokus dengan outcome yang cukup jelas."""
    return [
        record for record in records
        if record.get("kind") == "next_action"
        and record.get("action_kind") == "focus"
        and isinstance(record.get("fitur"), dict)
        and record.get("fitur")
    ]


def _tanda(records: list[dict]) -> str:
    raw = json.dumps(records, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _baris(fitur: Any) -> list[float]:
    source = getattr(fitur, "nilai", fitur) or {}
    out: list[float] = []
    for key in FEATURES:
        try:
            out.append(float(source.get(key, 0.0)))
        except (TypeError, ValueError):
            out.append(0.0)
    return out


def _latih(records: list[dict]) -> bool:
    global _model, _scaler, _fingerprint, _n_latih

    layak = _records_layak(records)
    label = [1 if record.get("acted") else 0 for record in layak]
    if len(layak) < MIN_RECORDS or min(label.count(0), label.count(1)) < MIN_PER_CLASS:
        return False

    tanda = _tanda(layak)
    if _model is not None and _fingerprint == tanda:
        return True

    X = np.asarray([_baris(record["fitur"]) for record in layak], dtype=float)
    y = np.asarray(label, dtype=int)
    # Banyak tampilan tanpa klik adalah sinyal lebih kuat daripada satu tampilan.
    bobot = np.asarray([max(1, int(record.get("n_tampil", 1))) for record in layak], dtype=float)
    _scaler = StandardScaler().fit(X)
    _model = LogisticRegression(
        max_iter=1000, class_weight="balanced", C=0.5, random_state=42
    ).fit(_scaler.transform(X), y, sample_weight=bobot)
    _fingerprint = tanda
    _n_latih = len(layak)
    return True


@_locked
def nilai(fitur: Any, records: Optional[list[dict]] = None) -> SinyalKalem:
    """Prediksi peluang pengguna memulai sesi fokus yang ditawarkan."""
    if records is None:
        from app import storage

        records = storage.get_decision_records()
    if not _latih(records or []):
        return SinyalKalem(n_latih=len(_records_layak(records or [])))
    assert _model is not None and _scaler is not None
    skor = float(_model.predict_proba(_scaler.transform([_baris(fitur)]))[0][1])
    return SinyalKalem(skor=skor, siap=True, n_latih=_n_latih, sumber="belajar")


@_locked
def status() -> dict:
    from app import storage

    records = _records_layak(storage.get_decision_records())
    siap = _latih(records)
    positif = sum(1 for record in records if record.get("acted"))
    return {
        "siap": siap,
        "n_latih": len(records),
        "min_records": MIN_RECORDS,
        "n_dipencet": positif,
        "n_dilewati": len(records) - positif,
    }


@_locked
def reset_model() -> None:
    global _model, _scaler, _fingerprint, _n_latih
    _model = _scaler = None
    _fingerprint = ""
    _n_latih = 0
