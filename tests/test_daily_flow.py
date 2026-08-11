"""Kontrak integrasi siklus harian KALEM."""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import buddy, clock, focus_session, storage
from app.core.kalem_engine import DayState, decide, focus_minutes_for
from app.views import home, tracker
from models.model_overwhelm import Risiko


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  [OK] " if condition else "  [FAIL] ") + message)
    if not condition:
        FAILURES.append(message)


class FakePage:
    def __init__(self) -> None:
        self.dialogs = []
        self.overlay = []

    def update(self) -> None:
        pass

    def show_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def run_task(self, fn, *args) -> None:
        pass


def walk_controls(control):
    if control is None:
        return
    yield control
    for child in getattr(control, "controls", []) or []:
        yield from walk_controls(child)
    yield from walk_controls(getattr(control, "content", None))


def task(
    task_id: str,
    title: str,
    *,
    deadline: str | None = None,
    deadline_time: str = "",
    minutes: int = 30,
    steps: list[dict] | None = None,
    repeat: str = "none",
    occurrence: str | None = None,
) -> dict:
    result = {
        "id": task_id,
        "title": title,
        "deadline": deadline or clock.today().isoformat(),
        "deadline_time": deadline_time,
        "important": True,
        "difficulty_est": 2,
        "menit_est": minutes,
        "created_at": clock.now().isoformat(),
        "repeat": repeat,
        "steps": steps if steps is not None else [{"text": f"Buka {title}", "done": False}],
    }
    if occurrence:
        result["_occurrence_date"] = occurrence
    return result


def scenario_checkin_before_brief_and_decision() -> None:
    print("\n=== Check-in menjadi prerequisite daily decision ===")
    state = storage.load_state()
    state["profile"].update({"name": "Ari", "onboarded": True})
    state["last_brief_date"] = ""
    storage.save_state(state)

    ready = getattr(storage, "ready_for_morning_brief", None)
    check(callable(ready), "storage menyediakan gate Morning Brief berbasis check-in aktual")
    if callable(ready):
        check(not ready(), "Morning Brief belum final sebelum check-in hari ini")

    page = FakePage()
    home.build(page, lambda route: None)
    check(len(page.dialogs) == 1, "hanya satu interruption check-in yang tampil")
    check(
        storage.get_decision_records() == [],
        "decision di balik modal check-in belum dicatat sebagai shown",
    )

    storage.add_mood_log("tenang", 4, 4)
    if callable(ready):
        check(ready(), "selesai check-in membuat Morning Brief siap dihitung ulang")


def scenario_deadline_progress_with_small_capacity() -> None:
    print("\n=== Deadline dekat tetap mendapat progress dalam capacity kecil ===")
    now = datetime.combine(clock.today(), datetime.min.time()).replace(hour=10)
    urgent = task(
        "urgent",
        "Laporan deadline dua jam",
        deadline=clock.today().isoformat(),
        deadline_time="12:00",
        minutes=90,
        steps=[{"text": "Buka data laporan", "done": False}],
    )
    quick = task(
        "quick",
        "Balas email besok",
        deadline=(clock.today() + timedelta(days=1)).isoformat(),
        minutes=15,
    )
    day = DayState(
        tasks_today=[quick, urgent],
        mood_logs=[{"date": clock.today().isoformat(), "score": 5, "energy": 5}],
        energy_level=5,
        available_minutes=20,
    )
    with patch("models.model_overwhelm.nilai", return_value=Risiko(0, "tenang", "prior")):
        decision = decide({"name": "Ari", "productive_hours": []}, day, now=now)
    check(decision.task is not None and decision.task["id"] == "urgent",
          "task deadline dekat tidak dibuang hanya karena estimasi totalnya besar")
    check(decision.focus_minutes <= 20,
          "durasi progress tidak melewati available_minutes yang benar-benar diberikan")
    check(decision.step_text == "Buka data laporan",
          "progress tetap memakai langkah konkret yang terhubung ke parent task")


def scenario_capacity_none_and_zero_are_distinct() -> None:
    print("\n=== Capacity None tidak dikarang, capacity nol dihormati ===")
    workload = task("capacity", "Kerjakan laporan", minutes=90)
    now = datetime.combine(clock.today(), datetime.min.time()).replace(hour=14)
    base = {
        "tasks_today": [workload],
        "mood_logs": [{"date": clock.today().isoformat(), "score": 5, "energy": 5}],
        "energy_level": 5,
    }
    with patch("models.model_overwhelm.nilai", return_value=Risiko(0, "tenang", "prior")):
        unknown = decide(
            {"name": "Ari", "productive_hours": []},
            DayState(**base, available_minutes=None),
            now=now,
        )
        none_left = decide(
            {"name": "Ari", "productive_hours": []},
            DayState(**base, available_minutes=0),
            now=now,
        )
    check(unknown.action_kind == "focus" and unknown.focus_minutes == focus_minutes_for(5),
          "None tidak diganti angka capacity sintetis")
    check(none_left.action_kind == "rest" and none_left.focus_minutes == 0,
          "available_minutes=0 tidak menghasilkan sesi satu menit yang melampaui capacity")
def scenario_medication_only_when_relevant() -> None:
    print("\n=== Medication tidak mendominasi keputusan sepanjang hari ===")
    workload = task("med-task", "Kerjakan tugas", minutes=20)
    medication = {"last_taken": ""}
    day = DayState(
        tasks_today=[workload],
        mood_logs=[{"date": clock.today().isoformat(), "score": 4, "energy": 4}],
        energy_level=4,
        medication=medication,
    )
    status = SimpleNamespace(active=True, pills_remaining=10, name="Obat rutin")
    morning = datetime.combine(clock.today(), datetime.min.time()).replace(hour=9)
    afternoon = morning.replace(hour=14)
    with patch("models.model_overwhelm.nilai", return_value=Risiko(0, "tenang", "prior")):
        with patch("app.core.kalem_engine.check_status", return_value=status):
            at_nine = decide({"name": "Ari", "productive_hours": []}, day, now=morning)
            at_two = decide({"name": "Ari", "productive_hours": []}, day, now=afternoon)
    check(at_nine.action_kind == "med_taken",
          "pengingat obat masih muncul pada jendela pagi yang relevan")
    check(at_two.action_kind == "focus" and at_two.task and at_two.task["id"] == "med-task",
          "di luar jendela pengingat, task kembali menjadi keputusan utama")


def scenario_meal_modal_hides_decision_logging() -> None:
    print("\n=== Prompt makan menjadi satu-satunya interruption ===")
    state = storage.load_state()
    state["profile"].update({"name": "Ari", "onboarded": True})
    storage.save_state(state)
    storage.add_mood_log("tenang", 4, 4)
    page = FakePage()
    with patch("app.views.home.storage.perlu_tanya_makan", return_value=True):
        home.build(page, lambda route: None)
    check(len(page.dialogs) == 1, "hanya modal makan yang tampil setelah check-in selesai")
    check(storage.get_decision_records() == [],
          "decision di balik modal makan belum dicatat sebagai shown")


def scenario_overwhelm_does_not_auto_open_reset() -> None:
    print("\n=== Overwhelm meringankan action tanpa menjadikan Reset otomatis ===")
    workload = task("heavy", "Kerjakan laporan", minutes=90)
    day = DayState(
        tasks_today=[workload],
        mood_logs=[{"date": clock.today().isoformat(), "score": 2, "energy": 2}],
        energy_level=2,
    )
    now = datetime.combine(clock.today(), datetime.min.time()).replace(hour=10)
    with patch("models.model_overwhelm.nilai", return_value=Risiko(0.45, "waspada", "prior")):
        decision = decide({"name": "Ari", "productive_hours": []}, day, now=now)
    check(decision.action_kind != "reset", "risk model tidak otomatis merekomendasikan Reset")
    check(decision.action_kind == "focus" and decision.focus_minutes <= 10,
          "overwhelm waspada masih boleh mendapat action kerja yang sangat ringan")


def scenario_reset_feedback_changes_next_decision() -> None:
    print("\n=== Reset dinilai dari outcome user, bukan sekadar dibuka ===")
    add_event = storage.add_reset_event("napas")
    check(add_event.get("completed") is False,
          "memilih aktivitas Reset belum dianggap menyelesaikan recovery")
    complete = getattr(storage, "complete_reset_event", None)
    check(callable(complete), "storage mendukung after-state Reset")
    if not callable(complete):
        return

    complete(add_event["id"], improved=True)
    event = storage.get_reset_events()[0]
    check(event.get("completed") is True and event.get("improved") is True,
          "jawaban user bahwa kondisi membaik menjadi success signal Reset")

    workload = task("reset-task", "Kerjakan laporan praktikum", minutes=90)
    day = DayState(
        tasks_today=[workload],
        mood_logs=[{"date": clock.today().isoformat(), "score": 3, "energy": 4}],
        energy_level=4,
        reset_events=[event],
    )
    now = datetime.combine(clock.today(), datetime.min.time()).replace(hour=10)
    with patch("models.model_overwhelm.nilai", return_value=Risiko(0, "tenang", "prior")):
        decision = decide({"name": "Ari", "productive_hours": []}, day, now=now)
    check(decision.action_kind == "focus" and decision.focus_minutes < 20,
          "Reset membaik menghasilkan next action yang lebih ringan")

    second = storage.add_reset_event("grounding")
    complete(second["id"], improved=False)
    day.reset_events = storage.get_reset_events()
    with patch("models.model_overwhelm.nilai", return_value=Risiko(0, "tenang", "prior")):
        not_better = decide({"name": "Ari", "productive_hours": []}, day, now=now)
    check(not_better.action_kind not in {"focus", "reset"},
          "Reset yang tidak membantu tidak memaksa produktivitas atau membuka Reset lagi")


def scenario_focus_outcome_updates_exact_step() -> None:
    print("\n=== Post-focus outcome memperbarui task identity yang tepat ===")
    real = storage.add_task(
        "Tugas kembar",
        clock.today().isoformat(),
        steps=[{"text": "Langkah asli", "done": False}, {"text": "Langkah dua", "done": False}],
        kategori="Kuliah",
    )
    storage.add_task(
        "Tugas kembar",
        clock.today().isoformat(),
        steps=[{"text": "Langkah decoy", "done": False}],
        kategori="Rumah",
    )
    finish = getattr(focus_session, "finish", None)
    check(callable(finish), "focus session menyediakan penyelesaian dengan outcome eksplisit")
    if not callable(finish):
        return

    focus_session.start(
        10,
        label="Langkah asli",
        task_title=real["title"],
        task_id=real["id"],
        step_index=0,
        kategori="Kuliah",
    )
    internal = focus_session._state()
    internal.ends_at = None
    internal.paused_left = 300
    record = finish("completed")
    updated = next(item for item in storage.get_tasks() if item["id"] == real["id"])
    decoy = next(item for item in storage.get_tasks() if item["id"] != real["id"])
    check(updated["steps"][0]["done"] is True and updated["steps"][1]["done"] is False,
          "outcome Selesai hanya menutup step yang dikerjakan")
    check(decoy["steps"][0]["done"] is False,
          "duplicate title tidak membuat task lain ikut berubah")
    check(record and record.get("outcome") == "completed" and record.get("task_id") == real["id"],
          "focus record menyimpan outcome dan task_id, bukan hanya judul/durasi")


def scenario_focus_outcome_preserves_recurring_and_incomplete() -> None:
    print("\n=== Outcome fokus menjaga recurring occurrence dan progress belum selesai ===")
    today = clock.today().isoformat()
    recurring = storage.add_task(
        "Review mingguan",
        today,
        steps=[{"text": "Buka catatan minggu ini", "done": False}],
        repeat="weekly",
    )
    occurrence = next(item for item in storage.tasks_for(today) if item["id"] == recurring["id"])
    focus_session.start(
        10,
        label=occurrence["steps"][0]["text"],
        task_title=occurrence["title"],
        task_id=occurrence["id"],
        occurrence_date=occurrence["_occurrence_date"],
        step_index=0,
    )
    internal = focus_session._state()
    internal.ends_at = None
    internal.paused_left = 300
    focus_session.finish("completed")
    this_week = next(item for item in storage.tasks_for(today) if item["id"] == recurring["id"])
    next_week_date = (clock.today() + timedelta(days=7)).isoformat()
    next_week = next(
        item for item in storage.tasks_for(next_week_date) if item["id"] == recurring["id"]
    )
    check(storage.task_is_done(this_week), "Selesai hanya menutup occurrence minggu ini")
    check(not storage.task_is_done(next_week), "occurrence minggu berikutnya tetap terbuka")

    one_off = storage.add_task(
        "Tugas belum selesai",
        today,
        steps=[{"text": "Buka draf", "done": False}],
    )
    for outcome in ("incomplete", "later", "blocked"):
        focus_session.start(
            10,
            label="Buka draf",
            task_title=one_off["title"],
            task_id=one_off["id"],
            step_index=0,
        )
        internal = focus_session._state()
        internal.ends_at = None
        internal.paused_left = 300
        focus_session.finish(outcome)
    stored = next(item for item in storage.get_tasks() if item["id"] == one_off["id"])
    check(not stored["steps"][0]["done"],
          "Belum selesai/Terhambat/Lanjut nanti tidak menutup step")

    profile = {"name": "Ari", "productive_hours": []}
    day = DayState(
        tasks_today=[stored],
        mood_logs=[{"date": today, "score": 4, "energy": 4}],
        energy_level=4,
        focus_records=storage.get_focus_records(),
    )
    now = datetime.combine(clock.today(), datetime.min.time()).replace(hour=13)
    with patch("models.model_overwhelm.nilai", return_value=Risiko(0, "tenang", "prior")):
        after_blocked = decide(profile, day, now=now)
    check(after_blocked.task and after_blocked.task["id"] == one_off["id"]
          and after_blocked.focus_minutes == 5,
          "Terhambat membuat decision berikutnya mengecil tanpa mengganti task identity")


def scenario_decision_lifecycle_without_feature_leakage() -> None:
    print("\n=== Decision lifecycle tetap memisahkan decision-time dan outcome-time ===")
    record_id = storage.record_decision_shown(
        "next_action", "focus", {"energi_terakhir": 2}, "FOKUS 10 menit",
        task_id="task-a", step_index=0,
    )
    started = getattr(storage, "record_decision_started", None)
    outcome = getattr(storage, "record_decision_outcome", None)
    check(callable(started) and callable(outcome),
          "decision record memisahkan shown, acted, started, dan completed")
    if not callable(started) or not callable(outcome):
        return
    started(record_id)
    outcome(record_id, completed=True)
    record = next(item for item in storage.get_decision_records() if item["id"] == record_id)
    check(record.get("started") is True and record.get("completed") is True,
          "started/completed tercatat sebagai outcome terpisah")
    check(record["fitur"]["energi_terakhir"] == 2.0,
          "outcome tidak menimpa feature snapshot saat decision dibuat")


def scenario_tracker_progress_re_evaluates_decision() -> None:
    print("\n=== Perubahan langkah di Tracker menjalankan decision loop lagi ===")
    saved = storage.add_task(
        "Bereskan satu langkah",
        clock.today().isoformat(),
        steps=[{"text": "Buka catatan", "done": False}],
    )
    root = tracker.build(FakePage(), lambda route: None)
    checkbox = next(
        (
            control for control in walk_controls(root)
            if getattr(control, "label", None) == "Buka catatan"
        ),
        None,
    )
    check(checkbox is not None, "checkbox langkah ditemukan di Tracker nyata")
    if checkbox is None:
        return
    from app.core import kalem_engine

    with patch("app.views.tracker.kalem_engine.decide", wraps=kalem_engine.decide) as rerun:
        checkbox.on_change(SimpleNamespace(control=SimpleNamespace(value=True)))
    updated = next(item for item in storage.get_tasks() if item["id"] == saved["id"])
    check(updated["steps"][0]["done"] is True, "perubahan langkah benar-benar tersimpan")
    check(rerun.call_count == 1, "state baru langsung dievaluasi ulang oleh KALEM")


def main() -> int:
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    with tempfile.TemporaryDirectory(prefix="focusbuddy_daily_flow_") as directory:
        storage.DATA_DIR = Path(directory)
        storage.DATA_FILE = storage.DATA_DIR / "data.json"
        storage.BACKUP_FILE = storage.DATA_DIR / "data.json.bak"
        storage.reset_all_data()
        try:
            scenario_checkin_before_brief_and_decision()
            storage.reset_all_data()
            scenario_deadline_progress_with_small_capacity()
            storage.reset_all_data()
            scenario_capacity_none_and_zero_are_distinct()
            storage.reset_all_data()
            scenario_medication_only_when_relevant()
            storage.reset_all_data()
            scenario_meal_modal_hides_decision_logging()
            storage.reset_all_data()
            scenario_overwhelm_does_not_auto_open_reset()
            storage.reset_all_data()
            scenario_reset_feedback_changes_next_decision()
            storage.reset_all_data()
            scenario_focus_outcome_updates_exact_step()
            storage.reset_all_data()
            scenario_focus_outcome_preserves_recurring_and_incomplete()
            storage.reset_all_data()
            scenario_decision_lifecycle_without_feature_leakage()
            storage.reset_all_data()
            scenario_tracker_progress_re_evaluates_decision()
        finally:
            storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"GAGAL: {len(FAILURES)} kontrak daily flow belum terpenuhi")
        return 1
    print("SEMUA KONTRAK DAILY FLOW LULUS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
