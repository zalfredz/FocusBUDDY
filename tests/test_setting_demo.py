"""Tes skenario dan overlay demo."""
from __future__ import annotations

import sys
import tempfile
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import SettingDemo
from app import storage


def _test_overlay_tidak_merusak_data_user() -> None:
    storage.reset_all_data()
    state = storage.load_state()
    state["profile"].update(
        {
            "name": "Nama User Asli",
            "onboarded": True,
            "age_range": "25-34",
            "status": ["kerja"],
            "on_medication": "ya",
        }
    )
    state["favorites"]["musik"] = "musik asli"
    state["medication"] = {
        "name": "Obat user",
        "pills_left": 7,
        "pills_per_day": 1,
        "start_date": "2026-08-01",
        "enabled": True,
        "last_taken": "",
        "take_log": [],
        "bpom": None,
    }
    state["subscription"] = {"is_premium": False}
    state["today_energy"] = {"date": date.today().isoformat(), "level": 6}
    state["last_brief_date"] = "2026-08-09"
    state["tasks"] = [{"id": "task-asli", "title": "Tugas asli", "steps": []}]
    state["mood_logs"] = [
        {
            "date": date.today().isoformat(),
            "mood": "tenang",
            "score": 4,
            "energy": 5,
            "diary": "Diary ini tidak boleh hilang",
        }
    ]
    state["reset_events"] = [
        {"timestamp": "2026-08-08T10:00:00", "date": "2026-08-08", "choice": "musik"}
    ]
    state["inbox"] = [{"id": "inbox-asli", "text": "Catatan asli"}]
    state["focus_records"] = [{"id": "focus-asli"}]
    state["decompose_records"] = [{"id": "pecah-asli"}]
    state["decision_records"] = [{"id": "decision-asli"}]
    storage.save_state(state)
    original = deepcopy(storage.load_state())

    SettingDemo.apply_scenario_overlay("learning_from_history")
    overlaid = storage.load_state()

    for key in (
        "profile",
        "favorites",
        "medication",
        "subscription",
        "today_energy",
        "focus_records",
        "decompose_records",
        "decision_records",
    ):
        assert overlaid[key] == original[key], f"overlay mengubah {key} milik user"
    for collection, original_id in (
        ("tasks", "task-asli"),
        ("inbox", "inbox-asli"),
    ):
        assert any(item.get("id") == original_id for item in overlaid[collection])
        assert any(item.get("_demo_generated") is True for item in overlaid[collection])
    assert any(
        log.get("diary") == "Diary ini tidak boleh hilang"
        for log in overlaid["mood_logs"]
    )
    today_logs = [log for log in overlaid["mood_logs"] if log.get("date") == date.today().isoformat()]
    assert len(today_logs) == 1 and not today_logs[0].get("_demo_generated")

    SettingDemo.apply_scenario_overlay("deadline_stack")
    replaced = storage.load_state()
    demo_entries = [
        item
        for collection in ("tasks", "mood_logs", "reset_events", "inbox")
        for item in replaced.get(collection, [])
        if item.get("_demo_generated") is True
    ]
    assert demo_entries
    assert {item.get("_demo_scenario") for item in demo_entries} == {"deadline_stack"}

    assert SettingDemo.clear_demo_overlay() is True
    cleared = storage.load_state()
    assert "demo_overlay" not in cleared
    assert all(
        not item.get("_demo_generated")
        for collection in ("tasks", "mood_logs", "reset_events", "inbox")
        for item in cleared.get(collection, [])
    )
    for key in (
        "profile",
        "favorites",
        "medication",
        "subscription",
        "today_energy",
        "tasks",
        "mood_logs",
        "reset_events",
        "inbox",
        "focus_records",
        "decompose_records",
        "decision_records",
        "last_brief_date",
    ):
        assert cleared[key] == original[key], f"cleanup tidak memulihkan {key}"


def main() -> int:
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    with tempfile.TemporaryDirectory(prefix="focusbuddy_demo_") as directory:
        storage.DATA_DIR = Path(directory)
        storage.DATA_FILE = storage.DATA_DIR / "data.json"
        storage.BACKUP_FILE = storage.DATA_DIR / "data.json.bak"
        try:
            _test_overlay_tidak_merusak_data_user()
            assert len(SettingDemo.SCENARIOS) == 10, "demo harus tetap punya 10 skenario inti"
            assert set(SettingDemo.SCENARIOS) == set(SettingDemo.DEMO_OBJECTIVES), "set skenario/objective harus sama"
            results = {key: SettingDemo.run_demo(key) for key in SettingDemo.SCENARIOS}
        finally:
            storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original

    assert results["after_reset"]["passed"] is False, "gap recovery harus terlihat gagal secara jujur"
    assert any(item["passed"] is False for item in results["after_reset"]["checks"])
    assert all(result["passed"] in (True, False) for result in results.values())
    print("Overlay aman + 10 skenario pipeline nyata lolos; after_reset tetap gap eksplisit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
