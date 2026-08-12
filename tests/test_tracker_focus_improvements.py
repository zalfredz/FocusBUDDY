"""Acceptance contract untuk improvement Tracker, Focus, dan Home."""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import flet as ft

from app import clock, focus_session, storage
from app.views import demo_tools, home, tracker
from models.model_overwhelm import Risiko


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  [OK] " if condition else "  [FAIL] ") + message)
    if not condition:
        FAILURES.append(message)


class FakePage:
    def __init__(self) -> None:
        self.dialogs: list = []
        self.overlay: list = []

    def update(self) -> None:
        pass

    def show_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def run_task(self, fn, *args) -> None:
        pass


def walk(control):
    if control is None:
        return
    yield control
    for child in getattr(control, "controls", []) or []:
        yield from walk(child)
    for action in getattr(control, "actions", []) or []:
        yield from walk(action)
    yield from walk(getattr(control, "title", None))
    yield from walk(getattr(control, "subtitle", None))
    yield from walk(getattr(control, "content", None))


def texts(root) -> list[str]:
    return [
        control.value
        for control in walk(root)
        if isinstance(getattr(control, "value", None), str)
    ]


def clickable(root, label: str):
    return next(
        (
            control
            for control in walk(root)
            if getattr(control, "on_click", None) is not None
            and label in texts(control)
        ),
        None,
    )


def prepare() -> None:
    focus_session.stop()
    state = storage.reset_all_data()
    state["profile"].update(
        {"name": "Ari", "onboarded": True, "productive_hours": []}
    )
    state["last_brief_date"] = clock.today().isoformat()
    storage.save_state(state)
    storage.add_mood_log(
        "tenang", 4, 4, ate_today=True, rested_enough=True
    )
    storage.set_today_energy(4)


def scenario_rest_outcome_duration_and_logging() -> None:
    print("\n=== Outcome istirahat, durasi opsional, dan decision logging ===")
    task = storage.add_task(
        "Tugas panjang",
        clock.today().isoformat(),
        deadline_time="23:59",
        menit_est=90,
        steps=[{"id": "step-rest", "text": "Buka dokumen", "done": False}],
    )
    record_id = storage.record_decision_shown(
        "next_action",
        "focus",
        {"energi_terakhir": 4},
        "FOKUS 10 menit",
        task_id=task["id"],
        step_index=0,
    )
    storage.record_decision_acted_by_id(record_id)
    focus_session.start(
        10,
        label="Buka dokumen",
        task_title=task["title"],
        task_id=task["id"],
        step_id="step-rest",
        step_index=0,
        decision_id=record_id or "",
        task_estimate_minutes=90,
    )

    page = FakePage()
    routes: list[str] = []
    with patch("models.model_overwhelm.nilai", return_value=Risiko(0, "tenang", "test")):
        root = home.build(page, routes.append)
    shown = texts(root)
    check("Estimasi sisa task" in shown and "Durasi sesi" in shown,
          "Focus memisahkan estimasi task dari durasi sesi")
    check("~90 menit" in shown and "10 menit" in shown,
          "kedua angka memakai metadata yang berbeda")

    edit_duration = clickable(root, "Ubah durasi")
    check(edit_duration is not None, "Ubah durasi tersedia sebagai kontrol opsional")
    if edit_duration is not None:
        edit_duration.on_click(None)
    duration_dialog = page.dialogs[-1] if page.dialogs else None
    duration_field = next(
        (control for control in walk(duration_dialog)
         if isinstance(control, ft.TextField) and control.label == "Durasi sesi (menit)"),
        None,
    )
    save_duration = clickable(duration_dialog, "Simpan durasi")
    check(duration_field is not None and save_duration is not None,
          "dialog durasi meminta angka lalu menyimpan secara eksplisit")
    if duration_field is not None:
        duration_field.value = "18"
    if save_duration is not None:
        save_duration.on_click(None)
    check(focus_session.snapshot()["total_seconds"] == 18 * 60,
          "durasi sesi aktif berubah tanpa membuat sesi baru")
    check(focus_session.snapshot()["task_estimate_minutes"] == 90,
          "mengubah durasi sesi tidak menimpa estimasi task")

    end_session = clickable(root, "Akhiri sesi")
    if end_session is not None:
        end_session.on_click(None)
    outcome_dialog = page.dialogs[-1] if page.dialogs else None
    rest = clickable(outcome_dialog, "Butuh istirahat")
    check(rest is not None, "Butuh istirahat tersedia sebagai outcome Focus")
    if rest is not None:
        rest.on_click(None)

    stored_task = next(item for item in storage.get_tasks() if item["id"] == task["id"])
    focus_record = storage.get_focus_records()[0]
    decision_record = next(
        item for item in storage.get_decision_records() if item["id"] == record_id
    )
    check(not stored_task["steps"][0]["done"],
          "outcome istirahat tidak menyelesaikan task")
    check(focus_record.get("outcome") == "rest"
          and focus_record.get("task_estimate_minutes") == 90,
          "Focus record menyimpan outcome dan estimasi task")
    check(
        decision_record.get("outcome") == "rest"
        and decision_record.get("outcome_at")
        and decision_record.get("completed") is False
        and decision_record.get("completed_at") == "",
        "decision record membedakan resolved outcome dari task completion",
    )
    check(
        decision_record.get("planned_focus_minutes") == 18
        and decision_record.get("actual_focus_minutes") is not None,
        "decision record menyimpan durasi rencana dan aktual secara eksplisit",
    )


def scenario_tracker_focus_history_actual_only() -> None:
    print("\n=== Tracker menampilkan Focus History aktual tanpa target ===")
    for title, minutes, outcome in (
        ("Baca jurnal", 8.5, "completed"),
        ("Tulis ringkasan", 4, "rest"),
    ):
        storage.add_focus_record(
            kategori="Belajar",
            jumlah_unit=1,
            menit=minutes,
            task_title=title,
            outcome=outcome,
        )
    root = tracker.build(FakePage(), lambda route: None)
    shown = texts(root)
    check("FOCUS HISTORY" in shown, "Tracker punya bagian Focus History ringkas")
    check("Sesi aktual" in shown and "Menit aktual" in shown,
          "Tracker membedakan jumlah sesi dan total menit aktual")
    check("12.5" in shown and "2" in shown,
          "ringkasan dihitung dari focus record hari ini")
    check("Butuh istirahat" in shown and "Selesai" in shown,
          "riwayat ringkas menerjemahkan outcome sesi")
    check(any("bukan target yang wajib" in value for value in shown),
          "total aktual tidak diubah menjadi target wajib")


def scenario_passive_deadline_cue() -> None:
    print("\n=== Home memberi deadline cue pasif ===")
    now = datetime(2026, 8, 11, 10, 0)
    due_today = {
        "deadline": "2026-08-11", "deadline_time": "17:00"
    }
    overdue = {"deadline": "2026-08-10", "deadline_time": "10:00"}
    no_deadline = {"deadline": "", "deadline_time": ""}
    check(home.deadline_cue(due_today, now)[0] == "Deadline hari ini · 17:00",
          "deadline hari ini ditampilkan sebagai cue, bukan interruption")
    check("lewat" in home.deadline_cue(overdue, now)[0].lower(),
          "deadline terlewat punya cue pasif yang jelas")
    check(home.deadline_cue(no_deadline, now)[0] == "",
          "task tanpa deadline tidak diberi deadline palsu")

    storage.add_task(
        "Kirim laporan",
        clock.today().isoformat(),
        deadline_time="23:59",
        menit_est=20,
        steps=[{"text": "Buka laporan", "done": False}],
    )
    with patch("models.model_overwhelm.nilai", return_value=Risiko(0, "tenang", "test")):
        root = home.build(FakePage(), lambda route: None)
    check(any(value.startswith("Deadline hari ini") for value in texts(root)),
          "deadline cue benar-benar dirender pada card keputusan Home")


def main() -> int:
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    with tempfile.TemporaryDirectory(prefix="focusbuddy_tracker_focus_") as directory:
        storage.DATA_DIR = Path(directory)
        storage.DATA_FILE = storage.DATA_DIR / "data.json"
        storage.BACKUP_FILE = storage.DATA_DIR / "data.json.bak"
        try:
            for scenario in (
                scenario_rest_outcome_duration_and_logging,
                scenario_tracker_focus_history_actual_only,
                scenario_passive_deadline_cue,
            ):
                prepare()
                scenario()
        finally:
            focus_session.stop()
            storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original
            clock.reset_offset()

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"GAGAL: {len(FAILURES)} improvement belum terpenuhi")
        return 1
    print("SEMUA IMPROVEMENT TRACKER/FOCUS LULUS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
