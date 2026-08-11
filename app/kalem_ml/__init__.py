"""Model personal KALEM dan status kesiapan masing-masing model."""
from __future__ import annotations

from app.kalem_ml import (  # noqa: F401
    fitur,
    model_durasi,
    model_energi,
    model_kalem,
    model_mood,
    model_overwhelm,
    model_pecah,
    model_penenang,
    riwayat,
)

__all__ = [
    "fitur",
    "riwayat",
    "model_durasi",
    "model_mood",
    "model_energi",
    "model_kalem",
    "model_overwhelm",
    "model_penenang",
    "model_pecah",
    "status_semua",
    "reset_semua",
]


def status_semua() -> dict:
    return {
        "durasi": model_durasi.status(),
        "mood": model_mood.status(),
        "energi": model_energi.status(),
        "kalem": model_kalem.status(),
        "overwhelm": model_overwhelm.status(),
        "penenang": model_penenang.status(),
        "pecah": model_pecah.status(),
    }


def reset_semua() -> None:
    model_durasi.reset_model()
    model_mood.reset_model()
    model_overwhelm.reset_model()
    model_kalem.reset_model()
