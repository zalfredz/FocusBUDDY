"""Decision engine tunggal yang memilih respons dan tindakan KALEM."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from app import clock
from app.core.medication_model import check_status, missed_streak

MED_NUDGE_HOUR = 7

ENERGY_BLOCKS = {
    1: (5, 3),
    2: (10, 5),
    3: (15, 5),
    4: (20, 5),
    5: (25, 5),
    6: (30, 8),
}


QUADRANT_PRIORITY = ["lakukan", "delegasikan", "jadwalkan", "nanti"]


@dataclass
class KalemDecision:

    kind: str
    message: str
    mood: str
    detail: str = ""
    action_label: str = ""
    action_kind: str = ""
    task: Optional[dict] = None
    step_text: str = ""
    step_index: int = 0
    focus_minutes: int = 15


@dataclass
class DayState:

    tasks_today: list[dict] = field(default_factory=list)
    mood_logs: list[dict] = field(default_factory=list)
    reset_events: list[dict] = field(default_factory=list)
    medication: Optional[dict] = None
    energy_level: Optional[int] = None
    available_minutes: Optional[int] = None
    all_tasks: list[dict] = field(default_factory=list)
    favorites: dict = field(default_factory=dict)
    focus_records: list[dict] = field(default_factory=list)
    inbox_count: int = 0
    decision_records: list[dict] = field(default_factory=list)


def focus_minutes_for(energy_level: int) -> int:
    focus, _ = ENERGY_BLOCKS.get(energy_level, ENERGY_BLOCKS[3])
    return focus


def break_minutes_for(energy_level: int) -> int:
    _, rest = ENERGY_BLOCKS.get(energy_level, ENERGY_BLOCKS[3])
    return rest


def focus_reason(energy_level: int) -> str:
    if energy_level <= 2:
        return "Disesuaikan karena energi kamu lagi rendah."
    if energy_level >= 5:
        return "Energi kamu lagi bagus, jadi sesinya boleh lebih panjang."
    return "Durasi standar buat energi sedang."


def in_productive_window(profile: dict, now: Optional[datetime] = None) -> Optional[bool]:
    from app import storage

    return storage.in_productive_hours(profile, (now or clock.now()).hour)


def _recent(items: list[dict], days: int, today: Optional[date] = None) -> list[dict]:
    today = today or clock.today()
    out = []
    for item in items:
        try:
            when = date.fromisoformat(item["date"])
        except (KeyError, ValueError):
            continue
        if (today - when).days < days:
            out.append(item)
    return out


def _muat_kapasitas(task: dict, available_minutes: Optional[int]) -> bool:
    if available_minutes is None:
        return True
    from app.core.decision_quality import assess_capacity

    return assess_capacity([task], available_minutes).fits


def urgency_score(task: dict, now: Optional[datetime] = None) -> int:
    from app import storage

    batas = storage.deadline_at(task)
    if batas is None:
        return 0
    now = now or clock.now()
    remaining_minutes = int((batas - now).total_seconds() // 60)
    if remaining_minutes <= 0:
        return 3_000_000 + abs(remaining_minutes)
    if remaining_minutes <= 24 * 60:
        return 2_000_000 - remaining_minutes
    return max(1, 1_000_000 - remaining_minutes)


def pick_next_action(
    tasks: list[dict], available_minutes: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Optional[tuple[dict, int, str]]:
    from app import storage

    pending = [t for t in tasks if not storage.task_is_done(t)]
    if not pending:
        return None

    def sort_key(task: dict):
        quadrant = storage.quadrant_of(task, now=now)
        rank = QUADRANT_PRIORITY.index(quadrant) if quadrant in QUADRANT_PRIORITY else 99
        muat = 0 if _muat_kapasitas(task, available_minutes) else 1
        return (
            rank,
            -urgency_score(task, now=now),
            muat,
            task.get("difficulty_est", 2),
            task.get("created_at", ""),
        )

    pending.sort(key=sort_key)
    chosen = pending[0]

    for i, step in enumerate(chosen.get("steps", [])):
        if not step.get("done"):
            return chosen, i, step.get("text", chosen["title"])

    return chosen, 0, chosen["title"]


def predicted_mood(mood_logs: list[dict], default: str = "tenang") -> str:
    recent = _recent(mood_logs, 3)
    if not recent:
        return default

    scores = [log["score"] for log in recent if log.get("score") is not None]
    if not scores:
        return recent[0].get("mood", default)

    avg = sum(scores) / len(scores)
    if avg <= 1.5:
        return "cemas"
    if avg <= 2.5:
        return "sedih"
    if avg <= 3.5:
        return "lelah"
    if avg <= 4.5:
        return "tenang"
    return "semangat"


def decide(
    profile: dict,
    day: DayState,
    now: Optional[datetime] = None,
) -> KalemDecision:
    now = now or clock.now()
    name = profile.get("name") or "kamu"
    mood = predicted_mood(day.mood_logs)
    energy = day.energy_level or _energy_from_logs(day.mood_logs)
    minutes = focus_minutes_for(energy)

    med_status = check_status(day.medication)
    if med_status.active and med_status.pills_remaining > 0 and now.hour >= MED_NUDGE_HOUR:
        taken_today = (day.medication or {}).get("last_taken") == clock.today().isoformat()
        if not taken_today:
            return KalemDecision(
                kind="med",
                message=f"Udah minum {med_status.name} hari ini?",
                detail="Kalau udah, pencet aja -- stoknya Kalem yang hitung.",
                mood=mood,
                action_label="Udah minum",
                action_kind="med_taken",
                focus_minutes=minutes,
            )

    from app.kalem_ml import fitur as kfitur
    from app.kalem_ml import model_overwhelm

    fitur_sekarang = kfitur.bangun_fitur(now, day=day, profil=profile)
    risiko = model_overwhelm.nilai(fitur_sekarang)
    if risiko.perlu_diringankan:
        return KalemDecision(
            kind="pre_escalate",
            message="Beberapa hari ini kelihatannya berat ya.",
            detail="Nggak harus produktif dulu. Mau berhenti sebentar sama Kalem?",
            mood="cemas",
            action_label="Ambil jeda",
            action_kind="reset",
            focus_minutes=minutes,
        )

    found = pick_next_action(
        day.tasks_today, available_minutes=day.available_minutes, now=now,
    )
    if found:
        task, step_index, step_text = found
        from app.kalem_ml import model_kalem

        engagement = model_kalem.nilai(fitur_sekarang, records=day.decision_records)
        if engagement.perlu_diringankan:
            minutes = max(5, minutes - 5)
        gentle = in_productive_window(profile, now) is False
        message = (
            "Kalau lagi nggak di jam terbaik kamu, satu langkah kecil aja udah cukup."
            if gentle
            else "Satu hal ini dulu aja."
        )
        return KalemDecision(
            kind="next_action",
            message=message,
            detail=task["title"],
            mood=mood,
            action_label=f"FOKUS {minutes} menit",
            action_kind="focus",
            task=task,
            step_text=step_text,
            step_index=step_index,
            focus_minutes=minutes,
        )

    return KalemDecision(
        kind="calm",
        message=f"Nggak ada tugas hari ini, {name}. Nikmati aja.",
        detail="Istirahat juga termasuk progress.",
        mood=mood,
        action_label="Tambah tugas",
        action_kind="add_task",
        focus_minutes=minutes,
    )


def _energy_from_logs(mood_logs: list[dict]) -> int:
    today_iso = clock.today().isoformat()
    for log in mood_logs:
        if log.get("date") == today_iso and log.get("energy"):
            return int(log["energy"])
    if mood_logs and mood_logs[0].get("energy"):
        return int(mood_logs[0]["energy"])
    return 3


def snapshot() -> tuple[dict, DayState]:
    from app import storage

    profile = storage.get_profile()
    day = DayState(
        tasks_today=storage.tasks_actionable_today(),
        mood_logs=storage.get_mood_logs(),
        reset_events=storage.get_reset_events(),
        medication=storage.get_medication(),
        all_tasks=storage.get_tasks(),
        favorites=storage.get_favorites(),
        focus_records=storage.get_focus_records(),
        inbox_count=len(storage.get_inbox()),
        decision_records=storage.get_decision_records(),
        energy_level=storage.today_energy(),
    )
    return profile, day


@dataclass
class MorningBrief:
    ready: bool
    greeting: str
    forecast: str
    plan: str
    mood: str
    energy_level: int
    focus_minutes: int
    reasons: list[str] = field(default_factory=list)
    task_count: int = 0
    burnout_risk: bool = False
    encouragement: str = ""
    long_pattern: str = ""


def build_morning_brief(
    profile: dict,
    day: DayState,
    now: Optional[datetime] = None,
) -> MorningBrief:
    from app import storage
    from app.core.energy_predictor import MISSED_MED_THRESHOLD
    from app.kalem_ml import fitur as kfitur
    from app.kalem_ml import model_energi, model_mood

    now = now or clock.now()
    name = profile.get("name") or "kamu"
    logs = [log for log in day.mood_logs if log.get("score") is not None]
    encouragement = day.favorites.get("penyemangat", "").strip()

    hour = now.hour
    if hour < 11:
        greeting = f"Pagi, {name}!"
    elif hour < 15:
        greeting = f"Siang, {name}!"
    elif hour < 19:
        greeting = f"Sore, {name}!"
    else:
        greeting = f"Malam, {name}!"

    task_count = len([t for t in day.tasks_today if not _task_done(t)])

    f = kfitur.bangun_fitur(now, day=day, profil=profile)
    ramalan = model_mood.ramal(f)

    if f["data_mood_basi"]:
        jarak = int(f["hari_sejak_checkin"])
        return MorningBrief(
            ready=False,
            greeting=greeting,
            forecast=f"Udah {jarak} hari nggak ketemu. Seneng kamu balik lagi.",
            plan=(
                "Aku sengaja nggak nebak-nebak hari kamu dari catatan lama — "
                "itu udah lewat. Check-in bentar yuk, biar aku mulai dari "
                "kondisi kamu yang sekarang."
            ),
            mood="tenang",
            energy_level=3,
            focus_minutes=focus_minutes_for(3),
            reasons=[],
            task_count=task_count,
            encouragement=encouragement,
        )

    if not ramalan.siap:
        return MorningBrief(
            ready=False,
            greeting=greeting,
            forecast=(
                f"Kalem belum cukup data buat meramal hari kamu "
                f"({ramalan.n_data}/{model_mood.MIN_POLA} catatan)."
            ),
            plan=(
                "Cerita dikit di check-in hari ini biar makin kebaca ke depannya. "
                "Sementara ini aku pakai setelan tengah dulu."
            ),
            mood="tenang",
            energy_level=3,
            focus_minutes=focus_minutes_for(3),
            reasons=[],
            task_count=task_count,
            encouragement=encouragement,
        )

    predicted_score = ramalan.skor
    saran = model_energi.nilai(f, skor_mood=predicted_score)

    energy_level = saran.level_energi
    tired_now = bool(f["di_jam_capek"])

    reasons: list[str] = []
    weekday_name = _WEEKDAY_NAMES[clock.today().weekday()]
    if predicted_score <= 2.5:
        reasons.append(f"{weekday_name} biasanya berat buat kamu")
    elif predicted_score >= 4:
        reasons.append(f"{weekday_name} biasanya lumayan buat kamu")
    if f["tidur_jam"] < 5.5:
        reasons.append("pola tidur kamu lagi berantakan")
    if f["streak_abai"] >= 2:
        reasons.append(f"{int(f['streak_abai'])} hari terakhir makan/istirahat kelewat")
    if f["energi_terakhir"] <= 2:
        reasons.append("energi terakhir kamu rendah")
    if tired_now:
        reasons.append("ini jam yang kamu bilang biasanya paling capek")
    if f["obat_kelewat"] >= MISSED_MED_THRESHOLD:
        reasons.append(f"obat kamu belum keabsen {int(f['obat_kelewat'])} hari terakhir")

    if saran.label == "rendah" or saran.burnout:
        forecast = "Hari ini kemungkinan bakal berat."
        mood = "lelah"
    elif saran.label == "tinggi":
        forecast = "Hari ini kemungkinan lagi enak-enaknya."
        mood = "semangat"
    else:
        forecast = "Hari ini kemungkinan biasa aja."
        mood = "tenang"

    minutes = focus_minutes_for(energy_level)
    if energy_level <= 2:
        plan = (
            f"Aku udah susunin: ambil yang paling ringan aja, sesi fokus {minutes} menit."
        )
    elif energy_level >= 5:
        plan = (
            f"Boleh ambil yang agak berat hari ini, sesi fokus {minutes} menit."
        )
    else:
        plan = f"Aku setel sesi fokus {minutes} menit dulu -- santai tapi jalan."

    if in_productive_window(profile, now) is False:
        plan += " Ini juga lagi di luar jam terbaik kamu, jadi santai aja."

    return MorningBrief(
        ready=True,
        greeting=greeting,
        forecast=forecast,
        plan=plan,
        mood=mood,
        energy_level=energy_level,
        focus_minutes=minutes,
        reasons=reasons,
        task_count=task_count,
        burnout_risk=saran.burnout,
        encouragement=encouragement,
        long_pattern=long_range_pattern(logs) if storage.is_premium() else "",
    )


_WEEKDAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

LONG_PATTERN_MIN_WEEKS = 3


def long_range_pattern(logs: list[dict], today: Optional[date] = None) -> str:
    today = today or clock.today()
    weekday = today.weekday()

    same_day = []
    for log in logs:
        if log.get("score") is None:
            continue
        try:
            when = date.fromisoformat(log["date"])
        except (KeyError, ValueError):
            continue
        if when.weekday() == weekday and when != today:
            same_day.append((when, log["score"]))

    if len(same_day) < LONG_PATTERN_MIN_WEEKS:
        return ""

    same_day.sort(key=lambda pair: pair[0], reverse=True)
    recent = same_day[:4]
    scores = [s for _, s in recent]
    name = _WEEKDAY_NAMES[weekday]

    others = [
        log["score"]
        for log in logs
        if log.get("score") is not None
        and date.fromisoformat(log["date"]).weekday() != weekday
    ]
    if not others:
        return ""

    avg_day = sum(scores) / len(scores)
    avg_other = sum(others) / len(others)
    gap = avg_day - avg_other

    if gap <= -0.8:
        return (
            f"{len(recent)} {name} terakhir mood kamu konsisten lebih rendah "
            f"({avg_day:.1f} vs {avg_other:.1f} di hari lain). Kalau ada yang "
            f"bisa digeser dari {name}, mungkin worth dicoba."
        )
    if gap >= 0.8:
        return (
            f"{len(recent)} {name} terakhir mood kamu konsisten lebih bagus "
            f"({avg_day:.1f} vs {avg_other:.1f}). Hari yang pas buat naruh "
            "yang berat-berat."
        )
    return (
        f"Dari {len(recent)} {name} terakhir, mood kamu di hari ini relatif "
        "stabil — nggak ada pola khusus yang kebaca."
    )


def _task_done(task: dict) -> bool:
    from app import storage

    return storage.task_is_done(task)


def morning_brief_now() -> MorningBrief:
    profile, day = snapshot()
    return build_morning_brief(profile, day)
