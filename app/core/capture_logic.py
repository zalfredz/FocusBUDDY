"""Klasifikasi deterministik quick capture menjadi Diary atau task Tracker."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app import clock, storage


TASK_PREFIXES = ("task:", "todo:", "tugas:")
DIARY_PREFIXES = ("cerita:", "diary:", "catatan:")
ACTION_WORDS = {
    "ambil", "balas", "bawa", "beli", "buat", "buka", "cari", "cek",
    "daftar", "hubungi", "isi", "kirim", "kerjakan", "kerjain", "rapikan",
    "revisi", "selesaikan", "siapkan", "tulis", "upload",
}
TASK_INTENT = ("harus", "perlu", "jangan lupa", "ingat untuk", "mau ngerjain")
STORY_SIGNALS = {
    "bahagia", "capek", "cemas", "kecewa", "lega", "marah", "sedih",
    "senang", "takut", "tenang", "overwhelmed",
}
MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
}


@dataclass(frozen=True)
class CaptureDraft:
    kind: str
    text: str
    deadline: str = ""
    deadline_time: str = ""


@dataclass(frozen=True)
class CaptureResult:
    kind: str
    route: str
    record_id: str


def _without_prefix(text: str, prefixes: tuple[str, ...]) -> str:
    lowered = text.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def _parse_deadline(text: str, today: date) -> tuple[str, str]:
    lowered = text.lower()
    deadline = ""
    if "lusa" in lowered:
        deadline = (today + timedelta(days=2)).isoformat()
    elif "besok" in lowered:
        deadline = (today + timedelta(days=1)).isoformat()
    elif "hari ini" in lowered:
        deadline = today.isoformat()

    iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", lowered)
    numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", lowered)
    named = re.search(
        r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")(?:\s+(20\d{2}))?\b",
        lowered,
    )
    try:
        if iso:
            deadline = date(int(iso[1]), int(iso[2]), int(iso[3])).isoformat()
        elif numeric:
            year = int(numeric[3]) if numeric[3] else today.year
            if year < 100:
                year += 2000
            deadline = date(year, int(numeric[2]), int(numeric[1])).isoformat()
        elif named:
            deadline = date(
                int(named[3]) if named[3] else today.year,
                MONTHS[named[2]],
                int(named[1]),
            ).isoformat()
    except ValueError:
        deadline = ""

    time_match = re.search(r"\b(?:jam\s*)?([01]?\d|2[0-3])[.:]([0-5]\d)\b", lowered)
    deadline_time = f"{int(time_match[1]):02d}:{int(time_match[2]):02d}" if time_match else ""
    if deadline_time and not deadline:
        deadline = today.isoformat()
    return deadline, deadline_time


def classify_capture(text: str) -> CaptureDraft:
    clean = " ".join((text or "").strip().split())
    lowered = clean.lower()
    if any(lowered.startswith(prefix) for prefix in TASK_PREFIXES):
        content = _without_prefix(clean, TASK_PREFIXES)
        deadline, deadline_time = _parse_deadline(content, clock.today())
        return CaptureDraft("task", content, deadline, deadline_time)
    if any(lowered.startswith(prefix) for prefix in DIARY_PREFIXES):
        return CaptureDraft("diary", _without_prefix(clean, DIARY_PREFIXES))

    words = set(re.findall(r"[a-zA-ZÀ-ÿ]+", lowered))
    first_words = list(re.findall(r"[a-zA-ZÀ-ÿ]+", lowered))[:3]
    task_score = sum(word in ACTION_WORDS for word in first_words)
    task_score += sum(signal in lowered for signal in TASK_INTENT)
    task_score += 2 if any(marker in lowered for marker in ("deadline", "besok", "lusa")) else 0
    story_score = sum(word in STORY_SIGNALS for word in words)
    story_score += 1 if any(marker in lowered for marker in ("aku merasa", "rasanya", "tadi ")) else 0

    if task_score > story_score and task_score > 0:
        deadline, deadline_time = _parse_deadline(clean, clock.today())
        return CaptureDraft("task", clean, deadline, deadline_time)
    return CaptureDraft("diary", clean)


def save_capture(text: str) -> CaptureResult:
    draft = classify_capture(text)
    if draft.kind == "diary":
        from app.core.mood_model import extract_keywords, extract_tags

        keywords = extract_keywords(draft.text)
        tags = keywords + [tag for tag in extract_tags(draft.text) if tag not in keywords]
        record = storage.add_diary_entry(
            draft.text,
            tags=tags[:6],
            source="quick_capture",
        )
        return CaptureResult("diary", "diary", (record or {}).get("id", ""))

    from models import model_durasi

    tempo = 7
    if draft.deadline:
        tempo = max(0, (date.fromisoformat(draft.deadline) - clock.today()).days)
    estimate = model_durasi.perkirakan(
        draft.text,
        tempo_hari=tempo,
        penting=8 if draft.deadline else 4,
        records=storage.get_focus_records(),
        energi=storage.today_energy() or 3,
    )
    task = storage.add_task(
        draft.text,
        draft.deadline,
        important=bool(draft.deadline),
        steps=[{"text": draft.text, "done": False}],
        difficulty_est=2,
        menit_est=estimate.menit,
        deadline_time=draft.deadline_time,
    )
    return CaptureResult("task", "tracker", task["id"])
