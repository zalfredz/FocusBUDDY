"""Jam aplikasi -- satu-satunya sumber "hari ini" buat seluruh app.

Alasan modul ini ada: fitur yang bergantung riwayat beberapa hari (mood
model, deteksi distress, prediksi obat habis) mustahil dites kalau harus
nunggu hari beneran ganti. Dengan offset yang bisa digeser, satu sesi
testing bisa nyimulasiin dua minggu pemakaian.

Di produksi offset-nya selalu 0, jadi `today()` sama persis dengan
`date.today()`. Modul ini sengaja nggak import apa-apa dari app lain
supaya bebas dari circular import.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

_offset_days = 0


def set_offset(days: int) -> None:
    global _offset_days
    _offset_days = int(days)


def get_offset() -> int:
    return _offset_days


def advance(days: int = 1) -> int:
    global _offset_days
    _offset_days += int(days)
    return _offset_days


def reset_offset() -> None:
    global _offset_days
    _offset_days = 0


def is_simulated() -> bool:
    return _offset_days != 0


def today() -> date:
    return date.today() + timedelta(days=_offset_days)


def now() -> datetime:
    return datetime.now() + timedelta(days=_offset_days)
