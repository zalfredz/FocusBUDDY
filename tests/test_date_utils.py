"""Regresi DatePicker agar pilihan kalender tidak mundur satu hari."""
from datetime import date, datetime, timezone

from app.date_utils import selected_calendar_date, years_before


def test_event_date_wins_over_shifted_picker_value() -> None:
    shifted = datetime(2026, 1, 28, 17, tzinfo=timezone.utc)
    assert selected_calendar_date(shifted, "2026-01-29") == date(2026, 1, 29)


def test_aware_datetime_is_converted_before_taking_date() -> None:
    selected = datetime(2026, 1, 28, 17, tzinfo=timezone.utc)
    assert selected_calendar_date(selected) == date(2026, 1, 29)


def test_year_shift_handles_leap_day_without_hardcoded_day() -> None:
    assert years_before(date(2024, 2, 29), 1) == date(2023, 2, 28)
    assert years_before(date(2024, 2, 29), 4) == date(2020, 2, 29)
