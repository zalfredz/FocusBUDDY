"""Tracker tugas, kalender, dan pecah tugas."""
from __future__ import annotations

import calendar
from datetime import date, time, timedelta

import flet as ft

from app import clock, focus_session, storage, theme, ui_helpers
from app.core import kalem_engine
from app.voice_diary import VoiceDiary
from models import fitur as kfitur
from models.prediction_interface import duration_predictions
from app.core.decomposer_logic import plan_today, task_plan_key
from app.core.energy_predictor import energy_to_mood_default

MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]
DAY_INITIALS = ["S", "S", "R", "K", "J", "S", "M"]
DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

QUADRANT_META = {
    "lakukan": ("Lakukan sekarang", theme.DANGER),
    "jadwalkan": ("Jadwalkan", theme.PRIMARY),
    "delegasikan": ("Bisa didelegasikan", theme.SECONDARY),
    "nanti": ("Nanti aja", theme.MUTED),
}

DIFFICULTY_LABELS = {1: "Gampang", 2: "Sedang", 3: "Berat"}

FOCUS_OUTCOME_LABELS = {
    "completed": "Selesai",
    "incomplete": "Masih butuh waktu",
    "blocked": "Terhambat",
    "later": "Lanjut nanti",
    "rest": "Butuh istirahat",
}


def _date_label(day_iso: str) -> str:
    selected = date.fromisoformat(day_iso)
    return (
        f"{DAY_NAMES[selected.weekday()]}, {selected.day} "
        f"{MONTH_NAMES[selected.month - 1]} {selected.year}"
    )


def _history_stat(value: str, label: str) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    value,
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=theme.ON_BACKGROUND,
                ),
                ft.Text(label, size=10.5, color=theme.MUTED),
            ],
            spacing=1,
        ),
        expand=True,
        padding=8,
        bgcolor=theme.BACKGROUND,
        border_radius=10,
    )


def _actual_focus_minutes(record: dict) -> float:
    try:
        return max(
            float(record.get("actual_focus_minutes", record.get("menit", 0)) or 0),
            0,
        )
    except (TypeError, ValueError):
        return 0.0


def build(page: ft.Page, navigate) -> ft.Control:
    today = clock.today()
    latest_mood = storage.latest_mood()
    default_energy = energy_to_mood_default(latest_mood["score"]) if latest_mood else 3

    locked_energy = storage.today_energy()
    if locked_energy:
        default_energy = locked_energy

    state = {
        "month": today.month,
        "year": today.year,
        "selected": today.isoformat(),
        "energy": default_energy,
        "show_month": False,
        "time_filter": "weekly",
    }

    plan_state: dict = {
        "saved_count": 0,
        "source": "",
        "reason": "",
        "quota_msg": "",
        "n_lokal": 0,
        "n_retrieval": 0,
        "n_manual": 0,
        "n_ai": 0,
    }

    calendar_grid = ft.Column(spacing=6)
    month_label = ft.Text(size=15, weight=ft.FontWeight.BOLD, color=theme.ON_BACKGROUND)
    calendar_nav = ft.Row(spacing=0)
    day_tasks_column = ft.Column(spacing=8)
    eisenhower_column = ft.Column(spacing=8)
    timeline_column = ft.Column(spacing=8)
    plan_column = ft.Column(spacing=8, visible=False)
    next_action_holder = ft.Container(visible=False)
    focus_history_holder = ft.Container()
    expanded_tasks: set[str] = set()


    def day_has_task(day_iso: str) -> bool:
        return bool(storage.tasks_for(day_iso))

    def select_day(day_iso: str):
        selected = date.fromisoformat(day_iso)
        state["selected"] = day_iso
        state["month"], state["year"] = selected.month, selected.year
        state["time_filter"] = "daily"
        render_calendar()
        render_time_filter()
        render_day_tasks()
        render_eisenhower()
        render_timeline()
        page.update()

    def day_cell(day, in_month: bool) -> ft.Control:
        iso = day.isoformat()
        selected = iso == state["selected"]
        is_today = day == today

        if selected:
            bg, fg = theme.PRIMARY, "#FFFFFF"
        elif is_today:
            bg, fg = theme.SURFACE, theme.PRIMARY
        else:
            bg, fg = "#00000000", (theme.ON_BACKGROUND if in_month else theme.BORDER)

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        str(day.day),
                        size=12.5,
                        color=fg,
                        weight=ft.FontWeight.BOLD if (selected or is_today) else ft.FontWeight.NORMAL,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(
                        width=4,
                        height=4,
                        bgcolor=(
                            ("#FFFFFF" if selected else theme.TERTIARY)
                            if (in_month and day_has_task(iso))
                            else "#00000000"
                        ),
                        border_radius=2,
                    ),
                ],
                spacing=1,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            height=42,
            expand=True,
            bgcolor=bg,
            border=ft.Border.all(1, theme.PRIMARY) if is_today and not selected else None,
            border_radius=10,
            alignment=ft.Alignment.CENTER,
            on_click=(lambda e, d=iso: select_day(d)) if in_month else None,
            ink=in_month,
        )

    def render_calendar():
        if state["show_month"]:
            year, month = state["year"], state["month"]
            month_label.value = f"{MONTH_NAMES[month - 1]} {year}"
            rows: list[ft.Control] = [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(d, size=11, color=theme.MUTED, text_align=ft.TextAlign.CENTER),
                            expand=True,
                            alignment=ft.Alignment.CENTER,
                        )
                        for d in DAY_INITIALS
                    ],
                    spacing=4,
                )
            ]
            for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
                rows.append(ft.Row([day_cell(d, d.month == month) for d in week], spacing=4))
            calendar_grid.controls = rows
            calendar_nav.controls = [
                ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, icon_color=theme.MUTED,
                              on_click=lambda e: shift_month(-1)),
                ft.Container(content=month_label, expand=True, alignment=ft.Alignment.CENTER),
                ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_color=theme.MUTED,
                              on_click=lambda e: shift_month(1)),
                ft.TextButton(
                    content=ft.Text("Ringkas kalender", size=11.5),
                    icon=ft.Icons.UNFOLD_LESS,
                    on_click=lambda e: toggle_month(False),
                ),
            ]
        else:
            selected = date.fromisoformat(state["selected"])
            start = selected - timedelta(days=selected.weekday())
            week = [start + timedelta(days=i) for i in range(7)]
            end = week[-1]
            month_label.value = (
                f"{start.day} {MONTH_NAMES[start.month - 1][:3]} – "
                f"{end.day} {MONTH_NAMES[end.month - 1][:3]} {end.year}"
            )
            calendar_grid.controls = [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(DAY_INITIALS[i], size=10, color=theme.MUTED,
                                            text_align=ft.TextAlign.CENTER),
                            expand=True,
                            alignment=ft.Alignment.CENTER,
                        )
                        for i in range(7)
                    ],
                    spacing=4,
                ),
                ft.Row([day_cell(d, True) for d in week], spacing=4),
            ]
            calendar_nav.controls = [
                ft.Container(content=month_label, expand=True),
                ft.TextButton(
                    content=ft.Text("Lihat bulan", size=12, color=theme.PRIMARY),
                    on_click=lambda e: toggle_month(True),
                ),
            ]

    def toggle_month(show: bool):
        state["show_month"] = show
        if show:
            selected = date.fromisoformat(state["selected"])
            state["month"], state["year"] = selected.month, selected.year
        render_calendar()
        page.update()

    def shift_month(delta: int):
        month = state["month"] + delta
        year = state["year"]
        if month < 1:
            month, year = 12, year - 1
        elif month > 12:
            month, year = 1, year + 1
        state["month"], state["year"] = month, year
        render_calendar()
        page.update()


    def quadrant_chip(key: str, count: int) -> ft.Container:
        label, color = QUADRANT_META[key]
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(str(count), size=20, weight=ft.FontWeight.BOLD, color=color),
                    ft.Text(label, size=10, color=theme.MUTED, text_align=ft.TextAlign.CENTER),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            expand=True,
            padding=ft.Padding.symmetric(vertical=12, horizontal=6),
            bgcolor=theme.SURFACE,
            border=ft.Border.all(1, theme.BORDER),
            border_radius=14,
        )

    def render_eisenhower():
        tasks = [
            task
            for task in tasks_in_filter()
            if storage.is_recommendable_task(task)
        ]
        pending = [task for task in tasks if not storage.task_is_done(task)]
        done = [task for task in tasks if storage.task_is_done(task)]
        buckets = {key: [] for key in QUADRANT_META}
        for task in pending:
            buckets[storage.quadrant_of(task)].append(task)
        details = ft.Column(
            [
                ft.Row(
                    [quadrant_chip(k, len(buckets[k])) for k in ["lakukan", "jadwalkan"]],
                    spacing=8,
                ),
                ft.Row(
                    [quadrant_chip(k, len(buckets[k])) for k in ["delegasikan", "nanti"]],
                    spacing=8,
                ),
            ],
            spacing=8,
        )
        eisenhower_column.controls = [
            ui_helpers.card(
                ft.ExpansionTile(
                    title=ft.Text(
                        "SEBARAN TUGAS",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                    ),
                    subtitle=ft.Text(
                        f"{len(pending)} aktif · {len(done)} selesai",
                        size=10.5,
                        color=theme.MUTED,
                    ),
                    controls=[details],
                    controls_padding=ft.Padding.only(left=12, right=12, bottom=12),
                    tile_padding=ft.Padding.symmetric(vertical=2, horizontal=12),
                    expanded=False,
                    dense=True,
                    maintain_state=True,
                    text_color=theme.ON_BACKGROUND,
                    collapsed_text_color=theme.ON_BACKGROUND,
                    icon_color=theme.PRIMARY,
                    collapsed_icon_color=theme.MUTED,
                ),
                padding=0,
            )
        ]


    def render_timeline():
        tasks = kalem_engine.rank_actionable_tasks(tasks_in_filter())
        if not tasks:
            timeline_column.controls = []
            return

        visible_tasks = tasks[:3]
        labels = [
            ft.Row(
                [
                    ft.Container(
                        content=ft.Text(
                            str(index),
                            size=10.5,
                            weight=ft.FontWeight.BOLD,
                            color="#FFFFFF",
                            text_align=ft.TextAlign.CENTER,
                        ),
                        width=24,
                        height=24,
                        bgcolor=QUADRANT_META[storage.quadrant_of(task)][1],
                        border_radius=12,
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Text(
                        task["title"],
                        size=11.5,
                        weight=ft.FontWeight.BOLD,
                        color=theme.ON_BACKGROUND,
                        expand=True,
                    ),
                    ft.Text(
                        f"~{task.get('menit_est', 0)} mnt"
                        if task.get("menit_est")
                        else "",
                        size=10,
                        color=theme.MUTED,
                    ),
                ],
                spacing=8,
            )
            for index, task in enumerate(visible_tasks, start=1)
        ]
        if len(tasks) > len(visible_tasks):
            labels.append(
                ft.Text(
                    f"+{len(tasks) - len(visible_tasks)} tugas lain tetap ada di daftar.",
                    size=10.5,
                    color=theme.MUTED,
                )
            )
        timeline_column.controls = [
            ui_helpers.card(
                ft.Column(
                    [ui_helpers.section_header("Urutan yang disaranin"), *labels],
                    spacing=8,
                ),
                padding=12,
            )
        ]


    filter_holder = ft.Row(spacing=6)

    def set_time_filter(value: str):
        state["time_filter"] = value
        render_time_filter()
        render_day_tasks()
        render_eisenhower()
        render_timeline()
        page.update()

    def render_time_filter():
        labels = [("daily", "Harian"), ("weekly", "Mingguan"), ("monthly", "Bulanan")]
        filter_holder.controls = [
            ui_helpers.choice_chip(
                label, state["time_filter"] == key,
                lambda e, value=key: set_time_filter(value),
            )
            for key, label in labels
        ]

    def tasks_in_filter() -> list[dict]:
        mode = state["time_filter"]
        if mode == "daily":
            return storage.tasks_for(state["selected"])
        if mode == "weekly":
            selected = date.fromisoformat(state["selected"])
            start = selected - timedelta(days=selected.weekday())
            return [task for i in range(7) for task in storage.tasks_for((start + timedelta(days=i)).isoformat())]
        selected = date.fromisoformat(state["selected"])
        year, month = selected.year, selected.month
        days = calendar.monthrange(year, month)[1]
        return [
            task
            for day in range(1, days + 1)
            for task in storage.tasks_for(date(year, month, day).isoformat())
        ]

    def toggle_step(task_id: str, index: int, value: bool, occurrence_date: str | None = None):
        expanded_tasks.add(
            f"{task_id}::{occurrence_date}" if occurrence_date else task_id
        )
        before_task = next((t for t in tasks_in_filter() if t["id"] == task_id and
                            t.get("_occurrence_date") == occurrence_date), None)
        sebelum = storage.task_is_done(before_task) if before_task else False
        storage.set_step_done(task_id, index, value, occurrence_date)
        after_task = next((t for t in storage.tasks_for(occurrence_date) if t["id"] == task_id), None) \
            if occurrence_date else next((t for t in storage.get_tasks() if t["id"] == task_id), None)
        sesudah = storage.task_is_done(after_task) if after_task else False
        profile, day = kalem_engine.snapshot()
        next_decision = kalem_engine.decide(profile, day)
        next_action_holder.data = {
            "kind": next_decision.kind,
            "task_id": next_decision.task.get("id") if next_decision.task else None,
        }
        next_action_holder.content = ui_helpers.banner(
            "Progres tersimpan. KALEM sudah menilai ulang kondisimu — "
            "lihat satu langkah berikutnya di Beranda.",
            theme.SUCCESS,
            ft.Icons.AUTO_AWESOME,
        )
        next_action_holder.visible = True
        refresh_all()
        if sesudah and not sebelum:
            ui_helpers.reward_overlay(page)

    def reopen_task(task_id: str, occurrence_date: str | None = None):
        storage.set_task_done(task_id, False, occurrence_date)
        refresh_all()

    def complete_task(task: dict):
        if storage.set_task_done(
            task["id"], True, task.get("_occurrence_date") or None
        ):
            refresh_all()
            ui_helpers.reward_overlay(page)

    def open_step_dialog(task: dict, index: int | None = None):
        occurrence = task.get("_occurrence_date") or None
        existing = task.get("steps", [])
        current = existing[index].get("text", "") if index is not None else ""
        field = ft.TextField(
            label="Langkah tugas",
            value=current,
            autofocus=True,
            hint_text="mis. Buka dokumen dan baca catatan terakhir",
        )

        def save(ev):
            text = (field.value or "").strip()
            if not text:
                field.error = "Langkahnya masih kosong"
                page.update()
                return
            if index is None:
                changed = storage.add_task_step(task["id"], text, occurrence)
            else:
                changed = storage.update_task_step(task["id"], index, text, occurrence)
            if changed:
                page.pop_dialog()
                refresh_all()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Tambah langkah" if index is None else "Edit langkah", size=16),
                content=field,
                actions=[
                    ft.TextButton(content=ft.Text("Batal"), on_click=lambda e: page.pop_dialog()),
                    ui_helpers.primary_button("Simpan", save, icon=ft.Icons.SAVE),
                ],
            )
        )

    def delete_step(task: dict, index: int):
        storage.delete_task_step(
            task["id"], index, task.get("_occurrence_date") or None
        )
        refresh_all()

    def confirm_remove(task: dict):
        def do_delete(ev):
            page.pop_dialog()
            storage.delete_task(task["id"])
            refresh_all()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Hapus tugas ini?", size=16),
                content=ft.Text(
                    f"“{task['title']}” bakal dihapus beserta langkah-langkahnya. "
                    "Nggak bisa dibalikin.",
                    size=13,
                ),
                actions=[
                    ft.TextButton(content=ft.Text("Batal"), on_click=lambda ev: page.pop_dialog()),
                    ft.ElevatedButton(
                        content=ft.Text("Hapus", weight=ft.FontWeight.BOLD),
                        bgcolor=theme.DANGER,
                        color="#FFFFFF",
                        elevation=0,
                        on_click=do_delete,
                    ),
                ],
            )
        )

    def done_card(task: dict) -> ft.Control:
        return ui_helpers.card(
            ft.Row(
                [
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=theme.SUCCESS, size=20),
                    ft.Text(
                        task["title"],
                        size=13.5,
                        weight=ft.FontWeight.BOLD,
                        color=theme.MUTED,
                        expand=True,
                    ),
                    ft.Container(
                        content=ft.Text("SELESAI", size=9, weight=ft.FontWeight.BOLD,
                                        color="#FFFFFF"),
                        bgcolor=theme.SUCCESS,
                        border_radius=8,
                        padding=ft.Padding.symmetric(vertical=3, horizontal=7),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.UNDO,
                        icon_color=theme.MUTED,
                        icon_size=17,
                        tooltip="Buka lagi",
                        on_click=lambda e, t=task: reopen_task(t["id"], t.get("_occurrence_date")),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=theme.MUTED,
                        icon_size=17,
                        tooltip="Hapus tugas",
                        on_click=lambda e, t=task: confirm_remove(t),
                    ),
                ],
                spacing=6,
            ),
            padding=12,
        )

    def open_card(task: dict) -> ft.Control:
        card_key = task_plan_key(task)
        label, color = QUADRANT_META[storage.quadrant_of(task)]
        steps = task.get("steps", [])
        done_count = sum(1 for s in steps if s.get("done"))
        is_routine = not storage.is_recommendable_task(task)

        step_controls: list[ft.Control] = [
            ft.Row(
                [
                    ft.Checkbox(
                        label=step["text"],
                        value=step.get("done", False),
                        expand=True,
                        on_change=lambda e, tid=task["id"], i=i,
                        od=task.get("_occurrence_date"): toggle_step(
                            tid, i, e.control.value, od
                        ),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.EDIT_OUTLINED,
                        icon_color=theme.MUTED,
                        icon_size=16,
                        tooltip="Edit langkah",
                        on_click=lambda e, t=task, idx=i: open_step_dialog(t, idx),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_color=theme.MUTED,
                        icon_size=16,
                        tooltip="Hapus langkah",
                        on_click=lambda e, t=task, idx=i: delete_step(t, idx),
                    ),
                ],
                spacing=2,
            )
            for i, step in enumerate(steps)
        ]

        detail_controls: list[ft.Control] = []
        scheduled = task.get("_occurrence_date") or task.get("scheduled_date")
        if scheduled and not is_routine:
            detail_controls.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CALENDAR_TODAY, size=14, color=theme.MUTED),
                        ft.Text(f"Dikerjakan {scheduled}", size=11, color=theme.MUTED),
                    ],
                    spacing=6,
                )
            )
        deadline = storage.deadline_at(task)
        if deadline is not None and not is_routine:
            detail_controls.append(
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.EVENT,
                            size=14,
                            color=theme.DANGER if deadline < clock.now() else theme.MUTED,
                        ),
                        ft.Text(
                            "Deadline " + deadline.strftime("%d %b %Y · %H:%M"),
                            size=11,
                            color=theme.DANGER if deadline < clock.now() else theme.MUTED,
                        ),
                    ],
                    spacing=6,
                )
            )
        if len(steps) > 1:
            detail_controls.append(
                ft.ProgressBar(
                    value=done_count / len(steps),
                    color=theme.PRIMARY,
                    bgcolor=theme.BORDER,
                    bar_height=4,
                )
            )

        detail_controls.extend(step_controls)
        detail_controls.append(
            ft.Row(
                [
                    ft.TextButton(
                        content=ft.Text("Mulai", size=11.5, weight=ft.FontWeight.BOLD),
                        icon=ft.Icons.PLAY_ARROW,
                        on_click=lambda e, t=task: start_task_focus(t),
                    ),
                    ft.TextButton(
                        content=ft.Text("Done", size=11.5, weight=ft.FontWeight.BOLD),
                        icon=ft.Icons.CHECK,
                        on_click=lambda e, t=task: complete_task(t),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=theme.MUTED,
                        icon_size=17,
                        tooltip="Hapus tugas",
                        on_click=lambda e, t=task: confirm_remove(t),
                    ),
                ],
                spacing=2,
                alignment=ft.MainAxisAlignment.END,
            )
        )

        detail_controls.append(
            ft.TextButton(
                content=ft.Text("+ Tambah langkah", size=11.5, color=theme.PRIMARY),
                icon=ft.Icons.ADD,
                on_click=lambda e, t=task: open_step_dialog(t),
            )
        )

        repeat_label = {
            "daily": "Tiap hari",
            "weekly": "Jadwal mingguan",
            "monthly": "Tiap bulan",
        }.get(task.get("repeat", "none"), "")
        if is_routine:
            routine_meta = [
                {
                    "daily": "Jadwal harian",
                    "weekly": "Jadwal mingguan",
                    "monthly": "Jadwal bulanan",
                }.get(task.get("repeat", "none"), "Jadwal rutin")
            ]
            try:
                routine_meta.append(DAY_NAMES[date.fromisoformat(scheduled).weekday()])
            except (TypeError, ValueError):
                pass
            if task.get("deadline_time"):
                routine_meta.append(task["deadline_time"])
            if task.get("repeat_end_date"):
                routine_meta.append(f"sampai {task['repeat_end_date']}")
            routine_meta.append("tidak masuk saran KALEM")
            subtitle = " · ".join(routine_meta)
        else:
            meta = [label, DIFFICULTY_LABELS.get(task.get("difficulty_est", 2), "")]
            if repeat_label:
                meta.append(repeat_label)
            if task.get("repeat_end_date"):
                meta.append(f"sampai {task['repeat_end_date']}")
            if task.get("menit_est"):
                meta.append(f"~{task['menit_est']} menit")
            if len(steps) > 1:
                meta.append(f"{done_count}/{len(steps)} langkah")
            subtitle = " · ".join(value for value in meta if value)

        def remember_expansion(event) -> None:
            if bool(getattr(event.control, "expanded", False)):
                expanded_tasks.add(card_key)
            else:
                expanded_tasks.discard(card_key)

        return ui_helpers.card(
            ft.ExpansionTile(
                leading=ft.Icon(
                    ft.Icons.EVENT_REPEAT if is_routine else ft.Icons.CHECKLIST,
                    size=19,
                    color=theme.SECONDARY if is_routine else color,
                ),
                title=ft.Text(
                    task["title"],
                    size=13.5,
                    weight=ft.FontWeight.BOLD,
                    color=theme.ON_BACKGROUND,
                ),
                subtitle=ft.Text(
                    subtitle,
                    size=10,
                    color=theme.SECONDARY if is_routine else color,
                ),
                controls=[ft.Column(detail_controls, spacing=5)],
                controls_padding=ft.Padding.only(left=12, right=12, bottom=10),
                tile_padding=ft.Padding.symmetric(vertical=2, horizontal=12),
                expanded=card_key in expanded_tasks,
                on_change=remember_expansion,
                dense=True,
                maintain_state=True,
                text_color=theme.ON_BACKGROUND,
                collapsed_text_color=theme.ON_BACKGROUND,
                icon_color=theme.PRIMARY,
                collapsed_icon_color=theme.MUTED,
            ),
            padding=0,
        )

    def start_task_focus(task: dict):
        pending_index, pending = next(
            (
                (index, step["text"])
                for index, step in enumerate(task.get("steps", []))
                if not step.get("done")
            ),
            (-1, task["title"]),
        )
        if pending_index < 0:
            pending = f"Buka bahan yang dibutuhkan untuk {task['title']}"
            pending_index = storage.ensure_focus_step(
                task.get("id", ""), pending, task.get("_occurrence_date") or None
            )
        focus_minutes, remaining_estimate = kalem_engine.task_focus_minutes(
            task,
            pending_index,
            state["energy"],
            storage.get_focus_records(),
        )
        focus_session.start(
            focus_minutes,
            label=pending,
            task_title=task["title"],
            kategori=task.get("kategori", ""),
            jumlah_unit=task.get("jumlah_unit", 0),
            energi=state["energy"],
            task_id=task.get("id", ""),
            step_id=storage.task_step_id(
                task.get("id", ""),
                pending_index,
                task.get("_occurrence_date") or None,
            ),
            occurrence_date=task.get("_occurrence_date", ""),
            step_index=pending_index,
            task_estimate_minutes=remaining_estimate,
        )
        navigate("home")

    def render_focus_history():
        today_iso = clock.today().isoformat()
        records = [
            record
            for record in storage.get_focus_records()
            if record.get("date") == today_iso
        ]
        total_minutes = sum(_actual_focus_minutes(record) for record in records)
        recent: list[ft.Control] = []
        for record in records[:3]:
            minutes = _actual_focus_minutes(record)
            minute_label = f"{minutes:.1f}".rstrip("0").rstrip(".")
            recent.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.TIMER_OUTLINED, size=15, color=theme.PRIMARY),
                        ft.Column(
                            [
                                ft.Text(
                                    record.get("task_title") or "Sesi fokus",
                                    size=11.5,
                                    weight=ft.FontWeight.BOLD,
                                    color=theme.ON_BACKGROUND,
                                ),
                                ft.Text(
                                    FOCUS_OUTCOME_LABELS.get(
                                        record.get("outcome", ""), "Tercatat"
                                    ),
                                    size=10,
                                    color=theme.MUTED,
                                ),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Text(f"{minute_label} menit", size=10.5, color=theme.MUTED),
                    ],
                    spacing=8,
                )
            )

        minute_total = f"{total_minutes:.1f}".rstrip("0").rstrip(".")
        history_children: list[ft.Control] = [
            ft.Row(
                [
                    _history_stat(str(len(records)), "Sesi aktual"),
                    _history_stat(minute_total, "Menit aktual"),
                ],
                spacing=8,
            ),
            ft.Text(
                "Ini catatan aktivitas aktual hari ini, bukan target yang wajib dipenuhi.",
                size=10.5,
                color=theme.MUTED,
            ),
        ]
        if recent:
            history_children.extend(recent)
        else:
            history_children.append(
                ft.Text(
                    "Belum ada sesi fokus yang tercatat hari ini.",
                    size=11.5,
                    color=theme.MUTED,
                )
            )
        focus_history_holder.content = ui_helpers.card(
            ft.ExpansionTile(
                title=ft.Text(
                    "FOCUS HISTORY",
                    size=12,
                    weight=ft.FontWeight.BOLD,
                ),
                subtitle=ft.Text(
                    f"{len(records)} sesi · {minute_total} menit aktual hari ini",
                    size=10.5,
                    color=theme.MUTED,
                ),
                controls=[ft.Column(history_children, spacing=8)],
                controls_padding=ft.Padding.only(left=12, right=12, bottom=12),
                tile_padding=ft.Padding.symmetric(vertical=2, horizontal=12),
                expanded=False,
                dense=True,
                maintain_state=True,
                text_color=theme.ON_BACKGROUND,
                collapsed_text_color=theme.ON_BACKGROUND,
                icon_color=theme.PRIMARY,
                collapsed_icon_color=theme.MUTED,
            ),
            padding=0,
        )

    def render_day_tasks():
        tasks = tasks_in_filter()
        if not tasks:
            empty = {
                "daily": "Belum ada tugas di tanggal ini.",
                "weekly": "Belum ada tugas minggu ini.",
                "monthly": "Belum ada tugas bulan ini.",
            }[state["time_filter"]]
            day_tasks_column.controls = [ui_helpers.empty_state(empty, ft.Icons.EVENT_AVAILABLE)]
            return

        open_tasks = kalem_engine.rank_actionable_tasks(tasks)
        routine_by_id: dict[str, dict] = {}
        for task in tasks:
            if (
                not storage.is_recommendable_task(task)
                and not storage.task_is_done(task)
            ):
                routine_by_id.setdefault(task.get("id", ""), task)
        routine_tasks = sorted(
            routine_by_id.values(),
            key=lambda task: (task.get("deadline_time", ""), task.get("title", "")),
        )
        done_tasks: list[dict] = []
        seen_done_routines: set[str] = set()
        for task in tasks:
            if not storage.task_is_done(task):
                continue
            if not storage.is_recommendable_task(task):
                task_id = task.get("id", "")
                if task_id in seen_done_routines:
                    continue
                seen_done_routines.add(task_id)
            done_tasks.append(task)
        done_tasks.sort(key=lambda task: (task.get("deadline", ""), task.get("title", "")))

        items: list[ft.Control] = []
        if open_tasks:
            items.append(ui_helpers.section_header(f"Tugas aktif ({len(open_tasks)})"))
            items.extend(open_card(task) for task in open_tasks)
        if routine_tasks:
            items.append(ui_helpers.section_header(f"Jadwal rutin ({len(routine_tasks)})"))
            items.extend(open_card(task) for task in routine_tasks)
        if done_tasks:
            items.append(
                ui_helpers.section_header(f"Udah kelar ({len(done_tasks)})")
            )
            items.extend(done_card(t) for t in done_tasks)
        day_tasks_column.controls = items

    def refresh_all():
        render_calendar()
        render_day_tasks()
        render_eisenhower()
        render_timeline()
        render_focus_history()
        render_plan()
        page.update()


    def open_add_task(e):
        title_field = ft.TextField(label="Nama tugas", hint_text="mis. Bikin Skripsi Bab 1")
        description_field = ft.TextField(
            label="Deskripsi (opsional)",
            hint_text="mis. bikin proposal buat ikut hackathon kampus, "
                      "temanya bebas, deadline minggu depan",
            multiline=True,
            min_lines=2,
            max_lines=5,
            helper="Diisi -> Pecah Tugas mecah dari SINI, bukan cuma judul",
        )
        no_deadline = ft.Checkbox(
            label="Tanpa deadline",
            value=False,
        )
        task_date_state = {"value": state["selected"]}
        task_date_label = ft.Text(
            _date_label(task_date_state["value"]),
            size=11.5,
            color=theme.ON_BACKGROUND,
            expand=True,
        )

        def choose_task_date(ev) -> None:
            picked_date = task_date_picker.value
            if picked_date is None:
                return
            task_date_state["value"] = picked_date.isoformat()[:10]
            task_date_label.value = _date_label(task_date_state["value"])
            repeat_end_picker.first_date = date.fromisoformat(task_date_state["value"])
            if (
                repeat_end_state["value"]
                and date.fromisoformat(repeat_end_state["value"])
                < date.fromisoformat(task_date_state["value"])
            ):
                repeat_end_state["value"] = ""
                repeat_end_label.value = "Tidak ada tanggal akhir"
                repeat_end_clear.visible = False
            render_estimate()
            page.update()

        task_date_picker = ft.DatePicker(
            value=date.fromisoformat(task_date_state["value"]),
            first_date=date(today.year - 5, 1, 1),
            current_date=date.fromisoformat(task_date_state["value"]),
            last_date=date(today.year + 10, 12, 31),
            help_text="Pilih tanggal tugas",
            cancel_text="Batal",
            confirm_text="Pilih",
            on_change=choose_task_date,
        )
        task_date_holder = ft.Column(
            [
                ft.Text("Tanggal tugas", size=11, color=theme.MUTED),
                ft.Row(
                    [
                        ft.OutlinedButton(
                            content=ft.Text("Pilih tanggal", size=11.5),
                            icon=ft.Icons.CALENDAR_TODAY,
                            on_click=lambda ev: page.show_dialog(task_date_picker),
                        ),
                        task_date_label,
                    ],
                    spacing=6,
                ),
            ],
            spacing=4,
        )
        important_check = ft.Checkbox(label="Penting (berdampak besar)", value=True)
        difficulty = ft.RadioGroup(
            value="2",
            content=ft.Row(
                [
                    ft.Radio(value="1", label="Gampang"),
                    ft.Radio(value="2", label="Sedang"),
                    ft.Radio(value="3", label="Berat"),
                ],
                spacing=0,
            ),
        )
        repeat_group = ft.RadioGroup(
            value="none",
            content=ft.Row(
                [
                    ft.Radio(value="none", label="Sekali"),
                    ft.Radio(value="daily", label="Harian"),
                    ft.Radio(value="weekly", label="Mingguan"),
                    ft.Radio(value="monthly", label="Bulanan"),
                ],
                spacing=0,
                wrap=True,
            ),
        )
        routine_check = ft.Checkbox(
            label="Jadwal rutin saja (tidak masuk saran KALEM)",
            value=False,
            visible=False,
        )
        repeat_end_state = {"value": ""}
        repeat_end_label = ft.Text(
            "Tidak ada tanggal akhir",
            size=10.5,
            color=theme.MUTED,
            expand=True,
        )
        repeat_end_error = ft.Text("", size=10.5, color=theme.DANGER, visible=False)

        deadline_time_state = {"value": ""}
        deadline_time_label = ft.Text("Belum dipilih", size=11.5, color=theme.MUTED)
        deadline_time_picker = ft.TimePicker(
            value=None,
            entry_mode=ft.TimePickerEntryMode.DIAL,
            help_text="Pilih jam deadline",
            hour_label_text="Jam",
            minute_label_text="Menit",
            cancel_text="Batal",
            confirm_text="Pilih",
        )

        def set_deadline_time(selected: time | None) -> None:
            if selected is None:
                deadline_time_state["value"] = ""
                deadline_time_picker.value = None
                deadline_time_label.value = "Belum dipilih"
                deadline_time_clear.visible = False
                return
            deadline_time_state["value"] = selected.strftime("%H:%M")
            deadline_time_picker.value = selected
            deadline_time_label.value = f"Pukul {deadline_time_state['value']}"
            deadline_time_clear.visible = True

        def choose_deadline_time(ev) -> None:
            selected = deadline_time_picker.value
            if isinstance(selected, time):
                set_deadline_time(selected)
                render_estimate()
                page.update()

        def clear_deadline_time(ev=None) -> None:
            set_deadline_time(None)
            render_estimate()
            page.update()

        deadline_time_picker.on_change = choose_deadline_time
        deadline_time_button = ft.OutlinedButton(
            content=ft.Text("Pilih jam", size=11.5),
            icon=ft.Icons.SCHEDULE,
            on_click=lambda ev: page.show_dialog(deadline_time_picker),
        )
        deadline_time_clear = ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_size=16,
            icon_color=theme.MUTED,
            tooltip="Hapus jam deadline",
            visible=False,
            on_click=clear_deadline_time,
        )
        deadline_time_holder = ft.Column(
            [
                ft.Text("Jam deadline (opsional)", size=11, color=theme.MUTED),
                ft.Row(
                    [deadline_time_button, deadline_time_label, deadline_time_clear],
                    spacing=6,
                ),
                ft.Text(
                    "Untuk tugas berulang, jam ini ikut berlaku di setiap occurrence.",
                    size=10.5,
                    color=theme.MUTED,
                ),
            ],
            spacing=4,
        )

        def clear_repeat_end(ev=None):
            repeat_end_state["value"] = ""
            repeat_end_label.value = "Tidak ada tanggal akhir"
            repeat_end_clear.visible = False
            repeat_end_error.visible = False
            page.update()

        def choose_repeat_end(ev):
            picked_date = repeat_end_picker.value
            if picked_date is None:
                return
            repeat_end_state["value"] = picked_date.isoformat()[:10]
            repeat_end_label.value = f"Berakhir {repeat_end_state['value']}"
            repeat_end_clear.visible = True
            repeat_end_error.visible = False
            page.update()

        repeat_start_date = date.fromisoformat(task_date_state["value"])
        repeat_end_picker = ft.DatePicker(
            first_date=repeat_start_date,
            current_date=repeat_start_date,
            last_date=date(repeat_start_date.year + 10, 12, 31),
            help_text="Pilih tanggal berakhir",
            cancel_text="Batal",
            confirm_text="Pilih",
            on_change=choose_repeat_end,
        )
        repeat_end_clear = ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_size=16,
            icon_color=theme.MUTED,
            tooltip="Hapus tanggal akhir",
            visible=False,
            on_click=clear_repeat_end,
        )
        repeat_end_holder = ft.Column(
            [
                ft.Text("Berakhir kapan? (opsional)", size=11, color=theme.MUTED),
                ft.Row(
                    [
                        ft.OutlinedButton(
                            content=ft.Text("Pilih tanggal akhir", size=11.5),
                            icon=ft.Icons.EVENT,
                            on_click=lambda ev: page.show_dialog(repeat_end_picker),
                        ),
                        repeat_end_label,
                        repeat_end_clear,
                    ],
                    spacing=6,
                ),
                repeat_end_error,
            ],
            spacing=4,
            visible=False,
        )

        def change_repeat(ev):
            repeat = repeat_group.value or "none"
            routine_check.visible = repeat != "none"
            repeat_end_holder.visible = repeat != "none"
            routine_check.value = repeat == "weekly"
            if repeat == "none":
                clear_repeat_end()
            page.update()

        repeat_group.on_change = change_repeat

        picked = {
            "kategori": "",
            "jumlah": 0.0,
            "menit": 0,
            "prediction_source": "",
            "prediction_model_version": "",
            "prediction_global_minutes": None,
            "prediction_global_dataset_version": "",
            "prediction_global_artifact_sha256": "",
            "prediction_personalization_version": "",
            "prediction_personalization_dataset_version": "",
            "prediction_importance": None,
            "prediction_deadline_days": None,
        }
        kategori_holder = ft.Container()
        buka_lanjutan = {"on": False}
        jumlah_field = ft.TextField(
            label="Berapa banyak?",
            keyboard_type=ft.KeyboardType.NUMBER,
            visible=False,
            on_change=lambda ev: render_estimate(),
        )
        estimate_holder = ft.Container()

        def render_deadline():
            deadline_time_button.disabled = bool(no_deadline.value)
            deadline_time_clear.disabled = bool(no_deadline.value)
            if no_deadline.value:
                set_deadline_time(None)
                deadline_time_label.value = "Tidak ada deadline"
            elif not deadline_time_state["value"]:
                deadline_time_label.value = "Belum dipilih"
            render_estimate()

        no_deadline.on_change = lambda ev: render_deadline()

        def pick_kategori(key: str):
            picked["kategori"] = "" if picked["kategori"] == key else key
            render_kategori()
            render_estimate()

        def render_kategori():
            if not buka_lanjutan["on"]:
                kategori_holder.content = ft.TextButton(
                    content=ft.Text("+ Kasih tau jenis & jumlahnya (opsional)",
                                    size=11.5, color=theme.PRIMARY),
                    on_click=lambda ev: (buka_lanjutan.update(on=True), render_kategori(),
                                         render_estimate()),
                )
                return
            chips = [
                ui_helpers.choice_chip(
                    meta["label"], picked["kategori"] == key,
                    lambda ev, k=key: pick_kategori(k),
                )
                for key, meta in duration_predictions.categories.items()
            ]
            kategori_holder.content = ft.Column(
                [
                    ft.Text("Jenis tugasnya apa? Bikin KALEM inget kecepatan kamu "
                            "di jenis ini.", size=11, color=theme.MUTED),
                    ft.Row(chips, spacing=6, wrap=True, run_spacing=6),
                ],
                spacing=6,
            )

        def render_estimate():
            judul = (title_field.value or "").strip()
            kategori = picked["kategori"]

            jumlah_field.visible = bool(kategori) and buka_lanjutan["on"]
            if kategori:
                satuan = duration_predictions.unit_for_category(kategori)
                jumlah_field.label = f"Berapa {satuan}?"
            try:
                picked["jumlah"] = float((jumlah_field.value or "").strip())
            except ValueError:
                picked["jumlah"] = 0.0

            if len(judul) < 3:
                estimate_holder.content = None
                picked["menit"] = 0
                page.update()
                return

            if no_deadline.value:
                tempo = 7
            else:
                try:
                    tempo = max(
                        0,
                        (date.fromisoformat(task_date_state["value"]) - today).days,
                    )
                except ValueError:
                    tempo = 0
            penting = 8 if important_check.value else 4
            if tempo <= 1:
                penting = min(10, penting + 2)

            est = duration_predictions.predict(
                judul,
                deadline_days=tempo,
                importance=penting,
                category=kategori,
                quantity=picked["jumlah"],
                focus_records=storage.get_focus_records(),
                energy=state["energy"],
            )
            picked["menit"] = est.menit
            picked["prediction_source"] = est.sumber
            picked["prediction_importance"] = penting
            picked["prediction_deadline_days"] = tempo
            picked["prediction_model_version"] = est.model_version
            picked["prediction_global_minutes"] = est.global_minutes
            picked["prediction_global_dataset_version"] = est.global_dataset_version
            picked["prediction_global_artifact_sha256"] = est.global_artifact_sha256
            picked["prediction_personalization_version"] = est.personalization_version
            picked["prediction_personalization_dataset_version"] = (
                est.personalization_dataset_version
            )
            estimate_holder.content = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.SCHEDULE, size=16, color=theme.PRIMARY),
                                ft.Text(
                                    f"Biasanya {est.rentang}"
                                    + (f" · {est.sesi} sesi" if est.sesi > 1 else ""),
                                    size=13, weight=ft.FontWeight.BOLD,
                                    color=theme.ON_BACKGROUND, expand=True,
                                ),
                            ],
                            spacing=6,
                        ),
                        ft.Text(est.catatan, size=10.5, color=theme.MUTED),
                    ],
                    spacing=4,
                ),
                bgcolor=theme.BACKGROUND,
                border_radius=10,
                padding=ft.Padding.symmetric(vertical=8, horizontal=10),
            )
            page.update()

        title_field.on_change = lambda ev: render_estimate()
        important_check.on_change = lambda ev: render_estimate()

        render_kategori()
        render_deadline()
        render_estimate()

        def submit(ev):
            name = (title_field.value or "").strip()
            if not name:
                title_field.error = "Isi nama tugasnya dulu"
                page.update()
                return
            repeat = repeat_group.value or "none"
            repeat_end = repeat_end_state["value"] if repeat != "none" else ""
            if repeat_end and date.fromisoformat(repeat_end) < date.fromisoformat(
                task_date_state["value"]
            ):
                repeat_end_error.value = "Tanggal akhir tidak boleh sebelum tanggal mulai."
                repeat_end_error.visible = True
                page.update()
                return
            task_date = task_date_state["value"]
            deadline = "" if no_deadline.value else task_date
            storage.add_task(
                name,
                deadline,
                important_check.value,
                deadline_time=deadline_time_state["value"] if deadline else "",
                steps=[{"text": name, "done": False}],
                difficulty_est=int(difficulty.value or 2),
                kategori=picked["kategori"],
                jumlah_unit=picked["jumlah"],
                menit_est=picked["menit"],
                description=(description_field.value or "").strip(),
                repeat=repeat,
                scheduled_date=task_date,
                item_type="schedule" if routine_check.value else "task",
                repeat_end_date=repeat_end,
                prediction_model_version=picked["prediction_model_version"],
                prediction_global_minutes=picked["prediction_global_minutes"],
                prediction_global_model_version=picked["prediction_model_version"],
                prediction_global_dataset_version=picked["prediction_global_dataset_version"],
                prediction_global_artifact_sha256=picked["prediction_global_artifact_sha256"],
                prediction_personalization_version=picked["prediction_personalization_version"],
                prediction_personalization_dataset_version=(
                    picked["prediction_personalization_dataset_version"]
                ),
                prediction_source=picked["prediction_source"],
                prediction_importance=picked["prediction_importance"],
                prediction_deadline_days=picked["prediction_deadline_days"],
            )
            voice.cleanup()
            page.pop_dialog()
            refresh_all()

        submit_button = ui_helpers.primary_button("Tambah", submit)

        def set_voice_busy(busy: bool) -> None:
            submit_button.disabled = busy

        voice = VoiceDiary(page, description_field, set_voice_busy)
        voice_status = voice.embed_in_field()
        description_field.on_change = lambda ev: voice.sync_with_text()

        def cancel_add_task(ev) -> None:
            voice.cleanup()
            page.pop_dialog()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Tambah tugas", size=16),
                content=ft.Column(
                    [
                        title_field,
                        description_field,
                        voice_status,
                        task_date_holder,
                        no_deadline,
                        deadline_time_holder,
                        ft.Text("Ulangi tugas", size=11, color=theme.MUTED),
                        repeat_group,
                        routine_check,
                        repeat_end_holder,
                        important_check,
                        ft.Text("Seberat apa buat dimulai?", size=11, color=theme.MUTED),
                        difficulty,
                        ft.Divider(color=theme.BORDER, height=1),
                        kategori_holder,
                        jumlah_field,
                        estimate_holder,
                    ],
                    spacing=8,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                actions=[
                    ft.TextButton(content=ft.Text("Batal"), on_click=cancel_add_task),
                    submit_button,
                ],
            )
        )


    def open_split_picker(e):
        tasks = [
            task
            for task in tasks_in_filter()
            if storage.is_recommendable_task(task)
            and not storage.task_is_done(task)
        ]
        if not tasks:
            plan_state.update(
                saved_count=0, source="", reason="", quota_msg="", n_lokal=0,
                n_retrieval=0, n_manual=0, n_ai=0,
            )
            plan_column.controls = [
                ui_helpers.banner("Belum ada tugas aktif di periode ini buat dipecah.",
                                  theme.WARN, ft.Icons.INFO_OUTLINE)
            ]
            plan_column.visible = True
            page.update()
            return

        boxes = {
            task_plan_key(t): ft.Checkbox(
                label=(
                    t["title"]
                    + (f" · {t['_occurrence_date']}" if t.get("_occurrence_date") else "")
                ),
                value=True,
            )
            for t in tasks
        }

        def picker_row(task: dict) -> ft.Control:
            box = boxes[task_plan_key(task)]
            steps = len(task.get("steps", []))
            rows: list[ft.Control] = [box]
            if steps > 1:
                rows.append(
                    ft.Container(
                        content=ft.Text(
                            f"udah punya {steps} langkah — bakal disusun ulang",
                            size=10.5,
                            color=theme.MUTED,
                        ),
                        padding=ft.Padding.only(left=42),
                    )
                )
            return ft.Column(rows, spacing=4)

        def set_all(value: bool):
            for box in boxes.values():
                box.value = value
            page.update()

        def submit(ev):
            chosen = []
            for task in tasks:
                if not boxes[task_plan_key(task)].value:
                    continue
                chosen.append(task)
            page.pop_dialog()
            if chosen:
                run_split(chosen)

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Pecah tugas mana?", size=16),
                content=ft.Column(
                    [
                        ft.Text(
                            "Cuma tugas yang dicentang yang akan dipecah. Setelah hasilnya "
                            "muncul, langkah bisa diedit langsung dari card tugas.",
                            size=11.5,
                            color=theme.MUTED,
                        ),
                        ft.Row(
                            [
                                ft.TextButton(content=ft.Text("Pilih semua", size=12),
                                              on_click=lambda ev: set_all(True)),
                                ft.TextButton(content=ft.Text("Kosongkan", size=12),
                                              on_click=lambda ev: set_all(False)),
                            ],
                            spacing=4,
                        ),
                        *[picker_row(t) for t in tasks],
                    ],
                    spacing=6,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                actions=[
                    ft.TextButton(content=ft.Text("Batal"), on_click=lambda ev: page.pop_dialog()),
                    ui_helpers.primary_button("Pecah", submit, icon=ft.Icons.AUTO_AWESOME),
                ],
            )
        )

    def run_split(tasks: list[dict]):
        allow_ai = storage.can_use("decompose")

        progres_holder = ft.Container()
        plan_column.controls = [progres_holder]
        plan_column.visible = True
        page.update()

        async def kerjakan():
            hasil = await ui_helpers.jalankan_dengan_progres(
                page, progres_holder,
                lambda: plan_today(tasks, state["energy"], allow_ai=allow_ai),
                "KALEM lagi mecahin tugasnya...",
            )
            selesaikan(hasil, tasks)

        page.run_task(kerjakan)

    def selesaikan(result, tasks: list[dict]):
        if result.ai_called:
            storage.record_usage("decompose")

        saved_count = 0
        for task in tasks:
            steps = result.task_steps.get(task_plan_key(task))
            if steps:
                storage.set_task_steps(task["id"], steps, task.get("_occurrence_date"))
                saved_count += 1

        left = storage.quota_left("decompose")
        plan_state.update(
            saved_count=saved_count,
            source=result.source,
            reason=result.reason,
            quota_msg=f" — sisa {left}x hari ini" if left is not None else "",
            n_lokal=result.n_lokal,
            n_retrieval=result.n_retrieval,
            n_manual=result.n_manual,
            n_ai=result.n_ai,
        )
        if not saved_count:
            plan_column.controls = [
                ui_helpers.banner(
                    "Langkah belum berhasil disusun. Coba lagi sebentar lagi.",
                    theme.WARN,
                    ft.Icons.INFO_OUTLINE,
                )
            ]
            plan_column.visible = True
        refresh_all()

    def render_plan():
        saved_count = int(plan_state.get("saved_count", 0))
        if not saved_count:
            if not plan_column.controls:
                plan_column.visible = False
            return
        n_lokal = plan_state.get("n_lokal", 0)
        n_retrieval = plan_state.get("n_retrieval", 0)
        n_manual = plan_state.get("n_manual", 0)
        n_ai = plan_state.get("n_ai", 0)
        if plan_state["source"] == "ai":
            source = "Disusun KALEM" + plan_state["quota_msg"]
            color, icon = theme.PRIMARY, ft.Icons.AUTO_AWESOME
        elif plan_state["source"] == "lokal":
            if n_manual and n_retrieval:
                source = "Disusun dari deskripsi kamu dan pola KALEM — hemat kuota"
            elif n_manual:
                source = "Menggunakan langkah dari deskripsi kamu — hemat kuota"
            else:
                source = "Disusun dari pola KALEM — hemat kuota"
            color, icon = theme.SUCCESS, ft.Icons.BOLT
        elif plan_state["source"] == "campuran":
            if n_ai:
                if n_manual and n_retrieval:
                    source = "Sebagian dari deskripsi kamu/pola KALEM, sisanya disusun KALEM" + plan_state["quota_msg"]
                elif n_manual:
                    source = "Sebagian dari deskripsi kamu, sisanya disusun KALEM" + plan_state["quota_msg"]
                elif n_retrieval:
                    source = "Sebagian dari pola KALEM, sisanya disusun KALEM" + plan_state["quota_msg"]
                else:
                    source = "Sebagian disusun KALEM, sisanya template KALEM" + plan_state["quota_msg"]
                color, icon = theme.PRIMARY, ft.Icons.AUTO_AWESOME
            else:
                source = "Sebagian dari catatan kamu, sisanya template KALEM"
                color, icon = theme.WARN, ft.Icons.OFFLINE_BOLT
        else:
            source = "Disusun dengan template KALEM"
            color, icon = theme.WARN, ft.Icons.OFFLINE_BOLT

        plan_column.controls = [
            ui_helpers.banner(
                f"Langkah untuk {saved_count} tugas tersimpan di card. {source}",
                color,
                icon,
            )
        ]
        plan_column.visible = True


    render_calendar()
    render_time_filter()
    render_day_tasks()
    render_eisenhower()
    render_timeline()
    render_focus_history()

    calendar_card = ui_helpers.card(
        ft.Column([calendar_nav, calendar_grid], spacing=8), padding=14
    )

    return ft.Column(
        [
            ui_helpers.page_header("Tracker"),
            calendar_card,
            filter_holder,
            ft.Row(
                [
                    ui_helpers.primary_button("Tambah Tugas", open_add_task, icon=ft.Icons.ADD, expand=True),
                    ft.OutlinedButton(
                        content=ft.Text("Pecah Tugas"),
                        icon=ft.Icons.AUTO_AWESOME,
                        on_click=open_split_picker,
                        expand=True,
                    ),
                ],
                spacing=10,
            ),
            next_action_holder,
            timeline_column,
            plan_column,
            day_tasks_column,
            focus_history_holder,
            eisenhower_column,
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
