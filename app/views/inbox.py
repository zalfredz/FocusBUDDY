"""Halaman inbox untuk menangkap tugas dengan cepat."""
from __future__ import annotations

from datetime import datetime, time

import flet as ft

from app import clock, storage, theme, ui_helpers
from app.core.decomposer_logic import plan_today
from app.voice_diary import VoiceDiary


def _relative_time(iso: str) -> str:
    try:
        when = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    mins = int((clock.now() - when).total_seconds() // 60)
    if mins < 0:
        return "barusan"
    if mins < 1:
        return "barusan"
    if mins < 60:
        return f"{mins} menit lalu"
    hours = mins // 60
    if hours < 24:
        return f"{hours} jam lalu"
    return f"{hours // 24} hari lalu"


def build(page: ft.Page, navigate) -> ft.Control:
    body = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
    notes_column = ft.Column(spacing=10)

    def to_task(note: dict):
        title_field = ft.TextField(label="Jadiin tugas apa?", value=note["text"], multiline=True, max_lines=3)
        description_field = ft.TextField(
            label="Deskripsi (opsional)",
            hint_text="konteks lebih detail, kalau ada",
            multiline=True,
            min_lines=2,
            max_lines=5,
            helper="Diisi -> Pecah Tugas mecah dari SINI, bukan cuma judul",
        )
        for field in (title_field, description_field):
            field.color = theme.ON_BACKGROUND
            field.cursor_color = theme.ON_BACKGROUND
            field.label_style = ft.TextStyle(color=theme.ON_BACKGROUND)
            field.hint_style = ft.TextStyle(color=theme.MUTED)
            field.helper_style = ft.TextStyle(color=theme.MUTED)
            field.bgcolor = "#343446"
            field.filled = True
            field.border_color = theme.BORDER
            field.focused_border_color = theme.PRIMARY
        deadline_time_state = {"value": ""}
        deadline_time_label = ft.Text("Belum dipilih", size=11.5, color=theme.MUTED)
        deadline_time_picker = ft.TimePicker(
            value=None,
            entry_mode=ft.TimePickerEntryMode.DIAL,
            hour_format=ft.TimePickerHourFormat.H24,
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
                page.update()

        def clear_deadline_time(ev=None) -> None:
            set_deadline_time(None)
            page.update()

        deadline_time_picker.on_change = choose_deadline_time
        deadline_time_button = ft.OutlinedButton(
            content=ft.Text("Pilih jam", size=11.5, color=theme.ON_BACKGROUND),
            icon=ft.Icons.SCHEDULE,
            style=ft.ButtonStyle(
                color=theme.ON_BACKGROUND,
                side=ft.BorderSide(1, theme.BORDER),
            ),
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
                ft.Text("Dikosongkan = sampai akhir hari.", size=10.5, color=theme.MUTED),
            ],
            spacing=4,
        )
        important_check = ft.Checkbox(
            label="Penting (berdampak besar)",
            value=True,
            label_style=ft.TextStyle(color=theme.ON_BACKGROUND),
        )
        can_use_ai = storage.can_use("decompose")
        split_check = ft.Checkbox(
            label="Pecah otomatis jadi langkah kecil",
            value=True,
            label_style=ft.TextStyle(color=theme.ON_BACKGROUND),
        )
        note_text = ft.Text(
            "" if can_use_ai else "Kuota penyusunan KALEM habis: tetap coba pola lokal; "
            "kalau nggak cocok, dipakai template sederhana.",
            size=11,
            color=theme.MUTED,
        )

        def submit(ev):
            name = (title_field.value or "").strip()
            if not name:
                title_field.error = "Isi dulu ya"
                page.update()
                return

            task = storage.add_task(
                name,
                clock.today().isoformat(),
                important_check.value,
                steps=[{"text": name, "done": False}],
                difficulty_est=2,
                deadline_time=deadline_time_state["value"],
                description=(description_field.value or "").strip(),
            )

            if split_check.value:
                energy = storage.today_energy() or 3
                result = plan_today([task], energy, allow_ai=can_use_ai)
                if result.ai_called:
                    storage.record_usage("decompose")
                steps = [
                    {"text": step, "done": False}
                    for title, step, _m in result.steps
                    if title == name
                ]
                if steps:
                    storage.set_task_steps(task["id"], steps)

            storage.delete_inbox_note(note["id"])
            voice.cleanup()
            page.pop_dialog()
            render_notes()
            page.update()

        submit_button = ui_helpers.primary_button("Jadiin tugas", submit)

        def set_voice_busy(busy: bool) -> None:
            submit_button.disabled = busy

        voice = VoiceDiary(page, description_field, set_voice_busy)

        def cancel_to_task(ev) -> None:
            voice.cleanup()
            page.pop_dialog()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor="#1C1C26",
                shape=ft.RoundedRectangleBorder(radius=22),
                title=ft.Text(
                    "Rapikan jadi tugas",
                    size=16,
                    color=theme.ON_BACKGROUND,
                    weight=ft.FontWeight.BOLD,
                ),
                content=ft.Column(
                    [
                        title_field,
                        description_field,
                        voice.control(),
                        deadline_time_holder,
                        important_check,
                        split_check,
                        note_text,
                    ],
                    spacing=8,
                    tight=True,
                    width=340,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
                actions=[
                    ft.TextButton(
                        content=ft.Text("Batal", color=theme.ON_BACKGROUND),
                        on_click=cancel_to_task,
                    ),
                    submit_button,
                ],
            )
        )

    def drop(note_id: str):
        storage.delete_inbox_note(note_id)
        render_notes()
        page.update()

    def render_notes():
        notes = storage.get_inbox()
        if not notes:
            notes_column.controls = [
                ui_helpers.empty_state(
                    "Masih kosong nihh",
                    ft.Icons.EDIT_NOTE,
                )
            ]
            return

        notes_column.controls = [
            ui_helpers.card(
                ft.Column(
                    [
                        ft.Text(note["text"], size=13.5, color=theme.ON_BACKGROUND),
                        ft.Text(_relative_time(note.get("created_at", "")), size=10.5, color=theme.MUTED),
                        ft.Row(
                            [
                                ft.TextButton(
                                    content=ft.Text("Jadiin tugas", size=12, weight=ft.FontWeight.BOLD),
                                    icon=ft.Icons.ARROW_FORWARD,
                                    on_click=lambda e, n=note: to_task(n),
                                ),
                                ft.Container(expand=True),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE_OUTLINE,
                                    icon_color=theme.MUTED,
                                    icon_size=18,
                                    tooltip="Hapus catatan",
                                    on_click=lambda e, i=note["id"]: drop(i),
                                ),
                            ],
                            spacing=4,
                        ),
                    ],
                    spacing=6,
                ),
                padding=14,
            )
            for note in notes
        ]

    render_notes()

    body.controls = [
        ui_helpers.page_header("Catatan Kamu", on_back=lambda e: navigate("home")),
        notes_column,
    ]
    return body
