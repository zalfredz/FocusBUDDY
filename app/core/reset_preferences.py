"""Aturan distress dan sumber bantuan; eskalasi krisis tetap rule-based."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from app import clock

OPTIONS = {
    "napas": {
        "label": "Latihan napas 4-7-8",
        "desc": "Dipandu lingkaran yang ikut napas kamu, sekitar semenit",
        "icon": "AIR",
    },
    "grounding": {
        "label": "Balik ke sini: 5-4-3-2-1",
        "desc": "Nyebutin apa yang keliatan, kedengeran, kerasa — narik kamu keluar dari spiral",
        "icon": "VISIBILITY",
    },
    "musik": {
        "label": "Dengerin musik nenangin",
        "desc": "Langsung buka musik yang kamu bilang bikin tenang",
        "icon": "MUSIC_NOTE",
    },
    "gerak": {
        "label": "Gerak 60 detik",
        "desc": "Badan dulu yang digerakin, kepalanya nyusul",
        "icon": "DIRECTIONS_WALK",
    },
}

SOS_WINDOW_DAYS = 7
SOS_COUNT_THRESHOLD = 3
LOW_MOOD_THRESHOLD = 2.0


TRIGGER_DEFAULTS = {
    "tugas_numpuk": "grounding",
    "gagal_fokus": "grounding",
    "mulai_susah": "gerak",
    "deadline": "napas",
    "sosial": "napas",
    "kurang_tidur": "musik",
}


def music_links(query: str) -> list[dict]:
    from urllib.parse import quote_plus

    q = quote_plus(query.strip() or "lofi calm")
    return [
        {"name": "Spotify", "desc": f"Cari '{query}'", "url": f"https://open.spotify.com/search/{q}"},
        {"name": "YouTube Music", "desc": f"Cari '{query}'", "url": f"https://music.youtube.com/search?q={q}"},
    ]


@dataclass
class DistressSignal:
    escalate: bool
    sos_count: int
    avg_mood: Optional[float]
    reason: str = ""


def detect_distress(
    reset_events: list[dict],
    mood_logs: list[dict],
    window_days: int = SOS_WINDOW_DAYS,
) -> DistressSignal:
    today = clock.today()

    def within_window(iso_day: str) -> bool:
        return (today - date.fromisoformat(iso_day)).days < window_days

    recent_sos_days = {
        e.get("date") for e in reset_events
        if e.get("date") and within_window(e["date"])
    }
    sos_count = len(recent_sos_days)

    recent_scores = [
        log["score"] for log in mood_logs
        if log.get("score") is not None and within_window(log["date"])
    ]
    avg_mood = sum(recent_scores) / len(recent_scores) if recent_scores else None

    escalate = (
        sos_count >= SOS_COUNT_THRESHOLD
        and avg_mood is not None
        and avg_mood <= LOW_MOOD_THRESHOLD
    )

    reason = ""
    if escalate:
        reason = (
            f"Dalam {window_days} hari terakhir kamu butuh Reset di {sos_count} hari "
            f"dan mood kamu rata-rata {avg_mood:.1f}/5."
        )

    return DistressSignal(
        escalate=escalate,
        sos_count=sos_count,
        avg_mood=avg_mood,
        reason=reason,
    )


CRISIS_HOTLINES = [
    {
        "name": "Healing119.id — Kemenkes",
        "desc": "Hubungi 119, lalu pilih ekstensi 8",
        "number": "119 ext. 8",
        "tel": "tel:119",
        "web": "https://healing119.id",
    },
]

TELEHEALTH_PARTNERS = [
    {
        "name": "Into The Light",
        "desc": "Direktori layanan & hotline krisis di Indonesia",
        "url": "https://www.intothelightid.org/saya-ingin-bunuh-diri/",
    },
    {
        "name": "Halodoc",
        "desc": "Cari psikolog & psikiater online",
        "url": "https://www.halodoc.com/cari-dokter/spesialis-kejiwaan",
    },
    {
        "name": "Riliv",
        "desc": "Konseling psikolog via chat",
        "url": "https://riliv.co",
    },
]
