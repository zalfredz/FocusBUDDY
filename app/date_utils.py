"""Helper tanggal kalender yang aman dari pergeseran zona waktu."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Any


APP_TIMEZONE = timezone(timedelta(hours=7), "WIB")
MONTH_NAMES_ID = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)


def _as_calendar_date(value: Any) -> date | None:
    """Ubah nilai DatePicker menjadi tanggal lokal tanpa memotong timestamp UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(APP_TIMEZONE).date()
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None

    raw = value.strip()
    try:
        if len(raw) == 10:
            return date.fromisoformat(raw)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None and parsed.utcoffset() is not None:
            parsed = parsed.astimezone(APP_TIMEZONE)
        return parsed.date()
    except ValueError:
        return None


def selected_calendar_date(picker_value: Any, event_data: Any = None) -> date | None:
    """Ambil tanggal pilihan user, mengutamakan data event kalender bila tersedia."""
    return _as_calendar_date(event_data) or _as_calendar_date(picker_value)


def years_before(value: date, years: int) -> date:
    """Geser tahun secara dinamis dan amankan 29 Februari pada tahun non-kabisat."""
    target_year = value.year - years
    last_day = calendar.monthrange(target_year, value.month)[1]
    return date(target_year, value.month, min(value.day, last_day))


def format_date_id(value: str, empty_label: str = "Pilih tanggal") -> str:
    """Format tanggal ISO menjadi tanggal Indonesia untuk copy antarmuka."""
    try:
        selected = date.fromisoformat(value)
    except (TypeError, ValueError):
        return empty_label
    return f"{selected.day} {MONTH_NAMES_ID[selected.month - 1]} {selected.year}"
