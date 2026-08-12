"""Halaman penuh untuk menambahkan satu tugas dari Home."""
from __future__ import annotations

from datetime import date, time

import flet as ft

from app import clock, storage
from models.prediction_interface import duration_predictions

BACKGROUND = "#141416"
PANEL = "#1C1C26"
FIELD = "#343446"
BORDER = "#484863"
TEXT = "#DDE0FF"
MUTED = "#A8A8C0"
BUTTON_TEXT = "#181A35"
FONT = "Plus Jakarta Sans"
CONTENT_WIDTH = 320


def _field_style() -> dict:
    return {
        "border": ft.InputBorder.NONE,
        "bgcolor": FIELD,
        "color": TEXT,
        "cursor_color": TEXT,
        "hint_style": ft.TextStyle(color=MUTED, size=13, font_family=FONT),
        "text_style": ft.TextStyle(color=TEXT, size=14, font_family=FONT),
        "border_radius": 14,
        "content_padding": ft.Padding.symmetric(vertical=14, horizontal=14),
    }


def build(page: ft.Page, navigate) -> ft.Control:
    today = clock.today()
    selected_date = {"value": today}
    selected_time = {"value": time(hour=7)}

    title_field = ft.TextField(
        hint_text="Nama Tugas", autofocus=True, height=58, **_field_style()
    )
    description_field = ft.TextField(
        hint_text="Deskripsi Tugas",
        multiline=True,
        min_lines=3,
        max_lines=5,
        **_field_style(),
    )
    date_text = ft.Text(today.strftime("%d/%m/%Y"), color=MUTED, size=14, font_family=FONT)
    time_text = ft.Text("07:00", color=MUTED, size=14, font_family=FONT)

    def choose_date(e) -> None:
        value = date_picker.value
        if value is None:
            return
        if hasattr(value, "date"):
            value = value.date()
        selected_date["value"] = value
        date_text.value = value.strftime("%d/%m/%Y")
        page.update()

    def choose_time(e) -> None:
        value = time_picker.value
        if not isinstance(value, time):
            return
        selected_time["value"] = value
        time_text.value = value.strftime("%H:%M")
        page.update()

    date_picker = ft.DatePicker(
        value=today,
        first_date=date(today.year - 1, 1, 1),
        current_date=today,
        last_date=date(today.year + 10, 12, 31),
        help_text="Pilih tanggal deadline",
        cancel_text="Batal",
        confirm_text="Pilih",
        on_change=choose_date,
    )
    time_picker = ft.TimePicker(
        value=selected_time["value"],
        entry_mode=ft.TimePickerEntryMode.DIAL,
        hour_format=ft.TimePickerHourFormat.H24,
        help_text="Pilih jam deadline",
        hour_label_text="Jam",
        minute_label_text="Menit",
        cancel_text="Batal",
        confirm_text="Pilih",
        on_change=choose_time,
    )

    def picker_field(label: ft.Text, icon, on_click) -> ft.Control:
        return ft.Container(
            height=58,
            bgcolor=FIELD,
            border_radius=14,
            padding=ft.Padding.symmetric(vertical=10, horizontal=14),
            content=ft.Row(
                [label, ft.Icon(icon, size=21, color=TEXT)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            on_click=on_click,
            ink=True,
        )

    def submit(e) -> None:
        name = (title_field.value or "").strip()
        if not name:
            title_field.error = "Isi nama tugasnya dulu"
            page.update()
            return

        deadline = selected_date["value"].isoformat()
        days_left = max(0, (selected_date["value"] - today).days)
        importance = 10 if days_left <= 1 else 8
        estimate = duration_predictions.predict(
            name,
            deadline_days=days_left,
            importance=importance,
            category="",
            quantity=0.0,
            focus_records=storage.get_focus_records(),
            energy=storage.today_energy() or 3,
        )
        storage.add_task(
            name,
            deadline,
            True,
            deadline_time=selected_time["value"].strftime("%H:%M"),
            steps=[{"text": name, "done": False}],
            difficulty_est=2,
            menit_est=estimate.menit,
            description=(description_field.value or "").strip(),
            scheduled_date=deadline,
            prediction_model_version=estimate.model_version,
            prediction_global_minutes=estimate.global_minutes,
            prediction_global_model_version=estimate.model_version,
            prediction_global_dataset_version=estimate.global_dataset_version,
            prediction_global_artifact_sha256=estimate.global_artifact_sha256,
            prediction_personalization_version=estimate.personalization_version,
            prediction_personalization_dataset_version=estimate.personalization_dataset_version,
            prediction_source=estimate.sumber,
            prediction_importance=importance,
            prediction_deadline_days=days_left,
        )
        navigate("home")

    label_style = dict(
        size=13, color=TEXT, font_family=FONT, weight=ft.FontWeight.W_600
    )
    form = ft.Container(
        width=CONTENT_WIDTH,
        bgcolor=PANEL,
        border=ft.Border.all(1.5, BORDER),
        border_radius=22,
        padding=ft.Padding(left=22, top=24, right=22, bottom=20),
        content=ft.Column(
            [
                ft.Text(
                    "Tambah Tugas",
                    size=29,
                    color=TEXT,
                    weight=ft.FontWeight.W_900,
                    font_family=FONT,
                    style=ft.TextStyle(letter_spacing=0.7),
                ),
                ft.Container(height=18),
                ft.Text("Masukkan nama tugas:", **label_style),
                title_field,
                ft.Text("Masukkan deskripsi tugas:", **label_style),
                description_field,
                ft.Text("Deadline tugas:", **label_style),
                picker_field(
                    date_text,
                    ft.Icons.CALENDAR_MONTH_OUTLINED,
                    lambda e: page.show_dialog(date_picker),
                ),
                picker_field(
                    time_text,
                    ft.Icons.ACCESS_TIME,
                    lambda e: page.show_dialog(time_picker),
                ),
                ft.Row(
                    [
                        ft.TextButton(
                            content=ft.Text("Batal", color=MUTED, font_family=FONT),
                            on_click=lambda e: navigate("home"),
                        ),
                        ft.Button(
                            width=120,
                            height=42,
                            content=ft.Text(
                                "Tambah",
                                color=BUTTON_TEXT,
                                weight=ft.FontWeight.W_800,
                                font_family=FONT,
                            ),
                            style=ft.ButtonStyle(
                                bgcolor=TEXT,
                                color=BUTTON_TEXT,
                                shape=ft.RoundedRectangleBorder(radius=18),
                            ),
                            on_click=submit,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                ),
            ],
            spacing=10,
            tight=True,
        ),
    )

    return ft.Container(
        expand=True,
        bgcolor=BACKGROUND,
        alignment=ft.Alignment.CENTER,
        padding=ft.Padding(left=20, top=34, right=20, bottom=18),
        content=ft.Column(
            [
                ft.Stack(
                    [
                        form,
                        ft.Image(
                            src="kalem_cemas.svg",
                            width=72,
                            height=72,
                            left=-6,
                            bottom=-12,
                            fit=ft.BoxFit.CONTAIN,
                        ),
                    ],
                    width=CONTENT_WIDTH,
                    clip_behavior=ft.ClipBehavior.NONE,
                ),
                ft.Text(
                    "FocusBuddy bukan alat diagnosis ADHD dan bukan pengganti tenaga medis.",
                    size=10.5,
                    color=TEXT,
                    font_family=FONT,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=22,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
    )
