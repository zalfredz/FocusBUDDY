"""Persistensi cache per sesi dan state Supabase per pengguna."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from app import clock, data_provenance, session_scope

DATA_DIR = Path.home() / ".focusbuddy"
DATA_FILE = DATA_DIR / "data.json"
BACKUP_FILE = DATA_DIR / "data.json.bak"
SCHEMA_VERSION = 3
FOCUS_OUTCOME_SCHEMA_VERSION = "focus-outcome-v1"
MAX_FOCUS_OUTCOME_RECORDS = 2_000

_CLOUD_SAVE_HOOK: Optional[Callable[[dict[str, Any]], None]] = None
_SESSION_STORAGE_KEY = "focusbuddy.storage.v1"
_CURRENT_USER_ID = ""


@dataclass
class _StorageBinding:
    user_id: str
    data_dir: Path
    data_file: Path
    backup_file: Path
    cloud_save_hook: Optional[Callable[[dict[str, Any]], None]] = None


def _session_binding() -> Optional[_StorageBinding]:
    store = session_scope.current_store()
    if store is None:
        return None
    value = store.get(_SESSION_STORAGE_KEY)
    return value if isinstance(value, _StorageBinding) else None


def _paths() -> tuple[Path, Path, Path]:
    binding = _session_binding()
    if binding is not None:
        return binding.data_dir, binding.data_file, binding.backup_file
    return DATA_DIR, DATA_FILE, BACKUP_FILE


def current_data_file() -> Path:
    return _paths()[1]


def configure_user_storage(user_id: str, cache_root: Optional[Path] = None) -> None:
    global DATA_DIR, DATA_FILE, BACKUP_FILE, _CURRENT_USER_ID
    safe_id = "".join(c for c in str(user_id) if c.isalnum() or c in "-_")
    if not safe_id:
        raise ValueError("user_id tidak valid")
    session_id = "".join(
        c for c in session_scope.current_session_id() if c.isalnum() or c in "-_"
    )
    if session_id:
        root = cache_root or Path(
            os.getenv(
                "FOCUSBUDDY_CACHE_DIR",
                str(Path(tempfile.gettempdir()) / "focusbuddy-web-cache"),
            )
        )
        data_dir = root / safe_id / session_id
        session_scope.set_value(
            _SESSION_STORAGE_KEY,
            _StorageBinding(
                user_id=safe_id,
                data_dir=data_dir,
                data_file=data_dir / "data.json",
                backup_file=data_dir / "data.json.bak",
            ),
        )
        return

    _CURRENT_USER_ID = safe_id
    DATA_DIR = Path.home() / ".focusbuddy" / "users" / safe_id
    DATA_FILE = DATA_DIR / "data.json"
    BACKUP_FILE = DATA_DIR / "data.json.bak"


def set_cloud_save_hook(hook: Optional[Callable[[dict[str, Any]], None]]) -> None:
    global _CLOUD_SAVE_HOOK
    binding = _session_binding()
    if binding is not None:
        binding.cloud_save_hook = hook
        return
    _CLOUD_SAVE_HOOK = hook


def clear_user_storage() -> None:
    global _CURRENT_USER_ID
    session_scope.remove_value(_SESSION_STORAGE_KEY)
    _CURRENT_USER_ID = ""


def current_user_id() -> str:
    binding = _session_binding()
    return binding.user_id if binding is not None else _CURRENT_USER_ID


def get_duration_personalization() -> dict[str, Any]:
    payload = load_state().get("ml_personalization", {}).get("duration", {})
    return dict(payload) if isinstance(payload, dict) else {}


def _cloud_save_hook() -> Optional[Callable[[dict[str, Any]], None]]:
    binding = _session_binding()
    return binding.cloud_save_hook if binding is not None else _CLOUD_SAVE_HOOK

STATUS_OPTIONS = {
    "mahasiswa": "Mahasiswa / pelajar",
    "kerja": "Kerja kantoran",
    "freelance": "Freelance / remote",
    "lainnya": "Lainnya",
}

PRODUCTIVE_TIME_OPTIONS = {
    "pagi": "Pagi",
    "siang": "Siang",
    "sore": "Sore",
    "malam": "Malam",
    "nggak_tentu": "Tidak tentu",
}

PRODUCTIVE_PRESETS: dict[str, Optional[tuple[int, int]]] = {
    "pagi": (6, 11),
    "siang": (11, 16),
    "sore": (16, 19),
    "malam": (19, 24),
    "nggak_tentu": None,
}

HOUR_MIN, HOUR_MAX = 0, 30

SLEEP_OPTIONS = {
    "cukup": "Cukup teratur",
    "begadang": "Sering begadang",
    "susah_tidur": "Susah tidur (insomnia)",
    "berantakan": "Berantakan banget",
}

MAX_TRIGGERS = 4

MAX_STATUS = 3

MEDICATION_OPTIONS = {
    "ya": "Ada, rutin",
    "tidak": "Nggak ada",
    "kadang": "Kadang-kadang aja",
}

TRIGGER_OPTIONS = {
    "tugas_numpuk": "Tugas numpuk",
    "deadline": "Deadline mepet",
    "mulai_susah": "Susah mulai sesuatu",
    "gagal_fokus": "Gampang terdistraksi",
    "kurang_tidur": "Kurang tidur",
    "sosial": "Interaksi sosial",
}

FAVORITE_FIELDS = {
    "musik": "Musik / genre yang nenangin",
    "suara_alam": "Suara alam / background yang membantu fokus",
    "snack": "Comfort food / minuman favorit",
    "kondisi_ruangan": "Kondisi ruangan yang bikin fokus",
    "tempat_fokus": "Tempat tertentu yang membantu fokus",
    "fokus_lainnya": "Hal lain yang membantu fokus",
    "hobi": "Hobi santai kamu",
    "tempat": "Tempat yang bikin nyaman",
    "penyemangat": "Kalimat penyemangat versi kamu sendiri",
    "warna": "Warna favorit",
    "orang": "Orang yang biasa jadi tempat cerita",
    "gerak": "Gerak / olahraga ringan favorit",
    "overwhelm_lainnya": "Hal lain yang membantu saat overwhelmed",
    "preferensi_kerja": "Cara kerja yang paling nyaman",
    "preferensi_lainnya": "Preferensi kerja lainnya",
    "kembali_fokus": "Hal yang biasanya bikin kamu kembali fokus",
    "rasa_aman": "Hal yang biasanya bikin kamu merasa aman / nyaman",
    "jam_capek": "Jam kamu biasanya paling capek",
}

FAVORITE_WORK_STYLES = {
    "sendiri": "Sendiri",
    "ditemani": "Ditemani",
    "tenang": "Tempat tenang",
    "background": "Ada suara / background",
    "lainnya": "Lainnya",
}

FAVORITE_COLORS = {
    "sage": ("Hijau sage", "#8FBCA0"),
    "biru": ("Biru langit", "#A9C6DE"),
    "peach": ("Peach", "#F3B88B"),
    "lavender": ("Lavender", "#B8AEDB"),
    "terracotta": ("Terracotta", "#D97B66"),
}

FAVORITE_TIRED_HOURS = {
    "pagi": ("Pagi (06-11)", (6, 11)),
    "siang": ("Siang (11-16)", (11, 16)),
    "sore": ("Sore (16-19)", (16, 19)),
    "malam": ("Malam (19-24)", (19, 24)),
}


def _default_profile() -> dict[str, Any]:
    return {
        "name": "",
        "onboarded": False,
        "age_range": "",
        "status": [],
        "productive_time": "",
        "productive_hours": [],
        "sleep_condition": "",
        "on_medication": "",
        "overwhelm_triggers": [],
        "custom_triggers": [],
        "skipped_detail": False,
    }


def _default_state() -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "profile": _default_profile(),
        "favorites": {key: "" for key in FAVORITE_FIELDS},
        "tasks": [],
        "mood_logs": [],
        "diary_records": [],
        "reset_events": [],
        "medication": None,
        "inbox": [],
        "last_brief_date": "",
        "today_energy": {"date": "", "level": 0},
        "subscription": {"is_premium": False},
        "usage": {"date": ""},
        "focus_records": [],
        "ml_outcome_records": [],
        "ml_personalization": {"duration": {}},
        "decompose_records": [],
        "decision_records": [],
        "last_open_date": "",
        "dev": {"day_offset": 0, "hour_offset": 0},
    }


def _migrate(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("schema") == SCHEMA_VERSION:
        return state

    fresh = _default_state()

    old_profile = state.get("profile", {})
    fresh["profile"]["name"] = old_profile.get("name", "")
    fresh["profile"]["onboarded"] = old_profile.get("onboarded", False)
    for key in ("age_range", "status", "productive_time", "productive_hours",
                "sleep_condition", "on_medication", "custom_triggers", "skipped_detail"):
        if key in old_profile:
            fresh["profile"][key] = old_profile[key]
    fresh["profile"]["overwhelm_triggers"] = old_profile.get("overwhelm_triggers", [])

    fresh["favorites"].update(state.get("favorites", {}))

    for old_task in state.get("tasks", []):
        fresh["tasks"].append(
            {
                "id": old_task.get("id", str(uuid.uuid4())),
                "title": old_task.get("title", "Tugas"),
                "scheduled_date": old_task.get(
                    "scheduled_date", old_task.get("deadline", clock.today().isoformat())
                ),
                "deadline": old_task.get("deadline", clock.today().isoformat()),
                "deadline_time": old_task.get("deadline_time", ""),
                "important": old_task.get("important", True),
                "difficulty_est": old_task.get("difficulty_est", 2),
                "steps": old_task.get("steps", []),
                "created_at": old_task.get("created_at", clock.now().isoformat()),
            }
        )

    for old_log in state.get("mood_logs", []):
        fresh["mood_logs"].append(
            {
                "date": old_log.get("date", clock.today().isoformat()),
                "mood": old_log.get("mood", "tenang"),
                "score": old_log.get("score", 4),
                "energy": old_log.get("energy", old_log.get("focus", 3)),
                "diary": old_log.get("diary", ""),
                "tags": old_log.get("tags", []),
                "quick_tags": old_log.get("quick_tags", []),
                "ate_today": old_log.get("ate_today"),
                "rested_enough": old_log.get("rested_enough"),
                "weekday": old_log.get("weekday"),
                "is_weekend": old_log.get("is_weekend"),
            }
        )

    fresh["reset_events"] = state.get("reset_events", [])
    fresh["diary_records"] = state.get("diary_records", [])
    fresh["inbox"] = state.get("inbox", [])
    fresh["last_brief_date"] = state.get("last_brief_date", "")
    fresh["today_energy"] = state.get("today_energy", {"date": "", "level": 0})
    fresh["dev"] = state.get("dev", {"day_offset": 0, "hour_offset": 0})

    med = state.get("medication")
    if med:
        med.setdefault("take_log", [])
        med.setdefault("last_taken", "")
        fresh["medication"] = med

    return fresh


def _normalise_profile(profile: dict[str, Any]) -> bool:
    changed = False

    status = profile.get("status")
    if isinstance(status, str):
        profile["status"] = [status] if status else []
        changed = True
    elif not isinstance(status, list):
        profile["status"] = []
        changed = True

    hours = profile.get("productive_hours")
    if not isinstance(hours, list):
        hours = []
        changed = True
    if not hours:
        preset = PRODUCTIVE_PRESETS.get(profile.get("productive_time", ""))
        if preset:
            hours = [[preset[0], preset[1]]]
            changed = True
    clean: list[list[int]] = []
    for entry in hours:
        try:
            start, end = int(entry[0]), int(entry[1])
        except (TypeError, ValueError, IndexError, KeyError):
            changed = True
            continue
        if HOUR_MIN <= start < end <= HOUR_MAX:
            clean.append([start, end])
        else:
            changed = True
    if clean != hours:
        changed = True
    profile["productive_hours"] = clean

    if not isinstance(profile.get("custom_triggers"), list):
        profile["custom_triggers"] = []
        changed = True
    if not isinstance(profile.get("overwhelm_triggers"), list):
        profile["overwhelm_triggers"] = []
        changed = True

    return changed


def all_triggers(profile: Optional[dict] = None) -> list[str]:
    profile = profile if profile is not None else get_profile()
    return list(profile.get("overwhelm_triggers", [])) + list(profile.get("custom_triggers", []))


def in_productive_hours(profile: Optional[dict] = None, hour: Optional[int] = None) -> Optional[bool]:
    profile = profile if profile is not None else get_profile()
    ranges = profile.get("productive_hours") or []
    if not ranges:
        return None
    hour = clock.now().hour if hour is None else hour
    for start, end in ranges:
        if start <= hour < end or start <= hour + 24 < end:
            return True
    return False


def fmt_hour(hour: int) -> str:
    return f"{hour % 24:02d}:00"


def fmt_range(start: int, end: int) -> str:
    tail = " besok" if end > 24 else ""
    return f"{fmt_hour(start)} – {fmt_hour(end)}{tail}"


def set_productive_hours(ranges: list[list[int]]) -> None:
    state = load_state()
    state["profile"]["productive_hours"] = [[int(a), int(b)] for a, b in ranges]
    state["profile"]["productive_time"] = ""
    save_state(state)


def load_state() -> dict[str, Any]:
    data_dir, data_file, backup_file = _paths()
    data_dir.mkdir(parents=True, exist_ok=True)
    if not data_file.exists():
        state = _default_state()
        save_state(state)
        return state
    recovered_from_backup = False
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        try:
            with open(backup_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            recovered_from_backup = True
        except (json.JSONDecodeError, OSError):
            return _default_state()

    if not isinstance(state, dict):
        state = _default_state()
        recovered_from_backup = True

    migrated = _migrate(state)
    changed = migrated is not state or recovered_from_backup
    for key, value in _default_state().items():
        if key not in migrated:
            migrated[key] = deepcopy(value)
            changed = True

    for key in (
        "profile", "favorites", "today_energy", "subscription", "usage", "dev",
        "ml_personalization",
    ):
        if not isinstance(migrated.get(key), dict):
            migrated[key] = deepcopy(_default_state()[key])
            changed = True
    personalization = migrated["ml_personalization"]
    if not isinstance(personalization.get("duration"), dict):
        personalization["duration"] = {}
        changed = True
    for key in (
        "tasks", "mood_logs", "diary_records", "reset_events", "inbox", "focus_records",
        "ml_outcome_records", "decompose_records", "decision_records",
    ):
        if not isinstance(migrated.get(key), list):
            migrated[key] = []
            changed = True

    for task in migrated["tasks"]:
        if not isinstance(task, dict):
            continue
        if "scheduled_date" not in task:
            task["scheduled_date"] = task.get("deadline", "")
            changed = True
        if task.get("item_type") not in {"task", "schedule"}:
            task["item_type"] = (
                "schedule" if task.get("repeat", "none") == "weekly" else "task"
            )
            changed = True
        if "repeat_end_date" not in task:
            task["repeat_end_date"] = ""
            changed = True
        if task.get("data_provenance") not in data_provenance.ALLOWED:
            task["data_provenance"] = data_provenance.task_provenance(task)
            changed = True

    decision_defaults = {
        "outcome": "",
        "outcome_at": "",
        "actual_focus_minutes": None,
        "planned_focus_minutes": None,
    }
    for record in migrated["decision_records"]:
        if not isinstance(record, dict):
            continue
        for key, value in decision_defaults.items():
            if key not in record:
                record[key] = value
                changed = True

    favorites = migrated.setdefault("favorites", {})
    for key in FAVORITE_FIELDS:
        if key not in favorites:
            favorites[key] = ""
            changed = True

    profile = migrated.setdefault("profile", _default_profile())
    for key, value in _default_profile().items():
        if key not in profile:
            profile[key] = value
            changed = True
    if _normalise_profile(profile):
        changed = True
    for task in migrated.get("tasks", []):
        if not isinstance(task, dict):
            continue
        for step in task.get("steps", []):
            if isinstance(step, dict) and not step.get("id"):
                step["id"] = str(uuid.uuid4())
                changed = True
        occurrences = task.get("occurrences", {})
        if not isinstance(occurrences, dict):
            task["occurrences"] = {}
            changed = True
            continue
        for steps in occurrences.values():
            if not isinstance(steps, list):
                continue
            for step in steps:
                if isinstance(step, dict) and not step.get("id"):
                    step["id"] = str(uuid.uuid4())
                    changed = True
    if changed:
        save_state(migrated)
    dev = migrated.get("dev", {})
    clock.set_offset(dev.get("day_offset", 0))
    clock.set_hour_offset(dev.get("hour_offset", 0))
    return migrated


def save_state(state: dict[str, Any]) -> None:
    data_dir, data_file, backup_file = _paths()
    data_dir.mkdir(parents=True, exist_ok=True)
    temporary = data_file.with_suffix(".json.tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False, default=str)
        f.flush()
        os.fsync(f.fileno())
    if data_file.exists():
        try:
            with open(data_file, "r", encoding="utf-8") as current:
                valid_primary = isinstance(json.load(current), dict)
            if valid_primary:
                shutil.copy2(data_file, backup_file)
        except (json.JSONDecodeError, OSError):
            pass
    os.replace(temporary, data_file)
    hook = _cloud_save_hook()
    if hook is not None:
        try:
            hook(deepcopy(state))
        except Exception:
            pass


def reset_all_data() -> dict[str, Any]:
    state = _default_state()
    save_state(state)
    clock.reset_offset()
    try:
        import models as kalem_models

        kalem_models.reset_semua()
    except Exception:
        pass
    return state


def needs_morning_brief() -> bool:
    state = load_state()
    if not state["profile"].get("onboarded"):
        return False
    return state.get("last_brief_date", "") != clock.today().isoformat()


def ready_for_morning_brief() -> bool:
    """Morning Brief menjadi pembuka hari sebelum check-in aktual."""
    return needs_morning_brief()


def set_last_brief_date() -> None:
    state = load_state()
    state["last_brief_date"] = clock.today().isoformat()
    save_state(state)


STALE_AFTER_DAYS = 3


def touch_last_open() -> int:
    state = load_state()
    hari_ini = clock.today()
    terakhir = state.get("last_open_date") or ""
    state["last_open_date"] = hari_ini.isoformat()
    save_state(state)

    try:
        return max(0, (hari_ini - date.fromisoformat(terakhir)).days)
    except (TypeError, ValueError):
        return 0


def hari_sejak_checkin(logs: Optional[list[dict]] = None) -> Optional[int]:
    logs = get_mood_logs() if logs is None else logs
    hari_ini = clock.today()
    tanggal = []
    for log in logs:
        try:
            d = date.fromisoformat(log.get("date", ""))
        except (TypeError, ValueError):
            continue
        if d <= hari_ini:
            tanggal.append(d)
    if not tanggal:
        return None
    return (hari_ini - max(tanggal)).days


def data_mood_basi(logs: Optional[list[dict]] = None) -> bool:
    jarak = hari_sejak_checkin(logs)
    return jarak is not None and jarak > STALE_AFTER_DAYS


MEAL_ASK_HOUR = 18


def waktunya_tanya_makan(now: Optional[Any] = None) -> bool:
    return (now or clock.now()).hour >= MEAL_ASK_HOUR


def sudah_jawab_makan() -> bool:
    log = today_mood()
    return bool(log) and log.get("ate_today") is not None


def perlu_tanya_makan() -> bool:
    return waktunya_tanya_makan() and today_mood() is not None and not sudah_jawab_makan()


FREE_LIMITS = {
    "decompose": 3,
    "reco_cards": 1,
}


def is_premium() -> bool:
    return bool(load_state().get("subscription", {}).get("is_premium", False))


def set_premium(value: bool) -> None:
    state = load_state()
    state.setdefault("subscription", {})["is_premium"] = bool(value)
    save_state(state)


def _usage_bucket(state: dict[str, Any]) -> dict[str, Any]:
    usage = state.setdefault("usage", {"date": ""})
    today = clock.today().isoformat()
    if usage.get("date") != today:
        usage.clear()
        usage["date"] = today
    return usage


def usage_count(feature: str) -> int:
    return int(_usage_bucket(load_state()).get(feature, 0))


def quota_left(feature: str) -> Optional[int]:
    if is_premium():
        return None
    limit = FREE_LIMITS.get(feature)
    if limit is None:
        return None
    return max(0, limit - usage_count(feature))


def can_use(feature: str) -> bool:
    left = quota_left(feature)
    return left is None or left > 0


def record_usage(feature: str) -> int:
    if is_premium():
        return 0
    state = load_state()
    usage = _usage_bucket(state)
    usage[feature] = int(usage.get(feature, 0)) + 1
    save_state(state)
    return usage[feature]


def reco_cards_seen_this_week() -> int:
    entry = load_state().get("usage_week", {})
    week = clock.today().isocalendar()
    key = f"{week[0]}-W{week[1]}"
    return int(entry.get(key, 0))


def record_reco_card() -> None:
    if is_premium():
        return
    state = load_state()
    week = clock.today().isocalendar()
    key = f"{week[0]}-W{week[1]}"
    state["usage_week"] = {key: int(state.get("usage_week", {}).get(key, 0)) + 1}
    save_state(state)


def can_see_reco_card() -> bool:
    return is_premium() or reco_cards_seen_this_week() < FREE_LIMITS["reco_cards"]


def set_today_energy(level: int) -> None:
    state = load_state()
    state["today_energy"] = {"date": clock.today().isoformat(), "level": int(level)}
    save_state(state)


def today_energy() -> Optional[int]:
    entry = load_state().get("today_energy") or {}
    if entry.get("date") == clock.today().isoformat():
        return entry.get("level")
    return None


def advance_day(days: int = 1) -> int:
    state = load_state()
    dev = state.setdefault("dev", {"day_offset": 0})
    dev["day_offset"] = dev.get("day_offset", 0) + days
    save_state(state)
    clock.set_offset(dev["day_offset"])
    return dev["day_offset"]


def day_offset() -> int:
    return load_state().get("dev", {}).get("day_offset", 0)


def jump_to_hour(target_hour: int) -> int:
    state = load_state()
    dev = state.setdefault("dev", {"day_offset": 0, "hour_offset": 0})
    dev["hour_offset"] = dev.get("hour_offset", 0) + clock.hours_until(target_hour)
    save_state(state)
    clock.set_hour_offset(dev["hour_offset"])
    return dev["hour_offset"]


def hour_offset() -> int:
    return load_state().get("dev", {}).get("hour_offset", 0)


def clear_hour_offset() -> None:
    effective_day = clock.today()
    state = load_state()
    dev = state.setdefault("dev", {})
    dev["hour_offset"] = 0
    clock.set_hour_offset(0)
    day_adjustment = (effective_day - clock.today()).days
    if day_adjustment:
        dev["day_offset"] = int(dev.get("day_offset", 0)) + day_adjustment
        clock.set_offset(dev["day_offset"])
    save_state(state)


def clear_last_brief_date() -> None:
    state = load_state()
    state["last_brief_date"] = ""
    save_state(state)


def clear_day_offset() -> None:
    state = load_state()
    dev = state.setdefault("dev", {})
    dev["day_offset"] = 0
    dev["hour_offset"] = 0
    save_state(state)
    clock.reset_offset()


def get_profile() -> dict:
    return load_state()["profile"]


def save_profile(answers: dict[str, Any]) -> dict:
    state = load_state()
    profile = state["profile"]
    for key, value in answers.items():
        if key in profile:
            profile[key] = value
    if "productive_hours" in answers:
        profile["productive_time"] = ""
    profile["onboarded"] = True
    _normalise_profile(profile)
    save_state(state)
    return profile


def display_name() -> str:
    return get_profile().get("name") or "Teman"


def get_favorites() -> dict[str, str]:
    return load_state().get("favorites", {})


def set_favorite(key: str, value: str) -> None:
    state = load_state()
    state.setdefault("favorites", {})[key] = value.strip()
    save_state(state)


def favorites_filled() -> int:
    return sum(1 for v in get_favorites().values() if v)


def favorite_color_hex() -> Optional[str]:
    entry = FAVORITE_COLORS.get(get_favorites().get("warna", ""))
    return entry[1] if entry else None


def in_tired_window(now: Optional[Any] = None) -> bool:
    entry = FAVORITE_TIRED_HOURS.get(get_favorites().get("jam_capek", ""))
    if not entry:
        return False
    start, end = entry[1]
    hour = (now or clock.now()).hour
    return start <= hour < end


URGENT_WITHIN_HOURS = 24


def deadline_at(task: dict) -> Optional[datetime]:
    try:
        d = date.fromisoformat(task.get("deadline", ""))
    except (TypeError, ValueError):
        return None

    jam = (task.get("deadline_time") or "").strip()
    if jam:
        try:
            h, m = (int(x) for x in jam.split(":")[:2])
        except (ValueError, TypeError):
            h, m = 23, 59
    else:
        h, m = 23, 59
    return datetime(d.year, d.month, d.day, min(h, 23), min(m, 59))


def is_urgent(task: dict, now: Optional[Any] = None) -> bool:
    now = now or clock.now()
    batas = deadline_at(task)
    if batas is None:
        return False
    sisa_jam = (batas - now).total_seconds() / 3600
    return sisa_jam <= URGENT_WITHIN_HOURS


def add_task(
    title: str,
    deadline: str,
    important: bool = True,
    steps: Optional[list[dict]] = None,
    difficulty_est: int = 2,
    kategori: str = "",
    jumlah_unit: float = 0,
    menit_est: int = 0,
    deadline_time: str = "",
    description: str = "",
    repeat: str = "none",
    custom_steps: Optional[list[str]] = None,
    scheduled_date: Optional[str] = None,
    item_type: Optional[str] = None,
    repeat_end_date: str = "",
    prediction_model_version: str = "",
    prediction_source: str = "",
    prediction_importance: Optional[float] = None,
    prediction_deadline_days: Optional[float] = None,
    prediction_global_minutes: Optional[int] = None,
    prediction_global_model_version: str = "",
    prediction_global_dataset_version: str = "",
    prediction_global_artifact_sha256: str = "",
    prediction_personalization_version: str = "",
    prediction_personalization_dataset_version: str = "",
    data_provenance_value: str = data_provenance.REAL_USER,
) -> dict:
    state = load_state()
    repeat = repeat if repeat in {"none", "daily", "weekly", "monthly"} else "none"
    if item_type not in {"task", "schedule"}:
        item_type = "schedule" if repeat == "weekly" else "task"
    start_value = scheduled_date if scheduled_date is not None else deadline
    if repeat == "none":
        repeat_end_date = ""
    else:
        try:
            start_date = date.fromisoformat(start_value or clock.today().isoformat())
            end_date = date.fromisoformat((repeat_end_date or "").strip())
            repeat_end_date = end_date.isoformat() if end_date >= start_date else ""
        except (TypeError, ValueError):
            repeat_end_date = ""
    if data_provenance_value not in data_provenance.ALLOWED:
        raise ValueError("data_provenance task tidak valid")
    task = {
        "id": str(uuid.uuid4()),
        "title": title,
        "scheduled_date": (
            scheduled_date
            if scheduled_date is not None
            else (deadline or clock.today().isoformat())
        ),
        "deadline": deadline,
        "deadline_time": deadline_time,
        "important": important,
        "difficulty_est": difficulty_est,
        "kategori": kategori,
        "jumlah_unit": float(jumlah_unit),
        "menit_est": int(menit_est),
        "duration_prediction": {
            "estimated_duration_minutes": int(menit_est),
            "model_version": str(prediction_model_version or ""),
            "source": str(prediction_source or ""),
            "global_prediction_minutes": int(
                prediction_global_minutes
                if prediction_global_minutes is not None
                else menit_est
            ),
            "global_model_version": str(
                prediction_global_model_version or prediction_model_version or ""
            ),
            "global_dataset_version": str(prediction_global_dataset_version or ""),
            "global_artifact_sha256": str(prediction_global_artifact_sha256 or ""),
            "personalization_version": str(prediction_personalization_version or ""),
            "personalization_dataset_version": str(
                prediction_personalization_dataset_version or ""
            ),
            "importance": prediction_importance,
            "deadline_days": prediction_deadline_days,
            "predicted_at": clock.now().isoformat(),
        } if int(menit_est) > 0 else {},
        "data_provenance": data_provenance_value,
        "description": description,
        "custom_steps": [str(step).strip() for step in (custom_steps or []) if str(step).strip()],
        "repeat": repeat,
        "repeat_end_date": repeat_end_date,
        "item_type": item_type,
        "occurrences": {},
        "steps": [
            {**step, "id": step.get("id") or str(uuid.uuid4())}
            for step in (steps or [])
        ],
        "created_at": clock.now().isoformat(),
    }
    state["tasks"].append(task)
    save_state(state)
    return task


def get_tasks() -> list[dict]:
    return load_state()["tasks"]


def tasks_for(day: str) -> list[dict]:
    try:
        target = date.fromisoformat(day)
    except (TypeError, ValueError):
        return []

    tampil: list[dict] = []
    for task in get_tasks():
        anchor = (task.get("scheduled_date") or task.get("deadline") or "").strip()
        if not anchor:
            anchor = clock.today().isoformat()
        try:
            mulai = date.fromisoformat(anchor)
        except (KeyError, TypeError, ValueError):
            continue
        repeat = task.get("repeat", "none")
        repeat_end = None
        if repeat != "none" and (task.get("repeat_end_date") or "").strip():
            try:
                repeat_end = date.fromisoformat(task["repeat_end_date"])
            except (TypeError, ValueError):
                repeat_end = None
        if repeat_end is not None and target > repeat_end:
            continue
        cocok = (
            target == mulai
            or (repeat == "daily" and target >= mulai)
            or (repeat == "weekly" and target >= mulai and target.weekday() == mulai.weekday())
            or (repeat == "monthly" and target >= mulai and target.day == mulai.day)
        )
        if not cocok:
            continue
        shown = dict(task)
        if repeat != "none":
            saved_steps = task.get("occurrences", {}).get(day, task.get("steps", []))
            shown["steps"] = [dict(step) for step in saved_steps]
            shown["_occurrence_date"] = day
            shown["scheduled_date"] = day
            if (task.get("deadline") or "").strip():
                shown["deadline"] = day
        tampil.append(shown)
    return tampil


def tasks_today() -> list[dict]:
    return tasks_for(clock.today().isoformat())


def tasks_actionable_today() -> list[dict]:
    today = clock.today()
    current = tasks_for(today.isoformat())
    current_ids = {task.get("id") for task in current}
    carry_over = []
    for task in get_tasks():
        if (
            task.get("id") in current_ids
            or task.get("repeat", "none") != "none"
            or task_is_done(task)
        ):
            continue
        try:
            scheduled = date.fromisoformat(
                task.get("scheduled_date") or task.get("deadline") or ""
            )
        except (KeyError, TypeError, ValueError):
            continue
        if scheduled < today or is_urgent(task):
            carry_over.append(task)
    return current + carry_over


def delete_task(task_id: str) -> None:
    state = load_state()
    state["tasks"] = [t for t in state["tasks"] if t["id"] != task_id]
    save_state(state)


def set_task_steps(task_id: str, steps: list[dict], occurrence_date: Optional[str] = None) -> None:
    state = load_state()
    for task in state["tasks"]:
        if task["id"] == task_id:
            old_steps = task.get("steps", [])
            if occurrence_date and task.get("repeat", "none") != "none":
                old_steps = task.get("occurrences", {}).get(occurrence_date, old_steps)
            done_texts = {
                s.get("text") for s in old_steps if s.get("done")
            }
            new_steps = [
                {
                    **s,
                    "id": s.get("id") or str(uuid.uuid4()),
                    "done": s.get("done", False) or s.get("text") in done_texts,
                }
                for s in steps
            ]
            task["steps"] = new_steps
            if occurrence_date and task.get("repeat", "none") != "none":
                task.setdefault("occurrences", {})[occurrence_date] = [dict(s) for s in new_steps]
            break
    save_state(state)


def set_task_custom_steps(task_id: str, steps: list[str]) -> None:
    state = load_state()
    clean = [str(step).strip() for step in steps if str(step).strip()]
    for task in state["tasks"]:
        if task["id"] == task_id:
            task["custom_steps"] = clean
            break
    save_state(state)


def set_step_done(
    task_id: str, step_index: int, done: bool, occurrence_date: Optional[str] = None
) -> None:
    state = load_state()
    for task in state["tasks"]:
        if task["id"] != task_id:
            continue
        if occurrence_date and task.get("repeat", "none") != "none":
            steps = task.setdefault("occurrences", {}).setdefault(
                occurrence_date, [dict(step) for step in task.get("steps", [])]
            )
        else:
            steps = task.get("steps", [])
        if 0 <= step_index < len(steps):
            steps[step_index]["done"] = done
            break
    save_state(state)


def add_task_step(
    task_id: str, text: str, occurrence_date: Optional[str] = None
) -> bool:
    clean = (text or "").strip()
    if not clean:
        return False
    state = load_state()
    for task in state["tasks"]:
        if task.get("id") != task_id:
            continue
        if occurrence_date and task.get("repeat", "none") != "none":
            steps = task.setdefault("occurrences", {}).setdefault(
                occurrence_date, [dict(step) for step in task.get("steps", [])]
            )
        else:
            steps = task.setdefault("steps", [])
        steps.append({"id": str(uuid.uuid4()), "text": clean, "done": False})
        save_state(state)
        return True
    return False


def update_task_step(
    task_id: str,
    step_index: int,
    text: str,
    occurrence_date: Optional[str] = None,
) -> bool:
    clean = (text or "").strip()
    if not clean:
        return False
    state = load_state()
    for task in state["tasks"]:
        if task.get("id") != task_id:
            continue
        if occurrence_date and task.get("repeat", "none") != "none":
            steps = task.setdefault("occurrences", {}).setdefault(
                occurrence_date, [dict(step) for step in task.get("steps", [])]
            )
        else:
            steps = task.get("steps", [])
        if 0 <= step_index < len(steps):
            steps[step_index]["text"] = clean
            save_state(state)
            return True
        return False
    return False


def delete_task_step(
    task_id: str, step_index: int, occurrence_date: Optional[str] = None
) -> bool:
    state = load_state()
    for task in state["tasks"]:
        if task.get("id") != task_id:
            continue
        if occurrence_date and task.get("repeat", "none") != "none":
            steps = task.setdefault("occurrences", {}).setdefault(
                occurrence_date, [dict(step) for step in task.get("steps", [])]
            )
        else:
            steps = task.get("steps", [])
        if 0 <= step_index < len(steps):
            steps.pop(step_index)
            save_state(state)
            return True
        return False
    return False


def set_task_done(
    task_id: str, done: bool = True, occurrence_date: Optional[str] = None
) -> bool:
    state = load_state()
    for task in state["tasks"]:
        if task.get("id") != task_id:
            continue
        if occurrence_date and task.get("repeat", "none") != "none":
            steps = task.setdefault("occurrences", {}).setdefault(
                occurrence_date, [dict(step) for step in task.get("steps", [])]
            )
        else:
            steps = task.setdefault("steps", [])
        if not steps:
            if not done:
                return False
            steps.append(
                {
                    "id": str(uuid.uuid4()),
                    "text": task.get("title", "Tugas"),
                    "done": True,
                }
            )
        else:
            for step in steps:
                step["done"] = bool(done)
        save_state(state)
        return True
    return False


def ensure_focus_step(
    task_id: str,
    step_text: str,
    occurrence_date: Optional[str] = None,
) -> int:
    """Materialisasi micro-step untuk task yang belum memiliki decomposition."""
    state = load_state()
    for task in state["tasks"]:
        if task.get("id") != task_id:
            continue
        if occurrence_date and task.get("repeat", "none") != "none":
            steps = task.setdefault("occurrences", {}).setdefault(
                occurrence_date, [dict(step) for step in task.get("steps", [])]
            )
        else:
            steps = task.setdefault("steps", [])
        for index, step in enumerate(steps):
            if step.get("text") == step_text:
                return index
        steps.insert(0, {"id": str(uuid.uuid4()), "text": step_text, "done": False})
        if len(steps) == 1:
            steps.append({
                "id": str(uuid.uuid4()),
                "text": f"Lanjutkan {task.get('title', 'tugas')}",
                "done": False,
            })
        save_state(state)
        return 0
    return -1


def apply_focus_outcome(
    task_id: str,
    step_index: int,
    outcome: str,
    occurrence_date: Optional[str] = None,
) -> bool:
    """Terapkan outcome fokus ke step yang tepat tanpa mencocokkan judul."""
    if outcome != "completed" or not task_id:
        return False
    state = load_state()
    for task in state["tasks"]:
        if task.get("id") != task_id:
            continue
        if occurrence_date and task.get("repeat", "none") != "none":
            steps = task.setdefault("occurrences", {}).setdefault(
                occurrence_date, [dict(step) for step in task.get("steps", [])]
            )
        else:
            steps = task.get("steps", [])
        if 0 <= int(step_index) < len(steps):
            steps[int(step_index)]["done"] = True
            save_state(state)
            return True
        return False
    return False


def task_completion_status(task_id: str, occurrence_date: Optional[str] = None) -> bool:
    task = task_for_focus(task_id, occurrence_date)
    return task_is_done(task) if task else False


def task_for_focus(
    task_id: str,
    occurrence_date: Optional[str] = None,
) -> Optional[dict]:
    """Ambil task/occurrence berdasarkan identity sesi, bukan berdasarkan judul."""
    tasks = tasks_for(occurrence_date) if occurrence_date else get_tasks()
    return next((item for item in tasks if item.get("id") == task_id), None)


def next_pending_task_step(
    task_id: str,
    occurrence_date: Optional[str] = None,
) -> Optional[tuple[dict, int, dict]]:
    task = task_for_focus(task_id, occurrence_date)
    if not task:
        return None
    for index, step in enumerate(task.get("steps", [])):
        if not step.get("done"):
            return task, index, step
    return None


def task_step_id(
    task_id: str,
    step_index: int,
    occurrence_date: Optional[str] = None,
) -> str:
    task = task_for_focus(task_id, occurrence_date)
    if not task:
        return ""
    steps = task.get("steps", [])
    if 0 <= step_index < len(steps):
        return str(steps[step_index].get("id", ""))
    return ""


def is_recommendable_task(task: dict) -> bool:
    """Jadwal rutin tetap tampil, tetapi tidak dianggap tugas oleh KALEM."""
    item_type = task.get("item_type")
    if item_type not in {"task", "schedule"}:
        item_type = "schedule" if task.get("repeat", "none") == "weekly" else "task"
    return item_type == "task"


def task_is_done(task: dict) -> bool:
    steps = task.get("steps", [])
    return bool(steps) and all(s.get("done") for s in steps)


def quadrant_of(task: dict, now: Optional[Any] = None) -> str:
    urgent = is_urgent(task, now=now)
    penting = task.get("important", True)
    if urgent and penting:
        return "lakukan"
    if not urgent and penting:
        return "jadwalkan"
    if urgent and not penting:
        return "delegasikan"
    return "nanti"


def eisenhower_summary(day: Optional[str] = None) -> dict[str, list[dict]]:
    day = day or clock.today().isoformat()
    buckets: dict[str, list[dict]] = {
        "lakukan": [],
        "jadwalkan": [],
        "delegasikan": [],
        "nanti": [],
    }
    for task in tasks_for(day):
        if not task_is_done(task):
            buckets[quadrant_of(task)].append(task)
    return buckets


MIN_RECORD_MINUTES = 3


def add_focus_record(
    kategori: str,
    jumlah_unit: float,
    menit: float,
    energi: int = 4,
    task_title: str = "",
    menit_est: int = 0,
    task_estimate_minutes: int = 0,
    selesai: bool = False,
    outcome: str = "",
    task_id: str = "",
    step_id: str = "",
    occurrence_date: str = "",
    step_index: Optional[int] = None,
    decision_id: str = "",
    reflection: str = "",
    session_id: str = "",
    session_started_at: str = "",
    session_ended_at: str = "",
    task_completed: bool = False,
    interruption_count: int = 0,
    pause_duration_minutes: float = 0.0,
) -> Optional[dict]:
    if float(menit) < MIN_RECORD_MINUTES and not outcome:
        return None
    state = load_state()
    record = {
        "id": str(uuid.uuid4()),
        "kategori": kategori,
        "jumlah_unit": float(jumlah_unit),
        "menit": round(float(menit), 1),
        "menit_est": int(menit_est),
        "task_estimate_minutes": int(task_estimate_minutes or 0),
        "selesai": bool(selesai),
        "energi": int(energi),
        "task_title": task_title,
        "task_id": task_id,
        "step_id": step_id,
        "occurrence_date": occurrence_date,
        "step_index": step_index,
        "decision_id": decision_id,
        "outcome": outcome,
        "reflection": reflection.strip(),
        "session_id": session_id,
        "session_started_at": session_started_at,
        "session_ended_at": session_ended_at or clock.now().isoformat(),
        "actual_focus_minutes": round(float(menit), 1),
        "actual_active_duration_minutes": round(float(menit), 4),
        "interruption_count": max(0, int(interruption_count)),
        "pause_duration_minutes": round(max(0.0, float(pause_duration_minutes)), 4),
        "task_completed": bool(task_completed),
        "date": clock.today().isoformat(),
        "timestamp": clock.now().isoformat(),
    }
    state.setdefault("focus_records", []).insert(0, record)
    state["focus_records"] = state["focus_records"][:200]
    save_state(state)
    return record


def get_focus_records() -> list[dict]:
    return load_state().get("focus_records", [])


def _deadline_features(task: dict) -> tuple[bool, float]:
    raw = str(task.get("deadline") or "").strip()
    if not raw:
        return False, 0.0
    prediction = task.get("duration_prediction") or {}
    stored_days = prediction.get("deadline_days")
    if stored_days is not None:
        try:
            return True, float(stored_days)
        except (TypeError, ValueError):
            pass
    try:
        created = datetime.fromisoformat(str(task.get("created_at") or ""))
        deadline = date.fromisoformat(raw)
    except (TypeError, ValueError):
        return True, 0.0
    return True, float(max(0, (deadline - created.date()).days))


def start_focus_outcome_record(
    *,
    session_id: str,
    task_id: str,
    step_id: str,
    occurrence_date: str,
    planned_session_minutes: int,
    task_title: str,
) -> str:
    """Persist one versioned, unfinished Focus session for offline ML export."""
    state = load_state()
    task = next(
        (item for item in state.get("tasks", []) if item.get("id") == task_id),
        None,
    )
    prediction = (task or {}).get("duration_prediction") or {}
    has_deadline, deadline_days = _deadline_features(task or {})
    provenance = data_provenance.task_provenance(task)
    synthetic = data_provenance.is_synthetic(provenance)
    from app import config

    collection_context = "setting_demo" if config.DEMO_MODE else "production"
    record_id = str(uuid.uuid4())
    record = {
        "schema_version": FOCUS_OUTCOME_SCHEMA_VERSION,
        "record_id": record_id,
        "session_id": session_id,
        "task_id": task_id,
        "step_id": step_id,
        "occurrence_date": occurrence_date,
        "task_text": str((task or {}).get("title") or task_title or ""),
        "category": str((task or {}).get("kategori") or ""),
        "importance": prediction.get("importance"),
        "has_deadline": has_deadline,
        "deadline_days_or_zero": deadline_days,
        "predicted_duration_minutes": prediction.get("estimated_duration_minutes"),
        "prediction_model_version": str(prediction.get("model_version") or ""),
        "prediction_source": str(prediction.get("source") or ""),
        "global_prediction_minutes": prediction.get("global_prediction_minutes"),
        "global_model_version": str(
            prediction.get("global_model_version")
            or prediction.get("model_version")
            or ""
        ),
        "global_dataset_version": str(prediction.get("global_dataset_version") or ""),
        "global_artifact_sha256": str(prediction.get("global_artifact_sha256") or ""),
        "personalization_version": str(
            prediction.get("personalization_version") or ""
        ),
        "personalization_dataset_version": str(
            prediction.get("personalization_dataset_version") or ""
        ),
        "planned_session_minutes": int(planned_session_minutes),
        "task_created_at": str((task or {}).get("created_at") or ""),
        "started_at": datetime.now().isoformat(),
        "ended_at": "",
        "actual_active_duration_minutes": None,
        "pause_duration_minutes": 0.0,
        "completion_status": "started",
        "outcome": "",
        "interruption_count": 0,
        "task_completed": False,
        "task_snapshot_captured": task is not None,
        "timing_quality": "pause_aware_no_visibility_signal",
        "data_provenance": provenance,
        "collection_context": collection_context,
        "is_demo": provenance == data_provenance.SYNTHETIC_SCENARIO,
        "synthetic": synthetic,
        "created_at": clock.now().isoformat(),
        "data_quality_status": "unknown",
        "data_quality_reason": "session_in_progress",
    }
    state.setdefault("ml_outcome_records", []).append(record)
    state["ml_outcome_records"] = state["ml_outcome_records"][-MAX_FOCUS_OUTCOME_RECORDS:]
    save_state(state)
    return record_id


def update_focus_outcome_record(session_id: str, **changes: Any) -> bool:
    if not session_id:
        return False
    allowed = {
        "planned_session_minutes",
        "interruption_count",
        "pause_duration_minutes",
        "completion_status",
        "outcome",
        "ended_at",
        "actual_active_duration_minutes",
        "task_completed",
        "data_quality_status",
        "data_quality_reason",
    }
    state = load_state()
    for record in reversed(state.get("ml_outcome_records", [])):
        if record.get("session_id") != session_id:
            continue
        for key, value in changes.items():
            if key in allowed:
                record[key] = value
        save_state(state)
        return True
    return False


def get_focus_outcome_records() -> list[dict]:
    return load_state().get("ml_outcome_records", [])


MAX_DECOMPOSE_RECORDS = 300


def add_decompose_record(
    title: str,
    description: str,
    steps: list[str],
    source: str = "ai",
    language: str = "id",
) -> Optional[dict]:
    steps = [s.strip() for s in steps if (s or "").strip()]
    if not (title or "").strip() or not steps:
        return None

    state = load_state()
    record = {
        "title": title.strip(),
        "description": (description or "").strip(),
        "steps": steps,
        "source": source,
        "language": language,
        "date": clock.today().isoformat(),
    }
    daftar = state.setdefault("decompose_records", [])
    kunci = (record["title"].lower(), record["description"].lower())
    state["decompose_records"] = [
        r for r in daftar
        if (r.get("title", "").lower(), r.get("description", "").lower()) != kunci
    ]
    state["decompose_records"].insert(0, record)
    state["decompose_records"] = state["decompose_records"][:MAX_DECOMPOSE_RECORDS]
    save_state(state)
    return record


def get_decompose_records() -> list[dict]:
    return load_state().get("decompose_records", [])


MAX_DECISION_RECORDS = 500


def _fitur_ringkas(f: Optional[Any]) -> dict[str, float]:
    if f is None:
        return {}
    kolom = (
        "skor_3h", "energi_terakhir", "streak_abai", "n_sos_7h",
        "n_belum_selesai", "n_mendesak", "beban_menit", "rasio_selesai_7h",
        "di_jam_produktif", "di_jam_capek", "jam", "weekday", "is_weekend",
        "obat_kelewat", "hari_sejak_checkin",
    )
    keluar: dict[str, float] = {}
    for k in kolom:
        try:
            keluar[k] = round(float(f[k]), 3)
        except (KeyError, TypeError, ValueError):
            continue
    return keluar


def record_decision_shown(
    kind: str,
    action_kind: str,
    fitur: Optional[Any] = None,
    label: str = "",
    *,
    task_id: str = "",
    occurrence_date: str = "",
    step_index: Optional[int] = None,
) -> Optional[str]:
    if not kind:
        return None
    state = load_state()
    daftar = state.setdefault("decision_records", [])
    hari_ini = clock.today().isoformat()

    for r in daftar:
        if (
            r.get("date") == hari_ini
            and r.get("kind") == kind
            and r.get("action_kind") == action_kind
            and r.get("task_id", "") == task_id
            and r.get("occurrence_date", "") == occurrence_date
            and r.get("step_index") == step_index
            and not r.get("acted")
        ):
            r["n_tampil"] = int(r.get("n_tampil", 1)) + 1
            r["terakhir_tampil"] = clock.now().isoformat()
            save_state(state)
            return r.get("id")

    catatan = {
        "id": str(uuid.uuid4()),
        "date": hari_ini,
        "timestamp": clock.now().isoformat(),
        "terakhir_tampil": clock.now().isoformat(),
        "kind": kind,
        "action_kind": action_kind,
        "label": label,
        "task_id": task_id,
        "occurrence_date": occurrence_date,
        "step_index": step_index,
        "n_tampil": 1,
        "acted": False,
        "acted_at": "",
        "started": False,
        "started_at": "",
        "completed": False,
        "completed_at": "",
        "outcome": "",
        "outcome_at": "",
        "actual_focus_minutes": None,
        "planned_focus_minutes": None,
        "helpful": None,
        "fitur": _fitur_ringkas(fitur),
    }
    daftar.insert(0, catatan)
    state["decision_records"] = daftar[:MAX_DECISION_RECORDS]
    save_state(state)
    return catatan["id"]


def record_decision_acted(kind: str, action_kind: str) -> bool:
    state = load_state()
    hari_ini = clock.today().isoformat()
    for r in state.get("decision_records", []):
        if (
            r.get("date") == hari_ini
            and r.get("kind") == kind
            and r.get("action_kind") == action_kind
            and not r.get("acted")
        ):
            r["acted"] = True
            r["acted_at"] = clock.now().isoformat()
            save_state(state)
            return True
    return False


def record_decision_acted_by_id(record_id: Optional[str]) -> bool:
    if not record_id:
        return False
    state = load_state()
    for record in state.get("decision_records", []):
        if record.get("id") != record_id:
            continue
        if not record.get("acted"):
            record["acted"] = True
            record["acted_at"] = clock.now().isoformat()
            save_state(state)
        return True
    return False


def record_decision_started(
    record_id: Optional[str], *, planned_focus_minutes: Optional[int] = None
) -> bool:
    if not record_id:
        return False
    state = load_state()
    for record in state.get("decision_records", []):
        if record.get("id") != record_id:
            continue
        record["started"] = True
        record["started_at"] = record.get("started_at") or clock.now().isoformat()
        if planned_focus_minutes is not None:
            record["planned_focus_minutes"] = max(int(planned_focus_minutes), 0)
        save_state(state)
        return True
    return False


def record_decision_outcome(
    record_id: Optional[str],
    *,
    completed: bool,
    outcome: str = "",
    helpful: Optional[bool] = None,
    actual_focus_minutes: Optional[float] = None,
    planned_focus_minutes: Optional[int] = None,
) -> bool:
    if not record_id:
        return False
    state = load_state()
    for record in state.get("decision_records", []):
        if record.get("id") != record_id:
            continue
        timestamp = clock.now().isoformat()
        resolved_outcome = outcome or ("completed" if completed else "incomplete")
        record["outcome"] = resolved_outcome
        record["outcome_at"] = timestamp
        record["completed"] = bool(completed)
        record["completed_at"] = timestamp if completed else ""
        if actual_focus_minutes is not None:
            record["actual_focus_minutes"] = round(
                max(float(actual_focus_minutes), 0.0), 1
            )
        if planned_focus_minutes is not None:
            record["planned_focus_minutes"] = max(int(planned_focus_minutes), 0)
        if helpful is not None:
            record["helpful"] = bool(helpful)
        save_state(state)
        return True
    return False


def get_decision_records() -> list[dict]:
    return load_state().get("decision_records", [])


def add_inbox_note(text: str) -> dict:
    state = load_state()
    note = {
        "id": str(uuid.uuid4()),
        "text": text.strip(),
        "created_at": clock.now().isoformat(),
    }
    state.setdefault("inbox", []).insert(0, note)
    save_state(state)
    return note


def get_inbox() -> list[dict]:
    return load_state().get("inbox", [])


def delete_inbox_note(note_id: str) -> None:
    state = load_state()
    state["inbox"] = [n for n in state.get("inbox", []) if n["id"] != note_id]
    save_state(state)


def add_mood_log(
    mood: str,
    score: int,
    energy: int,
    diary: str = "",
    tags: Optional[list[str]] = None,
    quick_tags: Optional[list[str]] = None,
    ate_today: Optional[bool] = None,
    rested_enough: Optional[bool] = None,
) -> dict:
    state = load_state()
    today = clock.today()
    previous = next(
        (entry for entry in state["mood_logs"] if entry.get("date") == today.isoformat()),
        {},
    )
    log = {
        "date": today.isoformat(),
        "mood": mood,
        "score": score,
        "energy": energy,
        "diary": diary if diary else previous.get("diary", ""),
        "tags": tags if tags is not None else previous.get("tags", []),
        "quick_tags": quick_tags if quick_tags is not None else previous.get("quick_tags", []),
        "ate_today": ate_today if ate_today is not None else previous.get("ate_today"),
        "rested_enough": rested_enough if rested_enough is not None else previous.get("rested_enough"),
        "weekday": today.weekday(),
        "is_weekend": today.weekday() >= 5,
    }
    state["mood_logs"] = [entry for entry in state["mood_logs"] if entry["date"] != log["date"]]
    state["mood_logs"].insert(0, log)
    save_state(state)
    return log


def get_mood_logs() -> list[dict]:
    return load_state()["mood_logs"]


def latest_mood() -> Optional[dict]:
    logs = get_mood_logs()
    return logs[0] if logs else None


def today_mood() -> Optional[dict]:
    latest = latest_mood()
    return latest if latest and latest["date"] == clock.today().isoformat() else None


def diary_entries() -> list[dict]:
    state = load_state()
    records = list(state.get("diary_records", []))
    dates_with_records = {record.get("date") for record in records}
    legacy = [
        {
            "id": f"legacy-{entry.get('date', '')}",
            "date": entry.get("date", ""),
            "timestamp": entry.get("date", ""),
            "diary": entry.get("diary", ""),
            "mood": entry.get("mood", "tenang"),
            "tags": list(entry.get("tags") or []),
            "source": "legacy_mood_log",
        }
        for entry in state.get("mood_logs", [])
        if entry.get("diary") and entry.get("date") not in dates_with_records
    ]
    return sorted(
        records + legacy,
        key=lambda entry: str(entry.get("timestamp", entry.get("date", ""))),
        reverse=True,
    )


def add_diary_entry(
    text: str,
    *,
    mood: str = "",
    tags: Optional[list[str]] = None,
    source: str = "diary",
) -> Optional[dict]:
    clean = (text or "").strip()
    if not clean:
        return None
    state = load_state()
    today = clock.today().isoformat()
    today_log = next(
        (entry for entry in state.get("mood_logs", []) if entry.get("date") == today),
        None,
    )
    records = state.setdefault("diary_records", [])
    if today_log and today_log.get("diary") and not any(
        record.get("date") == today for record in records
    ):
        records.append({
            "id": str(uuid.uuid4()),
            "date": today,
            "timestamp": f"{today}T00:00:00",
            "diary": today_log["diary"],
            "mood": today_log.get("mood", "tenang"),
            "tags": list(today_log.get("tags") or []),
            "source": "legacy_mood_log",
        })
    record = {
        "id": str(uuid.uuid4()),
        "date": today,
        "timestamp": clock.now().isoformat(),
        "diary": clean,
        "mood": mood or (today_log or {}).get("mood", "tenang"),
        "tags": list(tags or []),
        "source": source,
    }
    records.insert(0, record)
    if today_log is not None:
        today_texts = [
            item.get("diary", "")
            for item in reversed(records)
            if item.get("date") == today and item.get("diary")
        ]
        today_log["diary"] = "\n\n".join(today_texts)
        today_log["tags"] = list(dict.fromkeys(
            list(today_log.get("tags") or []) + list(tags or [])
        ))[:12]
    save_state(state)
    return record


def add_reset_event(choice: str) -> dict:
    state = load_state()
    latest = state["mood_logs"][0] if state["mood_logs"] else None
    event = {
        "id": str(uuid.uuid4()),
        "timestamp": clock.now().isoformat(),
        "date": clock.today().isoformat(),
        "choice": choice,
        "mood_score": latest["score"] if latest else None,
        "energy_before": latest.get("energy") if latest else None,
        "completed": False,
        "completed_at": "",
        "improved": None,
        "followup_used": False,
        "stages": [],
    }
    state["reset_events"].insert(0, event)
    save_state(state)
    return event


def append_reset_stage(event_id: str, stage: str) -> bool:
    """Tambahkan jejak tahap ke satu event recovery tanpa menggandakan sinyal SOS."""
    clean = (stage or "").strip()
    if not clean:
        return False
    state = load_state()
    for event in state.get("reset_events", []):
        if event.get("id") != event_id:
            continue
        event.setdefault("stages", []).append({
            "name": clean,
            "timestamp": clock.now().isoformat(),
        })
        save_state(state)
        return True
    return False


def complete_reset_event(event_id: str, *, improved: bool) -> bool:
    state = load_state()
    for event in state.get("reset_events", []):
        if event.get("id") != event_id:
            continue
        event["completed"] = True
        event["completed_at"] = clock.now().isoformat()
        event["improved"] = bool(improved)
        save_state(state)
        return True
    return False


def mark_reset_followup_used(event_id: str) -> bool:
    state = load_state()
    for event in state.get("reset_events", []):
        if event.get("id") != event_id:
            continue
        event["followup_used"] = True
        save_state(state)
        return True
    return False


def get_reset_events(within_days: Optional[int] = None) -> list[dict]:
    events = load_state()["reset_events"]
    if within_days is None:
        return events
    cutoff = clock.today() - timedelta(days=within_days)
    return [e for e in events if date.fromisoformat(e["date"]) >= cutoff]


def set_medication(name: str, pills_left: int, pills_per_day: float) -> dict:
    state = load_state()
    existing = state.get("medication") or {}
    same_drug = (existing.get("name") or "").strip().lower() == name.strip().lower()
    state["medication"] = {
        "name": name,
        "pills_left": pills_left,
        "pills_per_day": pills_per_day,
        "start_date": existing.get("start_date") if same_drug and existing.get("start_date")
        else clock.today().isoformat(),
        "enabled": True,
        "last_taken": existing.get("last_taken", ""),
        "take_log": existing.get("take_log", []),
        "bpom": existing.get("bpom") if same_drug else None,
    }
    save_state(state)
    return state["medication"]


def set_medication_registry(entry: dict) -> None:
    state = load_state()
    if state.get("medication"):
        state["medication"]["bpom"] = entry
        save_state(state)


def get_medication() -> Optional[dict]:
    return load_state()["medication"]


def take_medication() -> Optional[dict]:
    state = load_state()
    med = state.get("medication")
    if not med or not med.get("enabled", True):
        return None
    if float(med.get("pills_left", 0)) <= 0:
        return None

    today_iso = clock.today().isoformat()
    if med.get("last_taken") == today_iso:
        return med

    rate = float(med.get("pills_per_day", 1))
    med["pills_left"] = max(float(med.get("pills_left", 0)) - rate, 0)
    med["last_taken"] = today_iso
    med.setdefault("take_log", []).insert(0, today_iso)
    save_state(state)
    return med


def disable_medication() -> None:
    state = load_state()
    if state["medication"]:
        state["medication"]["enabled"] = False
        save_state(state)
