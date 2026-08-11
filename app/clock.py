"""Jam aplikasi dengan offset per sesi untuk kebutuhan demo."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app import session_scope

_SESSION_KEY = "focusbuddy.clock.v1"


@dataclass
class _ClockState:
    days: int = 0
    hours: int = 0


_FALLBACK_STATE = _ClockState()


def _state() -> _ClockState:
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
    return now().date()


def now() -> datetime:
    state = _state()
    return datetime.now() + timedelta(days=state.days, hours=state.hours)
