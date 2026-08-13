"""Behavior contract untuk Home, task-based Focus, dan quick capture."""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

from app import clock, focus_session, storage
from app.core import kalem_engine
from app.core.kalem_engine import DayState
from app.views import home
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
    yield from walk(getattr(control, "content", None))


def button(root, prefix: str):
    for control in walk(root):
        if getattr(control, "on_click", None) is None:
            continue
        content = getattr(control, "content", None)
        text = getattr(content, "value", None)
        if isinstance(text, str) and text.startswith(prefix):
            return control
    return None


def texts(root) -> list[str]:
    return [
        control.value
        for control in walk(root)
        if isinstance(getattr(control, "value", None), str)
    ]


def make_task(
    task_id: str,
    title: str,
    minutes: int,
    *,
    steps: list[dict] | None = None,
    deadline: str | None = None,
    difficulty: int = 2,
) -> dict:
    return {
        "id": task_id,
        "title": title,
        "deadline": deadline if deadline is not None else clock.today().isoformat(),
        "deadline_time": "23:59",
        "important": True,
        "difficulty_est": difficulty,
        "menit_est": minutes,
        "created_at": clock.now().isoformat(),
        "repeat": "none",
        "steps": steps or [{"id": f"step-{task_id}", "text": f"Mulai {title}", "done": False}],
    }


def stable_day(tasks: list[dict], energy: int, records: list[dict] | None = None) -> DayState:
    return DayState(
        tasks_today=tasks,
        mood_logs=[{
            "date": clock.today().isoformat(), "mood": "tenang",
            "score": 4, "energy": energy,
        }],
        energy_level=energy,
        focus_records=records or [],
    )


def decide(day: DayState, now: datetime | None = None, profile: dict | None = None):
    with patch("models.model_overwhelm.nilai", return_value=Risiko(0, "tenang", "test")):
        return kalem_engine.decide(
            profile or {"name": "Ari", "productive_hours": []},
            day,
            now=now,
        )


def scenario_task_based_duration_and_remaining() -> None:
    print("\n=== Durasi Focus berasal dari task lalu dimodifikasi kondisi ===")
    five = decide(stable_day([make_task("five", "Task lima menit", 5)], 6))
    check(five.focus_minutes == 5, "task estimasi 5 menit menghasilkan sesi 5 menit")

    forty_five = decide(stable_day([make_task("45", "Task 45 menit", 45)], 6))
    check(20 <= forty_five.focus_minutes <= 25,
          "task 45 menit menjadi satu sesi Pomodoro yang masuk akal, bukan 45 menit")

    ninety = decide(stable_day([make_task("90", "Task 90 menit", 90)], 6))
    check(ninety.focus_minutes <= 25, "task 90 menit dipecah menjadi beberapa sesi")

    record = {
        "task_id": "45", "step_index": 0, "occurrence_date": "",
        "menit": 25, "outcome": "incomplete", "date": clock.today().isoformat(),
    }
    remaining = decide(stable_day([make_task("45", "Task 45 menit", 45)], 6, [record]))
    check(remaining.focus_minutes == 20 and remaining.remaining_minutes == 20,
          "focus history mengurangi remaining estimate sesi berikutnya")


def scenario_home_message_is_state_based() -> None:
    print("\n=== Pesan Home deterministik dan tidak selalu sama ===")
    now = datetime.combine(clock.today(), datetime.min.time()).replace(hour=10)
    task = make_task("copy", "Tugas normal", 20)
    normal = decide(stable_day([task], 4), now, {"name": "Ari", "productive_hours": [[9, 12]]})
    outside = decide(stable_day([task], 4), now, {"name": "Ari", "productive_hours": [[18, 22]]})
    low = decide(stable_day([task], 1), now, {"name": "Ari", "productive_hours": [[9, 12]]})
    workload = decide(
        stable_day([make_task(str(i), f"Beban {i}", 60) for i in range(4)], 4),
        now,
        {"name": "Ari", "productive_hours": [[9, 12]]},
    )
    check(normal.message == "", "kondisi normal tidak diberi motivasi generik")
    check(len({outside.message, low.message, workload.message}) == 3,
          "jam produktif, energi rendah, dan workload tinggi menghasilkan konteks berbeda")


def scenario_timer_and_done_update_real_task() -> None:
    print("\n=== Timer tidak menyelesaikan task; DONE menyelesaikan identity yang tepat ===")
    today = clock.today().isoformat()
    first = storage.add_task(
        "Tugas kembar", today, difficulty_est=1, menit_est=10, kategori="Benar",
        steps=[{"id": "step-benar", "text": "Langkah benar", "done": False}],
    )
    decoy = storage.add_task(
        "Tugas kembar", today, difficulty_est=3, menit_est=40, kategori="Decoy",
        steps=[{"id": "step-decoy", "text": "Langkah decoy", "done": False}],
    )
    second = storage.add_task(
        "Tugas berikutnya", today, difficulty_est=2, menit_est=15,
        steps=[{"id": "step-next", "text": "Langkah berikutnya", "done": False}],
    )
    decision = decide(kalem_engine.snapshot()[1])
    check(decision.task and decision.task["id"] == first["id"],
          "Home decision menggunakan task asli yang dipilih dari Tracker")

    focus_session.start(
        decision.focus_minutes,
        label=decision.step_text,
        task_title=decision.detail,
        task_id=first["id"],
        step_id="step-benar",
        step_index=0,
    )
    internal = focus_session._state()
    internal.ends_at = datetime.now() - timedelta(seconds=1)
    focus_session.just_finished()
    still_open = next(item for item in storage.get_tasks() if item["id"] == first["id"])
    check(not still_open["steps"][0]["done"], "timer habis tidak otomatis menyelesaikan step")

    record = focus_session.finish("completed")
    updated = next(item for item in storage.get_tasks() if item["id"] == first["id"])
    untouched = next(item for item in storage.get_tasks() if item["id"] == decoy["id"])
    check(updated["steps"][0]["done"], "DONE langsung memperbarui state Tracker")
    check(not untouched["steps"][0]["done"], "judul kembar tidak mengubah task ID lain")
    check(record is not None and all(record.get(key) not in (None, "") for key in (
        "task_id", "step_id", "session_started_at", "session_ended_at", "outcome",
    )), "focus record menyimpan identity serta awal/akhir sesi")
    check(record and record.get("task_completed") is True,
          "focus record menyimpan status completion task")
    check(focus_session.finish("completed") is None,
          "DONE kedua tidak membuat duplicate completion record")
    check(len([
        item for item in storage.get_focus_records()
        if item.get("task_id") == first["id"] and item.get("outcome") == "completed"
    ]) == 1, "completion event hanya tersimpan satu kali")

    next_decision = decide(kalem_engine.snapshot()[1])
    check(next_decision.task and next_decision.task["id"] == second["id"],
          "task DONE tidak dipilih lagi dan KALEM memilih task berikutnya")


def scenario_focus_ui_has_done_and_is_compact() -> None:
    print("\n=== Home ringkas dan Focus menyediakan DONE langsung ===")
    today = clock.today().isoformat()
    task = storage.add_task(
        "Tulis laporan", today, menit_est=20,
        steps=[{"id": "step-ui", "text": "Buka laporan", "done": False}],
    )
    normal_root = home.build(FakePage(), lambda route: None)
    normal_text = texts(normal_root)
    check(
        all(expected in normal_text for expected in (
            "Ayo, Sekarang kerjain ini dulu", "Tulis laporan", "Buka laporan",
        ))
        and any(
            text.startswith("Sisa estimasi ~20 menit · sesi ini ")
            for text in normal_text
        ),
        "card Home ringkas menampilkan title, step, remaining, dan sesi dari Tracker",
    )

    focus_session.start(
        20, label="Buka laporan", task_title=task["title"],
        task_id=task["id"], step_id="step-ui", step_index=0,
    )
    routes: list[str] = []
    root = home.build(FakePage(), routes.append)
    done = button(root, "DONE")
    check(done is not None, "tombol DONE tersedia saat timer masih berjalan")
    visible = texts(root)
    check(all(text in visible for text in (
        "Hai! Ari", "Ada yang Keingat?", "Kewalahan? YUK AMBIL JEDA",
    )), "saat Focus aktif shell Home tetap tampil seperti biasa")
    check(button(root, "Jeda") is not None and button(root, "Akhiri sesi") is not None,
          "kontrol Jeda, DONE, dan Akhiri sesi terlihat di kartu Focus")
    check(not any(isinstance(control, ft.ProgressBar) for control in walk(root)),
          "Focus tidak menampilkan progress bar abu-abu yang redundan")
    if done is not None:
        state = focus_session._state()
        state.ends_at = None
        state.paused_left = 5 * 60
        done.on_click(SimpleNamespace(control=None))
        updated = next(item for item in storage.get_tasks() if item["id"] == task["id"])
        check(updated["steps"][0]["done"] and routes[-1] == "home",
              "smoke Home → Focus → DONE menyimpan Tracker lalu kembali memilih action")


def scenario_done_continues_next_step_same_task() -> None:
    print("\n=== DONE melanjutkan step berikutnya dari parent task yang sama ===")
    today = clock.today().isoformat()
    parent = storage.add_task(
        "Kerjakan latihan", today, menit_est=30, difficulty_est=1,
        steps=[
            {"id": "step-parent-1", "text": "Buka soal", "done": False},
            {"id": "step-parent-2", "text": "Kerjakan nomor satu", "done": False},
        ],
    )
    other = storage.add_task(
        "Tugas berbeda", today, menit_est=5, difficulty_est=3,
        steps=[{"id": "step-other", "text": "Mulai tugas lain", "done": False}],
    )
    focus_session.start(
        15,
        label="Buka soal",
        task_title=parent["title"],
        task_id=parent["id"],
        step_id="step-parent-1",
        step_index=0,
        energi=4,
    )

    routes: list[str] = []
    first_root = home.build(FakePage(), routes.append)
    first_done = button(first_root, "DONE")
    check(first_done is not None, "DONE tersedia untuk step pertama")
    if first_done is None:
        return
    first_done.on_click(SimpleNamespace(control=None))

    stored_parent = next(item for item in storage.get_tasks() if item["id"] == parent["id"])
    continued = focus_session.snapshot()
    check(stored_parent["steps"][0]["done"] and not stored_parent["steps"][1]["done"],
          "DONE hanya menyelesaikan step aktif")
    check(
        continued["active"]
        and continued["task_id"] == parent["id"]
        and continued["step_id"] == "step-parent-2"
        and continued["label"] == "Kerjakan nomor satu",
        "Focus otomatis lanjut ke step berikutnya dari parent task yang sama",
    )
    check(continued["task_id"] != other["id"],
          "task lain tidak diselipkan di tengah rangkaian parent task")
    first_done.on_click(SimpleNamespace(control=None))
    after_stale_tap = focus_session.snapshot()
    stored_parent = next(item for item in storage.get_tasks() if item["id"] == parent["id"])
    check(
        after_stale_tap["active"]
        and after_stale_tap["step_id"] == "step-parent-2"
        and not stored_parent["steps"][1]["done"],
        "double-tap dari tombol DONE lama tidak ikut menyelesaikan step baru",
    )

    second_root = home.build(FakePage(), routes.append)
    second_done = button(second_root, "DONE")
    check(second_done is not None, "DONE tersedia untuk step kedua")
    if second_done is not None:
        second_done.on_click(SimpleNamespace(control=None))
    stored_parent = next(item for item in storage.get_tasks() if item["id"] == parent["id"])
    check(storage.task_is_done(stored_parent) and not focus_session.is_active(),
          "setelah seluruh parent selesai, Focus ditutup seperti behavior sebelumnya")
    next_decision = decide(kalem_engine.snapshot()[1])
    check(next_decision.task and next_decision.task["id"] == other["id"],
          "task berbeda baru ditampilkan sebagai next action setelah parent selesai")

    records = [
        record for record in storage.get_focus_records()
        if record.get("task_id") == parent["id"] and record.get("outcome") == "completed"
    ]
    check(
        len(records) == 2
        and {record.get("step_id") for record in records}
        == {"step-parent-1", "step-parent-2"},
        "setiap step menyimpan focus record sendiri tanpa kehilangan identity",
    )


def scenario_done_continues_recurring_occurrence() -> None:
    print("\n=== Continuation menjaga identity recurring occurrence ===")
    today = clock.today().isoformat()
    recurring = storage.add_task(
        "Rutinitas mingguan",
        today,
        repeat="weekly",
        menit_est=20,
        steps=[
            {"id": "repeat-step-1", "text": "Bagian pertama", "done": False},
            {"id": "repeat-step-2", "text": "Bagian kedua", "done": False},
        ],
    )
    focus_session.start(
        10,
        label="Bagian pertama",
        task_title=recurring["title"],
        task_id=recurring["id"],
        step_id="repeat-step-1",
        occurrence_date=today,
        step_index=0,
    )
    root = home.build(FakePage(), lambda route: None)
    done = button(root, "DONE")
    check(done is not None, "DONE tersedia pada recurring occurrence")
    if done is None:
        return
    done.on_click(SimpleNamespace(control=None))
    continued = focus_session.snapshot()
    check(
        continued["active"]
        and continued["task_id"] == recurring["id"]
        and continued["occurrence_date"] == today
        and continued["step_id"] == "repeat-step-2",
        "step recurring berikutnya tetap memakai parent dan occurrence yang sama",
    )
    next_week = (clock.today() + timedelta(days=7)).isoformat()
    future = next(
        task for task in storage.tasks_for(next_week)
        if task["id"] == recurring["id"]
    )
    check(not any(step.get("done") for step in future["steps"]),
          "continuation minggu ini tidak mengubah occurrence minggu depan")


def scenario_timer_finished_offers_outcomes() -> None:
    print("\n=== Timer selesai meminta outcome, bukan menebak completion ===")
    today = clock.today().isoformat()
    task = storage.add_task(
        "Baca materi", today, menit_est=45,
        steps=[{"id": "step-outcome", "text": "Baca bab satu", "done": False}],
    )
    focus_session.start(
        25, label="Baca bab satu", task_title=task["title"],
        task_id=task["id"], step_id="step-outcome", step_index=0,
    )
    state = focus_session._state()
    state.ends_at = datetime.now() - timedelta(seconds=1)
    root = home.build(FakePage(), lambda route: None)
    visible = texts(root)
    check(all(label in visible for label in (
        "Sudah selesai", "Masih butuh waktu", "Terhambat", "Lanjut nanti",
    )), "timer habis menampilkan pilihan outcome yang eksplisit")
    stored = next(item for item in storage.get_tasks() if item["id"] == task["id"])
    check(not stored["steps"][0]["done"],
          "membuka layar outcome setelah timer habis tidak menyelesaikan task")


def scenario_tracker_start_uses_same_pomodoro_rule() -> None:
    print("\n=== Jalur Tracker memakai aturan sesi task-based yang sama ===")
    from app.views import tracker

    today = clock.today().isoformat()
    task = storage.add_task(
        "Tugas panjang", today, menit_est=90,
        steps=[{"id": "step-tracker", "text": "Mulai tugas panjang", "done": False}],
    )
    root = tracker.build(FakePage(), lambda route: None)
    start = button(root, "Mulai")
    check(start is not None, "tombol Mulai task tersedia di Tracker")
    if start is not None:
        start.on_click(SimpleNamespace(control=None))
        snapshot = focus_session.snapshot()
        check(snapshot["task_id"] == task["id"] and snapshot["total_seconds"] <= 25 * 60,
              "task 90 menit dari Tracker tetap dipecah menjadi sesi maksimal 25 menit")


def scenario_multiple_diary_and_quick_capture() -> None:
    print("\n=== Quick capture tersimpan sebagai note sebelum dijadikan task ===")
    add_entry = getattr(storage, "add_diary_entry", None)
    check(callable(add_entry), "storage menyediakan diary multi-entry")
    if callable(add_entry):
        add_entry("Hari ini aku capek setelah kelas", source="quick_capture")
        add_entry("Tapi sore ini aku merasa lebih lega", source="quick_capture")
        today_entries = [
            entry for entry in storage.diary_entries()
            if entry.get("date") == clock.today().isoformat()
        ]
        check(len(today_entries) == 2, "dua cerita pada hari yang sama tidak saling overwrite")

    routes: list[str] = []
    page = FakePage()
    root = home.build(page, routes.append)
    capture = button(root, "Ada yang Keingat?")
    check(capture is not None, "quick capture tersedia di Home normal")
    if capture is not None:
        capture.on_click(SimpleNamespace(control=None))
        dialog = page.dialogs[-1]
        dialog_text = texts(dialog)
        check(
            "Apapun yang kamu mau ingat" in dialog_text
            and "Kamu boleh tulis apapun, tugas, cerita, atau apapun itu" in dialog_text,
            "dialog catatan menggunakan copy yang baru",
        )
        field = next(control for control in walk(dialog) if isinstance(control, ft.TextField))
        save = button(dialog, "Simpan")
        note_text = "Balas email dosen setelah makan siang"
        diary_count = len(storage.diary_entries())
        field.value = note_text
        save.on_click(SimpleNamespace(control=None))
        notes = storage.get_inbox()
        check(
            routes[-1] == "home"
            and len(notes) == 1
            and notes[0]["text"] == note_text,
            "Home → quick capture menyimpan isi mentah sebagai note lalu tetap di Home",
        )
        check(
            len(storage.diary_entries()) == diary_count and not storage.get_tasks(),
            "note tidak otomatis masuk Diary atau menjadi task",
        )

        refreshed_home = home.build(page, routes.append)
        open_notes = button(refreshed_home, "1 tersimpan")
        check(open_notes is not None, "Home menampilkan akses untuk membuka note tersimpan")
        if open_notes is not None:
            open_notes.on_click(SimpleNamespace(control=None))
            check(routes[-1] == "inbox", "note dibuka melalui halaman Catatan Kamu")

        from app.views import inbox

        inbox_root = inbox.build(page, routes.append)
        inbox_text = texts(inbox_root)
        check(
            "Catatan Kamu" in inbox_text
            and note_text in inbox_text
            and "Catatan mentah yang belum jadi tugas" not in inbox_text
            and "Nggak ada kewajiban ngosongin daftar ini" not in inbox_text,
            "halaman Catatan Kamu hanya menampilkan judul dan isi catatan",
        )
        convert = button(inbox_root, "Jadiin tugas")
        check(convert is not None, "note menyediakan opsi Jadiin tugas")
        if convert is not None:
            convert.on_click(SimpleNamespace(control=None))
            task_dialog = page.dialogs[-1]
            split = next(
                control for control in walk(task_dialog)
                if isinstance(control, ft.Checkbox)
                and str(control.label).startswith("Pecah otomatis")
            )
            split.value = False
            submit = button(task_dialog, "Jadiin tugas")
            submit.on_click(SimpleNamespace(control=None))
            tasks = storage.get_tasks()
            check(
                len(tasks) == 1
                and tasks[0]["title"] == note_text
                and not storage.get_inbox(),
                "note baru menjadi task setelah user memilih konversi",
            )
            empty_inbox = inbox.build(page, routes.append)
            check(
                "Masih kosong nihh" in texts(empty_inbox),
                "halaman Catatan Kamu menampilkan copy kosong yang baru",
            )


def scenario_navigation_is_locked_while_active() -> None:
    print("\n=== Navigation terkunci selama sesi aktif, termasuk saat pause ===")
    import app.main as main

    allowed = getattr(main, "focus_navigation_allowed", None)
    visible = getattr(main, "main_navigation_visible", None)
    check(callable(allowed), "navigation guard dapat diuji langsung")
    check(callable(visible), "visibility navigation dapat diuji langsung")
    if not callable(allowed) or not callable(visible):
        return
    focus_session.start(10, label="Kerjakan task")
    check(visible("home"), "navigation bawah tetap terlihat di Home selama Focus")
    check(not allowed("tracker") and not allowed("mood") and not allowed("reset"),
          "semua halaman selain Focus/Home terkunci saat timer berjalan")
    focus_session.pause()
    check(not allowed("tracker"), "pause tidak membuka navigation utama")
    check(allowed("home"), "route internal Home tetap boleh untuk merender Focus Session")
    focus_session.stop()
    check(allowed("tracker"), "navigation terbuka lagi setelah sesi benar-benar diakhiri")


def main() -> int:
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    with tempfile.TemporaryDirectory(prefix="focusbuddy_home_focus_") as directory:
        storage.DATA_DIR = Path(directory)
        storage.DATA_FILE = storage.DATA_DIR / "data.json"
        storage.BACKUP_FILE = storage.DATA_DIR / "data.json.bak"
        try:
            for scenario in (
                scenario_task_based_duration_and_remaining,
                scenario_home_message_is_state_based,
                scenario_timer_and_done_update_real_task,
                scenario_focus_ui_has_done_and_is_compact,
                scenario_done_continues_next_step_same_task,
                scenario_done_continues_recurring_occurrence,
                scenario_timer_finished_offers_outcomes,
                scenario_tracker_start_uses_same_pomodoro_rule,
                scenario_multiple_diary_and_quick_capture,
                scenario_navigation_is_locked_while_active,
            ):
                storage.reset_all_data()
                focus_session.stop()
                state = storage.load_state()
                state["profile"].update({"name": "Ari", "onboarded": True})
                storage.save_state(state)
                storage.add_mood_log("tenang", 4, 4, ate_today=True, rested_enough=True)
                scenario()
        finally:
            focus_session.stop()
            storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"GAGAL: {len(FAILURES)} behavior Home/Focus belum terpenuhi")
        return 1
    print("SEMUA BEHAVIOR HOME/FOCUS LULUS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
