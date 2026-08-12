"""Mencegah fungsi training baru terpanggil tanpa konteks eksperimen offline."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


class OfflineTrainingRequired(RuntimeError):
    """Training dicoba dari luar entrypoint eksperimen offline."""


_OFFLINE_TRAINING_ACTIVE: ContextVar[bool] = ContextVar(
    "focusbuddy_offline_training_active", default=False
)


def require_offline_training() -> None:
    if not _OFFLINE_TRAINING_ACTIVE.get():
        raise OfflineTrainingRequired(
            "Training hanya boleh dijalankan dari sesi eksperimen offline."
        )


@contextmanager
def offline_training_session() -> Iterator[None]:
    token = _OFFLINE_TRAINING_ACTIVE.set(True)
    try:
        yield
    finally:
        _OFFLINE_TRAINING_ACTIVE.reset(token)
