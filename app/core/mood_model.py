"""Analisis pola mood dari histori check-in pengguna."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sklearn.tree import DecisionTreeRegressor

from app import clock
from app.runtime_policy import runtime_training_allowed

MIN_LOGS_FOR_PATTERN = 5
MIN_LOGS_FOR_MODEL = 10
MIN_PER_DAYTYPE = 2
MIN_PER_WEEKDAY = 2
MIN_TAG_COUNT = 2
MIN_FOCUS_PER_ENERGY_GROUP = 3

DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "aku", "saya", "gue", "gua",
    "banget", "aja", "udah", "sudah", "lagi", "buat", "sama", "juga", "nggak",
    "gak", "tidak", "bisa", "ada", "untuk", "tapi", "kalau", "biar", "jadi",
    "sih", "deh", "kok", "pas", "abis", "habis", "terus", "trus", "gitu", "hari",
    "ya", "nya", "dengan", "karena", "masih", "belum", "akan", "pada", "dalam",
}


QUICK_TAGS = {
    "kuliah": "Kuliah",
    "kerja": "Kerja",
    "kelompok": "Kerja kelompok",
    "keluarga": "Keluarga",
    "sosial": "Ketemu orang",
    "sendirian": "Sendirian",
    "olahraga": "Gerak badan",
    "istirahat": "Istirahat",
}

KEYWORD_MAP = {
    "capek": ["capek", "lelah", "ngantuk", "letih", "drained", "burnout"],
    "deadline": ["deadline", "dikejar", "mepet", "telat", "buru"],
    "cemas": ["cemas", "takut", "khawatir", "panik", "gelisah", "overthinking"],
    "senang": ["senang", "seneng", "lega", "bahagia", "puas", "bangga"],
    "marah": ["marah", "kesel", "jengkel", "sebel"],
    "sendiri": ["sendiri", "sepi", "kesepian"],
    "produktif": ["produktif", "selesai", "kelar", "beres", "berhasil"],
}


def extract_keywords(diary_text: str) -> list[str]:
    text = (diary_text or "").lower()
    return [key for key, words in KEYWORD_MAP.items() if any(w in text for w in words)]


def recurring_tag_prompt(logs: list[dict], min_count: int = 2) -> Optional[str]:
    paired: dict[str, list[int]] = defaultdict(list)
    for log in logs:
        score = log.get("score")
        if score is None:
            continue
        for tag in (log.get("quick_tags") or []):
            paired[tag].append(score)

    for tag, scores in sorted(paired.items(), key=lambda kv: len(kv[1]), reverse=True):
        if len(scores) >= min_count and sum(scores) / len(scores) <= 3.0:
            label = QUICK_TAGS.get(tag, tag).lower()
            return f"Tiap kali kamu nandain '{label}', mood kamu cenderung turun. Lagi ada apa di situ?"
    return None


def neglect_streak(logs: list[dict]) -> int:
    streak = 0
    for log in logs:
        ate = log.get("ate_today")
        rested = log.get("rested_enough")
        if ate is None and rested is None:
            continue
        if ate is False or rested is False:
            streak += 1
        else:
            break
    return streak


def checkin_streak(logs: list[dict], today: Optional[date] = None) -> int:
    today = today or clock.today()
    seen = set()
    for log in logs:
        try:
            seen.add(date.fromisoformat(log["date"]))
        except (KeyError, ValueError, TypeError):
            continue
    if not seen:
        return 0

    from datetime import timedelta

    cursor = today if today in seen else today - timedelta(days=1)
    streak = 0
    while cursor in seen and streak < 10:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@dataclass
class MoodInsight:
    ready: bool
    log_count: int
    headline: str
    details: list[str] = field(default_factory=list)
    best_day: Optional[str] = None
    hardest_day: Optional[str] = None
    top_tags: list[tuple[str, int]] = field(default_factory=list)
    predicted_score: Optional[float] = None


def extract_tags(diary_text: str, limit: int = 5) -> list[str]:
    words = re.findall(r"[a-zA-ZÀ-ÿ]{4,}", (diary_text or "").lower())
    meaningful = [w for w in words if w not in STOPWORDS]
    return [w for w, _ in Counter(meaningful).most_common(limit)]


def _weekday_groups(logs: list[dict]) -> dict[int, list[int]]:
    grouped: dict[int, list[int]] = defaultdict(list)
    for log in logs:
        weekday = log.get("weekday")
        if weekday is None:
            try:
                weekday = date.fromisoformat(log["date"]).weekday()
            except (KeyError, TypeError, ValueError):
                continue
        grouped[weekday].append(log["score"])
    return grouped


def _weekday_averages(logs: list[dict]) -> dict[int, float]:
    grouped = _weekday_groups(logs)
    return {day: sum(scores) / len(scores) for day, scores in grouped.items()}


def _daytype_averages(logs: list[dict]) -> tuple[Optional[float], Optional[float], int, int]:
    weekday_scores = [l["score"] for l in logs if not _is_weekend(l)]
    weekend_scores = [l["score"] for l in logs if _is_weekend(l)]
    weekday_avg = sum(weekday_scores) / len(weekday_scores) if weekday_scores else None
    weekend_avg = sum(weekend_scores) / len(weekend_scores) if weekend_scores else None
    return weekday_avg, weekend_avg, len(weekday_scores), len(weekend_scores)


def _is_weekend(log: dict) -> bool:
    if "is_weekend" in log and log["is_weekend"] is not None:
        return bool(log["is_weekend"])
    return date.fromisoformat(log["date"]).weekday() >= 5


def _predict_today(logs: list[dict]) -> Optional[float]:
    if not runtime_training_allowed():
        return None
    if len(logs) < MIN_LOGS_FOR_MODEL:
        return None
    today = clock.today()
    weekday = today.weekday()

    X = []
    y = []
    for log in logs:
        wd = log.get("weekday")
        if wd is None:
            try:
                wd = date.fromisoformat(log["date"]).weekday()
            except (KeyError, TypeError, ValueError):
                continue
        X.append([wd, 1 if _is_weekend(log) else 0, log.get("energy") or 3])
        y.append(log["score"])
    if len(X) < MIN_LOGS_FOR_MODEL:
        return None
    model = DecisionTreeRegressor(max_depth=3, random_state=42).fit(X, y)
    recent_energy = logs[0].get("energy") or 3
    return float(model.predict([[weekday, 1 if weekday >= 5 else 0, recent_energy]])[0])


def analyse(
    logs: list[dict],
    focus_records: Optional[list[dict]] = None,
    diary_entries: Optional[list[dict]] = None,
) -> MoodInsight:
    logs = [l for l in logs if l.get("score") is not None]
    count = len(logs)

    if count < MIN_LOGS_FOR_PATTERN:
        remaining = MIN_LOGS_FOR_PATTERN - count
        return MoodInsight(
            ready=False,
            log_count=count,
            headline=f"KALEM masih belajar pola kamu ({count}/{MIN_LOGS_FOR_PATTERN} catatan).",
            details=[
                f"Isi check-in {remaining} hari lagi biar KALEM mulai bisa lihat polanya.",
                "Makin sering kamu cerita, makin akurat pola yang kebaca.",
            ],
        )

    details: list[str] = []
    groups = _weekday_groups(logs)
    averages = {
        day: sum(scores) / len(scores)
        for day, scores in groups.items()
        if len(scores) >= MIN_PER_WEEKDAY
    }

    best_day = hardest_day = None
    if averages:
        best_idx = max(averages, key=lambda d: averages[d])
        worst_idx = min(averages, key=lambda d: averages[d])
        if averages[best_idx] - averages[worst_idx] >= 0.5:
            best_day = DAY_NAMES[best_idx]
            hardest_day = DAY_NAMES[worst_idx]
            details.append(f"Mood kamu cenderung paling bagus hari {best_day}, paling berat hari {hardest_day}.")

    weekday_avg, weekend_avg, n_weekday, n_weekend = _daytype_averages(logs)
    if (
        weekday_avg is not None
        and weekend_avg is not None
        and n_weekday >= MIN_PER_DAYTYPE
        and n_weekend >= MIN_PER_DAYTYPE
    ):
        gap = weekend_avg - weekday_avg
        if gap >= 0.5:
            details.append("Kamu jelas lebih enak pas weekend dibanding hari kerja.")
        elif gap <= -0.5:
            details.append("Menariknya, mood kamu justru lebih stabil pas hari kerja daripada weekend.")
        else:
            details.append("Mood kamu relatif stabil antara hari kerja dan weekend.")

    tag_counter: Counter[str] = Counter()
    diary_entries = diary_entries or []
    diary_dates = {
        entry.get("date") for entry in diary_entries if entry.get("tags")
    }
    for log in logs:
        tag_counter.update(QUICK_TAGS.get(t, t) for t in (log.get("quick_tags") or []))
        if log.get("date") not in diary_dates:
            tag_counter.update(log.get("tags") or [])
    for entry in diary_entries:
        tag_counter.update(entry.get("tags") or [])
    top_tags = [item for item in tag_counter.most_common(3) if item[1] >= MIN_TAG_COUNT]
    if top_tags:
        details.append("Hal yang paling sering muncul di catatan kamu: " + ", ".join(t for t, _ in top_tags) + ".")

    follow_up = recurring_tag_prompt(logs)
    if follow_up:
        details.append(follow_up)

    low_energy_mood = [
        float(log["score"])
        for log in logs
        if isinstance(log.get("energy"), (int, float)) and float(log["energy"]) <= 2
    ]
    higher_energy_mood = [
        float(log["score"])
        for log in logs
        if isinstance(log.get("energy"), (int, float)) and float(log["energy"]) >= 4
    ]
    if len(low_energy_mood) >= 2 and len(higher_energy_mood) >= 2:
        difference = (
            sum(higher_energy_mood) / len(higher_energy_mood)
            - sum(low_energy_mood) / len(low_energy_mood)
        )
        if difference >= 0.5:
            details.append("Mood kamu cenderung lebih rendah saat energi berada di level 1–2.")

    low_energy_focus: list[float] = []
    higher_energy_focus: list[float] = []
    for record in focus_records or []:
        try:
            minutes = float(
                record.get("actual_focus_minutes", record.get("menit", 0)) or 0
            )
            energy = int(record.get("energi", 0) or 0)
        except (TypeError, ValueError):
            continue
        if minutes <= 0:
            continue
        if energy <= 2:
            low_energy_focus.append(minutes)
        elif energy >= 4:
            higher_energy_focus.append(minutes)
    if (
        len(low_energy_focus) >= MIN_FOCUS_PER_ENERGY_GROUP
        and len(higher_energy_focus) >= MIN_FOCUS_PER_ENERGY_GROUP
    ):
        low_average = sum(low_energy_focus) / len(low_energy_focus)
        high_average = sum(higher_energy_focus) / len(higher_energy_focus)
        if high_average - low_average >= 3:
            details.append("Saat energi rendah, sesi fokusmu cenderung lebih pendek.")

    predicted = _predict_today(logs)
    if predicted is not None:
        if predicted <= 2.2:
            details.append("Berdasarkan pola kamu, hari ini kemungkinan agak berat -- pasang target yang ringan aja.")
        elif predicted >= 4:
            details.append("Berdasarkan pola kamu, hari ini biasanya termasuk hari yang cukup oke.")

    avg_all = sum(l["score"] for l in logs) / count
    headline = f"Dari {count} catatan, rata-rata mood kamu {avg_all:.1f}/5."

    if not details:
        details.append("Belum ada pola yang cukup jelas -- catatan kamu masih cukup merata.")

    return MoodInsight(
        ready=True,
        log_count=count,
        headline=headline,
        details=details,
        best_day=best_day,
        hardest_day=hardest_day,
        top_tags=top_tags,
        predicted_score=predicted,
    )
