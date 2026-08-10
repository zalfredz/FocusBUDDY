"""Jam aplikasi -- satu-satunya sumber "hari ini" buat seluruh app.

Alasan modul ini ada: fitur yang bergantung riwayat beberapa hari (mood
model, deteksi distress, prediksi obat habis) mustahil dites kalau harus
nunggu hari beneran ganti. Dengan offset yang bisa digeser, satu sesi
testing bisa nyimulasiin dua minggu pemakaian.

Di produksi offset-nya selalu 0, jadi `today()` sama persis dengan
`date.today()`. Pada Flet Web, offset disimpan per sesi browser supaya tombol
demo satu peserta tidak mengubah waktu peserta lain.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app import session_scope

_SESSION_KEY = "focusbuddy.clock.v1"


@dataclass
class _ClockState:
    days: int = 0
    # Geseran JAM, kepisah dari geseran hari. Perlu sendiri karena ada fitur
    # yang gerbangnya jam, bukan tanggal.
    hours: int = 0


_FALLBACK_STATE = _ClockState()


def _state() -> _ClockState:
    """State sesi browser aktif; fallback global hanya untuk CLI/test."""
    return session_scope.get_or_create(_SESSION_KEY, _ClockState) or _FALLBACK_STATE


def set_offset(days: int) -> None:
    _state().days = int(days)


def get_offset() -> int:
    return _state().days


def advance(days: int = 1) -> int:
    state = _state()
    state.days += int(days)
    return state.days


def set_hour_offset(hours: int) -> None:
    _state().hours = int(hours)


def get_hour_offset() -> int:
    return _state().hours


def advance_hours(hours: int) -> int:
    state = _state()
    state.hours += int(hours)
    return state.hours


def hours_until(target_hour: int) -> int:
    """Berapa jam lagi biar `now()` nyampe di `target_hour`.

    Kalau sekarang udah lewat jamnya, dilanjut ke hari berikutnya -- jadi
    tombolnya selalu maju, nggak pernah mundurin waktu.
    """
    selisih = target_hour - now().hour
    return selisih if selisih > 0 else selisih + 24


def reset_offset() -> None:
    state = _state()
    state.days = 0
    state.hours = 0


def is_simulated() -> bool:
    state = _state()
    return state.days != 0 or state.hours != 0


def today() -> date:
    # Diturunin dari now(), bukan dihitung sendiri: geseran jam yang nyebrang
    # tengah malam harus ikut ganti tanggal juga. Kalau dua-duanya dihitung
    # terpisah, jam bisa nunjukkin 01.00 tapi tanggalnya masih kemarin.
    return now().date()


def now() -> datetime:
    state = _state()
    return datetime.now() + timedelta(days=state.days, hours=state.hours)
