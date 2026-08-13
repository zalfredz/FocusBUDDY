"""Acceptance contract untuk revisi besar Tracker FocusBuddy."""
from __future__ import annotations

import asyncio
import re
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

from app import clock, focus_session, storage, theme
from app.core import decomposer_logic, kalem_engine
from app.views import tracker


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


class ImmediatePage(FakePage):
    def run_task(self, fn, *args) -> None:
        asyncio.run(fn(*args))


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
    yield from walk(getattr(control, "suffix", None))


def texts(root) -> list[str]:
    return [
        control.value
        for control in walk(root)
        if isinstance(getattr(control, "value", None), str)
    ]


def clickable(root, label: str):
    for control in walk(root):
        if getattr(control, "on_click", None) is None:
            continue
        content = getattr(control, "content", None)
        if getattr(content, "value", None) == label:
            return control
    return None


def by_tooltip(root, tooltip: str) -> list:
    return [
        control for control in walk(root)
        if getattr(control, "tooltip", None) == tooltip
    ]


def calendar_cell(root, day_number: int):
    for control in walk(root):
        if (
            getattr(control, "height", None) not in (32, 42)
            or getattr(control, "on_click", None) is None
        ):
            continue
        if str(day_number) in texts(control):
            return control
    return None


def add_task(
    title: str,
    scheduled: date,
    *,
    deadline: date | None,
    deadline_time: str = "23:59",
    important: bool = True,
    difficulty: int = 2,
    steps: list[dict] | None = None,
    description: str = "",
) -> dict:
    return storage.add_task(
        title,
        deadline.isoformat() if deadline else "",
        important=important,
        deadline_time=deadline_time if deadline else "",
        difficulty_est=difficulty,
        menit_est=20,
        scheduled_date=scheduled.isoformat(),
        steps=steps or [{"text": f"Mulai {title}", "done": False}],
        description=description,
    )


def scenario_calendar_modes_and_done() -> None:
    print("\n=== A-E: Calendar, mode reversibel, dan DONE nyata ===")
    today = clock.today()
    week_start = today - timedelta(days=today.weekday())
    another_weekday = week_start + timedelta(days=3 if today.weekday() != 3 else 4)
    month_only = week_start + timedelta(days=8)
    if month_only.month != today.month:
        month_only = date(today.year, today.month, max(1, today.day - 7))

    daily = add_task("Tugas tanggal pilihan", today, deadline=today)
    weekly = add_task("Tugas lain minggu ini", another_weekday, deadline=another_weekday)
    monthly = add_task("Tugas lain bulan ini", month_only, deadline=month_only)
    done = add_task(
        "Tugas sudah selesai", today, deadline=today,
        steps=[{"text": "Sudah dikerjakan", "done": True}],
    )

    page = FakePage()
    root = tracker.build(page, lambda route: None)
    visible = texts(root)
    check(
        f"{tracker.MONTH_NAMES[today.month - 1]} {today.year}" in visible,
        "kalender mingguan memakai nama bulan lengkap tanpa rentang tanggal singkat",
    )
    check(
        all(day in visible for day in tracker.DAY_SHORT),
        "kalender mingguan menampilkan nama hari yang jelas",
    )
    check(
        any(
            isinstance(control, ft.Container) and control.bgcolor == "#DDE0FF"
            for control in walk(root)
        ),
        "baris tanggal mingguan dibedakan dengan warna terang",
    )
    check(
        any("Istirahat juga termasuk progress" in value for value in visible)
        or "Semangat untuk Hari Ini!" in visible,
        "Tracker menampilkan mascot dan bubble kondisi seperti Home",
    )
    check(daily["title"] in visible and weekly["title"] not in visible,
          "mode Mingguan tetap menampilkan card tugas aktif untuk hari terpilih saja")
    check("2 aktif · 1 selesai" in visible,
          "mode Mingguan hanya memperluas hitungan Sebaran Tugas")
    check(any("selesai" in value.lower() for value in visible)
          and "Tugas sudah selesai" in visible,
          "Sebaran dan card memakai status task yang benar-benar selesai")
    check(
        visible.index("Pecah Tugas") < visible.index("SEBARAN TUGAS")
        < visible.index("FOCUS HISTORY"),
        "Sebaran Tugas tepat di bawah tombol Tambah/Pecah Tugas",
    )

    target_cell = calendar_cell(root, another_weekday.day)
    check(target_cell is not None, "tanggal spesifik di kalender minggu dapat dipilih")
    if target_cell is not None:
        target_cell.on_click(SimpleNamespace(control=target_cell))
        visible = texts(root)
        check(weekly["title"] in visible and daily["title"] not in visible,
              "memilih tanggal otomatis pindah ke Harian dan hanya menampilkan tanggal itu")

    weekly_chip = clickable(root, "Mingguan")
    if weekly_chip is not None:
        weekly_chip.on_click(SimpleNamespace(control=weekly_chip))
    expand = clickable(root, "Bulan Ini")
    check(expand is not None, "calendar ringkas menyediakan tombol Bulan Ini")
    if expand is not None:
        expand.on_click(SimpleNamespace(control=expand))
    visible = texts(root)
    check(monthly["title"] not in visible,
          "membesarkan kalender tidak mengubah filter Mingguan")
    monthly_chip = clickable(root, "Bulanan")
    if monthly_chip is not None:
        monthly_chip.on_click(SimpleNamespace(control=monthly_chip))
    monthly_visible = texts(root)
    check(monthly["title"] not in monthly_visible and "3 aktif · 1 selesai" in monthly_visible,
          "filter Bulanan hanya mengubah Sebaran Tugas, bukan card tugas aktif")
    collapse = clickable(root, "Ringkas kalender")
    check(collapse is not None, "kalender bulanan punya kontrol ukuran sendiri")
    if collapse is not None:
        collapse.on_click(SimpleNamespace(control=collapse))
    check(monthly["title"] not in texts(root) and clickable(root, "Bulan Ini") is not None,
          "meringkas kalender tidak mengubah filter Bulanan")


def scenario_deadline_and_no_deadline() -> None:
    print("\n=== F-H: Deadline, overdue, dan task tanpa deadline ===")
    today = clock.today()
    overdue = add_task("Overdue", today, deadline=today - timedelta(days=2))
    close = add_task("Deadline dekat", today, deadline=today, deadline_time="23:59")
    far = add_task("Deadline jauh", today, deadline=today + timedelta(days=8))
    undated = add_task("Tanpa deadline", today, deadline=None)

    ranked = kalem_engine.rank_actionable_tasks(storage.tasks_for(today.isoformat()))
    titles = [task["title"] for task in ranked]
    check(titles.index(overdue["title"]) < titles.index(close["title"]),
          "task overdue mendapat urgency lebih tinggi")
    check(titles.index(close["title"]) < titles.index(far["title"]),
          "deadline lebih dekat memengaruhi urutan canonical")
    check(titles.index(far["title"]) < titles.index(undated["title"]),
          "task tanpa deadline berada di belakang task dengan deadline relevan")
    check(storage.is_urgent(overdue) and not storage.is_urgent(undated),
          "overdue urgent, sedangkan task tanpa deadline tidak dikarang urgent")
    check(kalem_engine.pick_next_action(storage.tasks_for(today.isoformat()))[0]["id"] == overdue["id"],
          "KALEM dan Tracker memakai ranking canonical yang sama")

    with patch(
        "app.core.decomposer_logic.ai_client.generate_json",
        return_value=([{"tugas": close["title"], "langkah": "Buka bahan"}], ""),
    ) as generate:
        decomposer_logic._ai_steps([close], 4)
    prompt = generate.call_args.kwargs["prompt"]
    check("Deadline:" in prompt and close["deadline"] in prompt,
          "deadline nyata diteruskan ke decomposition")

    page = FakePage()
    root = tracker.build(page, lambda route: None)
    open_add = clickable(root, "Tambah Tugas")
    if open_add is not None:
        open_add.on_click(SimpleNamespace(control=open_add))
    dialog = page.dialogs[-1] if page.dialogs else None
    dialog_text = texts(dialog)
    check(
        "Seberat apa buat dimulai?" in dialog_text
        and "+ Kasih tau jenis & jumlahnya (opsional)" not in dialog_text
        and not any("Diisi -> Pecah Tugas" in value for value in dialog_text),
        "difficulty tetap tersedia dan teks bantuan yang tidak perlu sudah dihapus",
    )
    repeat_dropdown = next(
        (
            control
            for control in walk(dialog)
            if isinstance(control, ft.Dropdown) and control.label == "Tugas berulang"
        ),
        None,
    )
    check(
        repeat_dropdown is not None
        and [option.key for option in repeat_dropdown.options]
        == ["none", "daily", "weekly", "monthly"]
        and [option.text for option in repeat_dropdown.options]
        == ["Sekali", "Harian", "Mingguan", "Bulanan"],
        "dropdown tugas berulang menampilkan Sekali, bukan nilai internal none",
    )
    check(
        getattr(dialog, "bgcolor", None) == "#1C1C26",
        "dialog Tambah Tugas memakai latar gelap",
    )
    title_field = next(
        (control for control in walk(dialog) if isinstance(control, ft.TextField)
         and control.label == "Nama tugas"),
        None,
    )
    no_deadline = next(
        (control for control in walk(dialog) if isinstance(control, ft.Checkbox)
         and control.label == "Tanpa deadline"),
        None,
    )
    date_holder = next(
        (
            control
            for control in walk(dialog)
            if isinstance(control, ft.Column)
            and any(
                getattr(child, "value", None) == "Tanggal deadline"
                for child in control.controls
            )
        ),
        None,
    )
    time_holder = next(
        (
            control
            for control in walk(dialog)
            if isinstance(control, ft.Column)
            and any(
                getattr(child, "value", None) == "Jam deadline"
                for child in control.controls
            )
        ),
        None,
    )
    form_controls = getattr(getattr(dialog, "content", None), "controls", [])
    check(
        len(form_controls) == 3
        and "Nama + deskripsi" in texts(form_controls[0])
        and "Deadline" in texts(form_controls[1])
        and "Penting + tingkat kesulitan" in texts(form_controls[2])
        and no_deadline in list(walk(form_controls[1]))
        and date_holder in list(walk(form_controls[1]))
        and time_holder in list(walk(form_controls[1])),
        "form dibagi menjadi tiga card dan seluruh kontrol deadline tetap satu kelompok",
    )
    if title_field is not None and no_deadline is not None:
        title_field.value = "Task tanpa deadline dari UI"
        no_deadline.value = True
        no_deadline.on_change(SimpleNamespace(control=no_deadline))
        check(
            date_holder is not None
            and time_holder is not None
            and not date_holder.visible
            and not time_holder.visible,
            "tanggal dan jam disembunyikan ketika Tanpa deadline dicentang",
        )
        submit = clickable(dialog, "Tambah")
        submit.on_click(SimpleNamespace(control=submit))
    added = next(
        (task for task in storage.get_tasks() if task["title"] == "Task tanpa deadline dari UI"),
        None,
    )
    check(
        added is not None
        and added["deadline"] == ""
        and added["scheduled_date"] == today.isoformat(),
        "form Tracker memisahkan tanggal kerja dari deadline opsional",
    )


def scenario_task_input_supports_voice_description_and_time_picker() -> None:
    print("\n=== Input tugas: suara inline, tanggal, dan pemilih waktu ===")
    page = FakePage()
    root = tracker.build(page, lambda route: None)
    open_add = clickable(root, "Tambah Tugas")
    if open_add is not None:
        open_add.on_click(SimpleNamespace(control=open_add))
    dialog = page.dialogs[-1] if page.dialogs else None

    description_field = next(
        (
            control
            for control in walk(dialog)
            if isinstance(control, ft.TextField)
            and control.label == "Deskripsi (opsional)"
        ),
        None,
    )
    check(
        description_field is not None
        and description_field.bgcolor == "#343446"
        and description_field.color == theme.ON_BACKGROUND,
        "input nama dan deskripsi memakai field gelap dengan tulisan terang",
    )
    voice_button = next(
        (
            control
            for control in walk(dialog)
            if isinstance(control, ft.OutlinedButton)
            and control.icon == ft.Icons.MIC_NONE
            and control.tooltip == "Isi pakai suara · maksimal 120 detik"
        ),
        None,
    )
    check(
        voice_button is not None
        and "Isi deskripsi pakai suara" in texts(voice_button),
        "aksi voice untuk deskripsi selalu terlihat dan memiliki label yang jelas",
    )
    check(
        any("Deskripsi dipakai KALEM sebagai konteks tugas" in value for value in texts(dialog)),
        "form menjelaskan bahwa deskripsi adalah konteks, bukan daftar langkah",
    )
    check(
        not any(
            isinstance(control, ft.TextField) and control.label == "Jam deadline (opsional)"
            for control in walk(dialog)
        ),
        "jam deadline bukan lagi input teks bebas",
    )

    time_button = clickable(dialog, "Pilih jam")
    check(time_button is not None, "form tugas menyediakan tombol pemilih jam")
    if time_button is not None:
        time_button.on_click(SimpleNamespace(control=time_button))
    picker = page.dialogs[-1] if page.dialogs else None
    check(isinstance(picker, ft.TimePicker), "tombol jam membuka TimePicker native")
    if isinstance(picker, ft.TimePicker):
        check(
            picker.hour_format == ft.TimePickerHourFormat.H24,
            "TimePicker deadline selalu memakai format 24 jam",
        )
        picker.value = time(17, 45)
        picker.on_change(SimpleNamespace(control=picker))
        page.pop_dialog()
    check("Pukul 17:45" in texts(dialog), "jam hasil picker ditampilkan dengan format HH:MM")

    task_date = clock.today() + timedelta(days=1)
    date_button = clickable(dialog, "Pilih tanggal")
    check(date_button is not None, "form tugas menyediakan pemilih tanggal")
    if date_button is not None:
        date_button.on_click(SimpleNamespace(control=date_button))
    date_picker = page.dialogs[-1] if page.dialogs else None
    check(isinstance(date_picker, ft.DatePicker), "tombol tanggal membuka DatePicker native")
    if isinstance(date_picker, ft.DatePicker):
        date_picker.value = task_date
        date_picker.on_change(SimpleNamespace(control=date_picker))
        page.pop_dialog()

    title_field = next(
        (
            control
            for control in walk(dialog)
            if isinstance(control, ft.TextField) and control.label == "Nama tugas"
        ),
        None,
    )
    if title_field is not None:
        title_field.value = "Task dengan jam dari picker"
        submit = clickable(dialog, "Tambah")
        submit.on_click(SimpleNamespace(control=submit))
    saved = next(
        (task for task in storage.get_tasks() if task["title"] == "Task dengan jam dari picker"),
        None,
    )
    check(
        saved is not None
        and saved["scheduled_date"] == task_date.isoformat()
        and saved["deadline"] == task_date.isoformat()
        and saved["deadline_time"] == "17:45",
        "tanggal dan jam picker tersimpan sebagai jadwal/deadline tugas",
    )


def scenario_decomposition_identity_and_persistence() -> None:
    print("\n=== I-L: Identity decomposition, persistence, dan tanpa pre-question ===")
    today = clock.today()
    first = storage.add_task(
        "Judul kembar", today.isoformat(), scheduled_date=today.isoformat(),
        description="Laporan untuk kelas A dengan format PDF.",
        custom_steps=["Buka dokumen A"],
        steps=[{"text": "Placeholder A", "done": False}],
    )
    second = storage.add_task(
        "Judul kembar", today.isoformat(), scheduled_date=today.isoformat(),
        description="Ringkasan kelas B untuk dikirim ke dosen.",
        custom_steps=["Cari catatan B"],
        steps=[{"text": "Placeholder B", "done": False}],
    )
    tasks = storage.tasks_for(today.isoformat())
    result = decomposer_logic.plan_today(tasks, 4, allow_ai=False)
    check(
        result.task_steps[first["id"]] != result.task_steps[second["id"]],
        "dua task berjudul sama memperoleh decomposition berdasarkan task_id masing-masing",
    )
    for task in tasks:
        storage.set_task_steps(task["id"], result.task_steps[task["id"]])

    page = FakePage()
    root = tracker.build(page, lambda route: None)
    visible_steps = {
        str(control.label)
        for control in walk(root)
        if isinstance(control, ft.Checkbox)
    }
    check("Buka dokumen A" in visible_steps and "Cari catatan B" in visible_steps,
          "hasil decomposition tetap ada setelah Tracker dibangun ulang")

    split = clickable(root, "Pecah Tugas")
    check(split is not None, "aksi Pecah Tugas tersedia")
    if split is not None:
        split.on_click(SimpleNamespace(control=split))
    split_dialog = page.dialogs[-1] if page.dialogs else None
    dialog_text = texts(split_dialog)
    split_content = getattr(split_dialog, "content", None)
    check(
        not any("tambahkan langkah" in text.casefold() for text in dialog_text)
        and not any(
            isinstance(control, ft.TextField) and "langkah" in str(control.label).casefold()
            for control in walk(page.dialogs[-1] if page.dialogs else None)
        ),
        "sebelum decomposition tidak ada pertanyaan manual-step tambahan",
    )
    check(
        getattr(split_dialog, "bgcolor", None) == "#1C1C26"
        and getattr(split_content, "width", None) == 320
        and getattr(split_content, "height", 999) <= 420,
        "dialog Pecah Tugas ringkas dan memakai tema gelap",
    )


def scenario_decomposition_renders_multi_task_timeline() -> None:
    print("\n=== Pecah Tugas menampilkan timeline multi-task 24 jam ===")
    today = clock.today()
    add_task(
        "Tugas deadline malam",
        today,
        deadline=today,
        deadline_time="23:00",
        steps=[{"text": "Placeholder malam", "done": False}],
        description="Buka dokumen malam\nTulis bagian malam",
    )

    add_task(
        "Tugas deadline awal",
        today,
        deadline=today,
        deadline_time="18:00",
        steps=[{"text": "Placeholder awal", "done": False}],
        description="Buka dokumen awal\nTulis bagian awal",
    )

    page = ImmediatePage()
    root = tracker.build(page, lambda route: None)
    split = clickable(root, "Pecah Tugas")
    if split is not None:
        split.on_click(SimpleNamespace(control=split))
    dialog = page.dialogs[-1] if page.dialogs else None
    submit = clickable(dialog, "Pecah")
    fake_now = datetime.combine(today, time(15, 12))
    if submit is not None:
        with patch.object(decomposer_logic.clock, "now", return_value=fake_now):
            submit.on_click(SimpleNamespace(control=submit))

    shown = texts(root)
    direct_controls = list(getattr(root, "controls", []) or [])
    button_row_index = next(
        (
            index
            for index, control in enumerate(direct_controls)
            if "Tambah Tugas" in texts(control) and "Pecah Tugas" in texts(control)
        ),
        -1,
    )
    plan_index = next(
        (
            index
            for index, control in enumerate(direct_controls)
            if any(value.startswith("Berhasil disusun") for value in texts(control))
        ),
        -1,
    )
    check(
        button_row_index >= 0 and plan_index == button_row_index + 1,
        "card hasil Pecah Tugas tampil tepat di bawah dua tombol utama",
    )
    check(
        "Tugas deadline awal" in shown
        and "Tugas deadline malam" in shown
        and shown.index("Tugas deadline awal") < shown.index("Tugas deadline malam"),
        "beberapa tugas tampil dalam satu timeline dan diurutkan dari deadline terdekat",
    )
    check("15:15" in shown, "timeline dimulai dari jam nyata yang dibulatkan ke 5 menit")
    check(
        any("Deadline 12 Agu · 18:00" in value for value in shown)
        and any("Deadline 12 Agu · 23:00" in value for value in shown),
        "setiap kelompok tugas menampilkan deadline 24 jam",
    )
    check(
        "Istirahat sebentar" in shown
        and any(value.startswith("Total sekitar ") for value in shown),
        "timeline lengkap menampilkan jeda dan total rencana",
    )
    check(
        not re.search(r"\b(?:AM|PM)\b", " ".join(shown), flags=re.IGNORECASE),
        "timeline tidak pernah menampilkan format AM/PM",
    )


def scenario_step_crud_and_done() -> None:
    print("\n=== K-N: CRUD langkah, checklist, dan DONE dari Tracker ===")
    today = clock.today()
    saved = add_task(
        "Task editable", today, deadline=today,
        steps=[{"text": "Langkah awal", "done": False}],
    )
    page = FakePage()
    root = tracker.build(page, lambda route: None)

    visible_step = next(
        (
            control
            for control in walk(root)
            if isinstance(control, ft.Checkbox) and control.label == "Langkah awal"
        ),
        None,
    )
    check(
        visible_step is not None
        and visible_step.label_style.color == theme.ON_BACKGROUND,
        "teks item langkah pada card tugas memakai warna putih",
    )

    add = clickable(root, "+ Tambah langkah")
    check(add is not None, "task card menyediakan + Tambah langkah")
    if add is not None:
        add.on_click(SimpleNamespace(control=add))
        dialog = page.dialogs[-1]
        field = next(control for control in walk(dialog) if isinstance(control, ft.TextField))
        field.value = "Langkah tambahan"
        save = clickable(dialog, "Simpan")
        save.on_click(SimpleNamespace(control=save))
    task = next(task for task in storage.get_tasks() if task["id"] == saved["id"])
    check([step["text"] for step in task["steps"]] == ["Langkah awal", "Langkah tambahan"],
          "langkah manual dari card tersimpan ke task yang sama")

    edits = by_tooltip(root, "Edit langkah")
    if len(edits) >= 2:
        edits[1].on_click(SimpleNamespace(control=edits[1]))
        dialog = page.dialogs[-1]
        field = next(control for control in walk(dialog) if isinstance(control, ft.TextField))
        field.value = "Langkah sudah diedit"
        save = clickable(dialog, "Simpan")
        save.on_click(SimpleNamespace(control=save))
    task = next(task for task in storage.get_tasks() if task["id"] == saved["id"])
    check(len(edits) >= 2 and task["steps"][1]["text"] == "Langkah sudah diedit",
          "langkah dapat diedit dari card dan perubahan persisten")

    deletes = by_tooltip(root, "Hapus langkah")
    if len(deletes) >= 2:
        deletes[1].on_click(SimpleNamespace(control=deletes[1]))
    task = next(task for task in storage.get_tasks() if task["id"] == saved["id"])
    check(len(deletes) >= 2 and len(task["steps"]) == 1,
          "langkah dapat dihapus dari card tanpa menghapus task")

    storage.add_task_step(saved["id"], "Langkah berikutnya")
    root = tracker.build(page, lambda route: None)
    expanded_tile = next(
        (
            control
            for control in walk(root)
            if isinstance(control, ft.ExpansionTile)
            and "Task editable" in texts(control)
        ),
        None,
    )
    if expanded_tile is not None:
        expanded_tile.expanded = True
        expanded_tile.on_change(SimpleNamespace(control=expanded_tile))

    checkbox = next(
        (control for control in walk(root) if getattr(control, "label", None) == "Langkah awal"),
        None,
    )
    if checkbox is not None:
        checkbox.on_change(SimpleNamespace(control=SimpleNamespace(value=True)))
    task = next(task for task in storage.get_tasks() if task["id"] == saved["id"])
    check(checkbox is not None and task["steps"][0]["done"] is True,
          "checklist langsung mengubah status step di storage")
    refreshed_tile = next(
        (
            control
            for control in walk(root)
            if isinstance(control, ft.ExpansionTile)
            and "Task editable" in texts(control)
        ),
        None,
    )
    check(
        refreshed_tile is not None and refreshed_tile.expanded,
        "card pecahan tetap terbuka setelah satu langkah dicentang",
    )
    next_checkbox = next(
        (
            control
            for control in walk(root)
            if getattr(control, "label", None) == "Langkah berikutnya"
        ),
        None,
    )
    if next_checkbox is not None:
        next_checkbox.on_change(SimpleNamespace(control=SimpleNamespace(value=True)))
    task = next(task for task in storage.get_tasks() if task["id"] == saved["id"])
    check(storage.task_is_done(task) and not kalem_engine.rank_actionable_tasks([task]),
          "beberapa step bisa dicentang berurutan sampai task DONE")


def scenario_focus_outcomes_keep_task_identity() -> None:
    print("\n=== O-R: Focus memakai identity Tracker dan outcome eksplisit ===")
    today = clock.today()
    task = add_task(
        "Task Focus", today, deadline=today,
        steps=[{"id": "focus-step", "text": "Kerjakan langkah ini", "done": False}],
    )
    page = FakePage()
    routes: list[str] = []
    root = tracker.build(page, routes.append)
    start = clickable(root, "Mulai")
    check(start is not None, "Tracker menyediakan mulai Focus pada task nyata")
    if start is None:
        return

    start.on_click(SimpleNamespace(control=start))
    check(focus_session.snapshot()["task_id"] == task["id"] and routes[-1] == "home",
          "Focus menerima task_id dan step identity dari Tracker")
    focus_session.finish("incomplete")
    current = next(item for item in storage.get_tasks() if item["id"] == task["id"])
    check(not storage.task_is_done(current), "Focus Belum selesai menjaga task tetap actionable")

    start.on_click(SimpleNamespace(control=start))
    focus_session.finish("blocked")
    current = next(item for item in storage.get_tasks() if item["id"] == task["id"])
    check(not storage.task_is_done(current), "Focus Terhambat tidak menghapus atau menutup task")

    start.on_click(SimpleNamespace(control=start))
    focus_session.finish("completed")
    current = next(item for item in storage.get_tasks() if item["id"] == task["id"])
    check(storage.task_is_done(current), "Focus Done menyelesaikan step/status task Tracker")
    check(not kalem_engine.rank_actionable_tasks([current]),
          "task yang selesai dari Focus tidak direkomendasikan KALEM lagi")


def scenario_weekly_schedule_is_not_recommended_and_ui_is_compact() -> None:
    print("\n=== S-T: Jadwal mingguan terpisah dan Tracker tetap ringkas ===")
    today = clock.today()
    routine = storage.add_task(
        "Kelas rutin mingguan",
        today.isoformat(),
        repeat="weekly",
        deadline_time="09:00",
        menit_est=90,
        steps=[{"text": "Masuk kelas", "done": False}],
    )
    real_task = add_task("Kirim tugas kelas", today, deadline=today)
    period_tasks = storage.tasks_for(today.isoformat())

    ranked = kalem_engine.rank_actionable_tasks(period_tasks)
    check(
        [task["id"] for task in ranked] == [real_task["id"]],
        "jadwal mingguan tidak masuk ranking, sedangkan tugas nyata tetap masuk",
    )
    check(
        kalem_engine.pick_next_action([routine]) is None,
        "jadwal mingguan saja tidak dibuat menjadi next action KALEM",
    )
    from models import fitur as feature_builder

    _, day = kalem_engine.snapshot()
    features = feature_builder.bangun_fitur(day=day)
    check(
        features["n_belum_selesai"] == 1
        and features["beban_menit"] == real_task["menit_est"],
        "jadwal mingguan tidak menggelembungkan jumlah dan beban tugas model",
    )
    weekly_task = storage.add_task(
        "Tugas rumah mingguan",
        today.isoformat(),
        repeat="weekly",
        item_type="task",
        menit_est=25,
        steps=[{"text": "Mulai tugas rumah", "done": False}],
    )
    check(
        any(
            task["id"] == weekly_task["id"]
            for task in kalem_engine.rank_actionable_tasks(
                storage.tasks_for(today.isoformat())
            )
        ),
        "tugas mingguan sungguhan tetap boleh masuk rekomendasi",
    )

    page = FakePage()
    root = tracker.build(page, lambda route: None)
    shown = texts(root)
    check(
        routine["title"] in shown
        and any(value.lower() == "jadwal rutin (1)" for value in shown),
        "jadwal mingguan tetap terlihat di kelompok Jadwal rutin Tracker",
    )
    check(
        any("tidak masuk saran KALEM" in value for value in shown),
        "Tracker menjelaskan jadwal rutin tidak memengaruhi rekomendasi",
    )
    collapsed = [
        control
        for control in walk(root)
        if isinstance(control, ft.ExpansionTile) and control.expanded is False
    ]
    check(
        len(collapsed) >= 4,
        "detail tugas, Focus History, dan sebaran tugas ringkas secara default",
    )


def scenario_recurring_task_has_end_date() -> None:
    print("\n=== U: Tugas berulang berhenti pada tanggal yang dipilih ===")
    today = clock.today()
    repeat_end = today + timedelta(days=14)
    recurring = storage.add_task(
        "Jadwal dengan batas akhir",
        today.isoformat(),
        repeat="weekly",
        repeat_end_date=repeat_end.isoformat(),
        steps=[{"text": "Datang", "done": False}],
    )
    for offset in (0, 7, 14):
        occurrence = storage.tasks_for((today + timedelta(days=offset)).isoformat())
        check(
            any(task["id"] == recurring["id"] for task in occurrence),
            f"occurrence hari ke-{offset} masih dibuat sampai batas inklusif",
        )
    after_end = storage.tasks_for((today + timedelta(days=21)).isoformat())
    check(
        not any(task["id"] == recurring["id"] for task in after_end),
        "occurrence setelah tanggal akhir tidak dibuat",
    )
    check(
        storage.get_tasks()[0]["repeat_end_date"] == repeat_end.isoformat(),
        "tanggal akhir tersimpan pada parent task",
    )

    root = tracker.build(FakePage(), lambda route: None)
    check(
        any(f"sampai {repeat_end.isoformat()}" in value for value in texts(root)),
        "batas akhir terlihat pada ringkasan item Tracker",
    )


def main() -> int:
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    with tempfile.TemporaryDirectory(prefix="focusbuddy_tracker_revision_") as directory:
        storage.DATA_DIR = Path(directory)
        storage.DATA_FILE = storage.DATA_DIR / "data.json"
        storage.BACKUP_FILE = storage.DATA_DIR / "data.json.bak"
        try:
            for scenario in (
                scenario_calendar_modes_and_done,
                scenario_deadline_and_no_deadline,
                scenario_task_input_supports_voice_description_and_time_picker,
                scenario_decomposition_identity_and_persistence,
                scenario_decomposition_renders_multi_task_timeline,
                scenario_step_crud_and_done,
                scenario_focus_outcomes_keep_task_identity,
                scenario_weekly_schedule_is_not_recommended_and_ui_is_compact,
                scenario_recurring_task_has_end_date,
            ):
                storage.reset_all_data()
                focus_session.stop()
                scenario()
        finally:
            focus_session.stop()
            storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"GAGAL: {len(FAILURES)} acceptance Tracker belum terpenuhi")
        return 1
    print("SEMUA ACCEPTANCE TRACKER LULUS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
