"""Proyeksi stok obat dari resep pengguna; tidak menentukan atau menyarankan dosis."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from app import clock

REMINDER_THRESHOLD_DAYS = 3

ONLINE_PHARMACY_PARTNERS = [
    {"name": "Halodoc", "desc": "Resep & antar ke rumah", "url": "https://www.halodoc.com"},
    {"name": "K24Klik", "desc": "Apotek online 24 jam", "url": "https://www.k24klik.com"},
]


@dataclass
class MedicationStatus:
    active: bool
    name: str = ""
    days_left: int = 0
    depletion_date: Optional[date] = None
    pills_remaining: float = 0.0
    needs_reminder: bool = False
    message: str = ""
    taken_today: bool = False


def check_status(medication: Optional[dict], today: Optional[date] = None) -> MedicationStatus:
    if not medication or not medication.get("enabled", True):
        return MedicationStatus(active=False)

    today = today or clock.today()
    rate = max(float(medication.get("pills_per_day", 1)), 0.01)
    remaining = float(medication.get("pills_left", 0))
    taken_today = medication.get("last_taken") == today.isoformat()

    if remaining <= 0:
        return MedicationStatus(
            active=True,
            name=medication.get("name", "Obat"),
            days_left=0,
            depletion_date=today,
            pills_remaining=0.0,
            needs_reminder=True,
            message=f"Stok {medication.get('name', 'obat')} kamu diperkirakan sudah habis.",
            taken_today=taken_today,
        )

    days_left = math.floor(remaining / rate)
    depletion_date = today + timedelta(days=days_left)
    needs_reminder = days_left <= REMINDER_THRESHOLD_DAYS

    message = ""
    if needs_reminder:
        nama = medication.get("name", "Obat")
        tanggal = depletion_date.strftime("%d %b")
        if days_left == 1:
            message = f"{nama} diperkirakan habis esok ({tanggal})."
        else:
            message = f"{nama} diperkirakan habis {days_left} hari lagi ({tanggal})."

    return MedicationStatus(
        active=True,
        name=medication.get("name", "Obat"),
        days_left=days_left,
        depletion_date=depletion_date,
        pills_remaining=remaining,
        needs_reminder=needs_reminder,
        message=message,
        taken_today=taken_today,
    )


def missed_streak(medication: Optional[dict], today: Optional[date] = None) -> int:
    if not medication or not medication.get("enabled", True):
        return 0

    today = today or clock.today()
    taken = set(medication.get("take_log", []))

    try:
        start = date.fromisoformat(medication.get("start_date", ""))
    except (TypeError, ValueError):
        start = None

    streak = 0
    cursor = today - timedelta(days=1)
    while streak < 14:
        if start and cursor < start:
            break
        if cursor.isoformat() in taken:
            break
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def maps_search_url(query: str = "apotek terdekat") -> str:
    from urllib.parse import quote_plus

    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"
