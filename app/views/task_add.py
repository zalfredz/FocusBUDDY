"""Halaman Tambah Tugas dari Home dengan input yang sama seperti Tracker."""
from __future__ import annotations

from datetime import date, time

import flet as ft

from app import clock, storage, theme, ui_helpers
from app.date_utils import selected_calendar_date
from app.voice_diary import VoiceDiary
from models.prediction_interface import duration_predictions


BACKGROUND = "#141416"
PANEL = "#1C1C26"
CARD = "#24242F"
FIELD = "#343446"
BORDER = "#484863"
TEXT = "#DDE0FF"
MUTED = "#A8A8C0"
FONT = "Plus Jakarta Sans"
CONTENT_WIDTH = 360


def _field_style() -> dict:
    return {
        "filled": True,
        "bgcolor": FIELD,
        "color": TEXT,
        "border_color": BORDER,
        "focused_border_color": theme.PRIMARY,
        "label_style": ft.TextStyle(color=TEXT),
        "hint_style": ft.TextStyle(color=MUTED),
        "border_radius": 12,
    }


def _date_label(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def build(page: ft.Page, navigate) -> ft.Control:
    today = clock.today()
    task_date = {"value": today}
    deadline_time = {"value": ""}
    repeat_end = {"value": ""}

    title_field = ft.TextField(
        label="Nama tugas",
        hint_text="Nama tugas",
        autofocus=True,
        **_field_style(),
    )
    description_field = ft.TextField(
        label="Deskripsi (opsional)",
        hint_text="Konteks, hasil yang diinginkan, atau batasan tugas",
        multiline=True,
        min_lines=2,
        max_lines=5,
        **_field_style(),
    )
    description_context = ft.Text(
        "Deskripsi dipakai KALEM sebagai konteks tugas, bukan sebagai daftar "
        "langkah. Langkah baru akan disusun saat tugas dipecah.",
        size=10.5,
        color=MUTED,
    )
    no_deadline = ft.Checkbox(
        label="Tanpa deadline",
        value=False,
        label_style=ft.TextStyle(color=TEXT),
    )
    important = ft.Checkbox(
        label="Penting (berdampak besar)",
        value=True,
        label_style=ft.TextStyle(color=TEXT),
    )
    difficulty = ui_helpers.compact_difficulty_selector()

    picker_style = ft.ButtonStyle(
        bgcolor=FIELD,
        color=TEXT,
        side=ft.BorderSide(1, BORDER),
        shape=ft.RoundedRectangleBorder(radius=12),
    )

    task_date_text = ft.Text(
        _date_label(today), size=11.5, color=TEXT, expand=True
    )

    def choose_task_date(event) -> None:
        chosen = selected_calendar_date(
            task_date_picker.value, getattr(event, "data", None)
        )
        if chosen is None:
            return
        task_date["value"] = chosen
        task_date_text.value = _date_label(chosen)
        repeat_end_picker.first_date = chosen
        if repeat_end["value"] and repeat_end["value"] < chosen:
            clear_repeat_end(update=False)
        render_estimate()
        page.update()

    task_date_picker = ft.DatePicker(
        value=today,
        first_date=date(today.year - 5, 1, 1),
        current_date=today,
        last_date=date(today.year + 10, 12, 31),
        help_text="Pilih tanggal deadline",
        cancel_text="Batal",
        confirm_text="Pilih",
        on_change=choose_task_date,
    )
    task_date_holder = ft.Column(
        [
            ft.Text("Tanggal deadline", size=11, color=MUTED),
            ft.Row(
                [
                    ft.OutlinedButton(
                        content=ft.Text("Pilih tanggal", size=11.5, color=TEXT),
                        icon=ft.Icons.CALENDAR_TODAY,
                        style=picker_style,
                        on_click=lambda event: page.show_dialog(task_date_picker),
                    ),
                    task_date_text,
                ],
                spacing=6,
            ),
        ],
        spacing=4,
    )

    deadline_time_text = ft.Text("Belum dipilih", size=11.5, color=MUTED)
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

    def set_deadline_time(value: time | None) -> None:
        if value is None:
            deadline_time["value"] = ""
            deadline_time_picker.value = None
            deadline_time_text.value = "Belum dipilih"
            deadline_time_clear.visible = False
            return
        deadline_time["value"] = value.strftime("%H:%M")
        deadline_time_picker.value = value
        deadline_time_text.value = f"Pukul {deadline_time['value']}"
        deadline_time_clear.visible = True

    def choose_deadline_time(event) -> None:
        value = deadline_time_picker.value
        if isinstance(value, time):
            set_deadline_time(value)
            render_estimate()
            page.update()

    def clear_deadline_time(event=None) -> None:
        set_deadline_time(None)
        render_estimate()
        page.update()

    deadline_time_picker.on_change = choose_deadline_time
    deadline_time_clear = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_size=16,
        icon_color=MUTED,
        tooltip="Hapus jam deadline",
        visible=False,
        on_click=clear_deadline_time,
    )
    deadline_time_holder = ft.Column(
        [
            ft.Text("Jam deadline", size=11, color=MUTED),
            ft.Row(
                [
                    ft.OutlinedButton(
                        content=ft.Text("Pilih jam", size=11.5, color=TEXT),
                        icon=ft.Icons.SCHEDULE,
                        style=picker_style,
                        on_click=lambda event: page.show_dialog(deadline_time_picker),
                    ),
                    deadline_time_text,
                    deadline_time_clear,
                ],
                spacing=6,
            ),
        ],
        spacing=4,
    )

    repeat_group = ft.Dropdown(
        value="none",
        label="Tugas berulang",
        options=[
            ft.DropdownOption(
                key=value,
                text=label,
                style=ft.ButtonStyle(color=TEXT),
            )
            for value, label in (
                ("none", "Sekali"),
                ("daily", "Harian"),
                ("weekly", "Mingguan"),
                ("monthly", "Bulanan"),
            )
        ],
        color=TEXT,
        text_style=ft.TextStyle(color=TEXT),
        label_style=ft.TextStyle(color=TEXT),
        filled=True,
        fill_color=FIELD,
        bgcolor=FIELD,
        border_color=BORDER,
        focused_border_color=theme.PRIMARY,
        border_radius=12,
        dense=True,
    )
    routine = ft.Checkbox(
        label="Jadwal rutin saja (tidak masuk saran KALEM)",
        value=False,
        visible=False,
        label_style=ft.TextStyle(color=TEXT),
    )
    repeat_end_text = ft.Text(
        "Tidak ada tanggal akhir", size=10.5, color=MUTED, expand=True
    )
    repeat_end_error = ft.Text("", size=10.5, color=theme.DANGER, visible=False)

    def clear_repeat_end(event=None, *, update=True) -> None:
        repeat_end["value"] = ""
        repeat_end_text.value = "Tidak ada tanggal akhir"
        repeat_end_clear.visible = False
        repeat_end_error.visible = False
        if update:
            page.update()

    def choose_repeat_end(event) -> None:
        chosen = selected_calendar_date(
            repeat_end_picker.value, getattr(event, "data", None)
        )
        if chosen is None:
            return
        repeat_end["value"] = chosen
        repeat_end_text.value = f"Berakhir {_date_label(chosen)}"
        repeat_end_clear.visible = True
        repeat_end_error.visible = False
        page.update()

    repeat_end_picker = ft.DatePicker(
        first_date=today,
        current_date=today,
        last_date=date(today.year + 10, 12, 31),
        help_text="Pilih tanggal berakhir",
        cancel_text="Batal",
        confirm_text="Pilih",
        on_change=choose_repeat_end,
    )
    repeat_end_clear = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_size=16,
        icon_color=MUTED,
        tooltip="Hapus tanggal akhir",
        visible=False,
        on_click=clear_repeat_end,
    )
    repeat_end_holder = ft.Column(
        [
            ft.Text("Berakhir kapan? (opsional)", size=11, color=MUTED),
            ft.Row(
                [
                    ft.OutlinedButton(
                        content=ft.Text("Pilih tanggal akhir", size=11.5, color=TEXT),
                        icon=ft.Icons.EVENT,
                        style=picker_style,
                        on_click=lambda event: page.show_dialog(repeat_end_picker),
                    ),
                    repeat_end_text,
                    repeat_end_clear,
                ],
                spacing=6,
            ),
            repeat_end_error,
        ],
        spacing=4,
        visible=False,
    )

    def change_repeat(event) -> None:
        value = repeat_group.value or "none"
        routine.visible = value != "none"
        repeat_end_holder.visible = value != "none"
        routine.value = value == "weekly"
        if value == "none":
            clear_repeat_end(update=False)
        page.update()

    repeat_group.on_select = change_repeat

    prediction = {
        "minutes": 0,
        "source": "",
        "model_version": "",
        "global_minutes": None,
        "global_dataset_version": "",
        "global_artifact_sha256": "",
        "personalization_version": "",
        "personalization_dataset_version": "",
        "importance": None,
        "deadline_days": None,
    }
    estimate_holder = ft.Container()

    def render_estimate() -> None:
        name = (title_field.value or "").strip()
        if len(name) < 3:
            estimate_holder.content = None
            prediction["minutes"] = 0
            page.update()
            return

        days_left = (
            7
            if no_deadline.value
            else max(0, (task_date["value"] - today).days)
        )
        importance = 8 if important.value else 4
        if days_left <= 1:
            importance = min(10, importance + 2)
        estimate = duration_predictions.predict(
            name,
            deadline_days=days_left,
            importance=importance,
            category="",
            quantity=0.0,
            focus_records=storage.get_focus_records(),
            energy=storage.today_energy() or 3,
        )
        prediction.update(
            {
                "minutes": estimate.menit,
                "source": estimate.sumber,
                "model_version": estimate.model_version,
                "global_minutes": estimate.global_minutes,
                "global_dataset_version": estimate.global_dataset_version,
                "global_artifact_sha256": estimate.global_artifact_sha256,
                "personalization_version": estimate.personalization_version,
                "personalization_dataset_version": (
                    estimate.personalization_dataset_version
                ),
                "importance": importance,
                "deadline_days": days_left,
            }
        )
        range_label = getattr(estimate, "rentang", f"~{estimate.menit} menit")
        sessions = int(getattr(estimate, "sesi", 1) or 1)
        note = getattr(estimate, "catatan", "Estimasi awal berdasarkan pola tugas.")
        estimate_holder.content = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SCHEDULE, size=16, color=theme.PRIMARY),
                            ft.Text(
                                f"Biasanya {range_label}"
                                + (f" · {sessions} sesi" if sessions > 1 else ""),
                                size=13,
                                weight=ft.FontWeight.BOLD,
                                color=TEXT,
                                expand=True,
                            ),
                        ],
                        spacing=6,
                    ),
                    ft.Text(note, size=10.5, color=MUTED),
                ],
                spacing=4,
            ),
            bgcolor=BACKGROUND,
            border_radius=10,
            padding=ft.Padding.symmetric(vertical=8, horizontal=10),
        )
        page.update()

    def render_deadline() -> None:
        has_deadline = not bool(no_deadline.value)
        task_date_holder.visible = has_deadline
        deadline_time_holder.visible = has_deadline
        if not has_deadline:
            set_deadline_time(None)
        render_estimate()

    title_field.on_change = lambda event: render_estimate()
    important.on_change = lambda event: render_estimate()
    no_deadline.on_change = lambda event: render_deadline()

    submit_button = ui_helpers.primary_button("Tambah", None)

    def set_voice_busy(busy: bool) -> None:
        submit_button.disabled = busy

    voice = VoiceDiary(
        page,
        description_field,
        set_voice_busy,
        idle_label="Isi deskripsi pakai suara",
    )

    def cancel(event=None) -> None:
        voice.cleanup()
        navigate("home")

    def submit(event) -> None:
        name = (title_field.value or "").strip()
        if not name:
            title_field.error = "Isi nama tugasnya dulu"
            page.update()
            return

        repeat = repeat_group.value or "none"
        repeat_end_value = repeat_end["value"] if repeat != "none" else ""
        if repeat_end_value and repeat_end_value < task_date["value"]:
            repeat_end_error.value = "Tanggal akhir tidak boleh sebelum tanggal mulai."
            repeat_end_error.visible = True
            page.update()
            return

        scheduled = task_date["value"].isoformat()
        deadline = "" if no_deadline.value else scheduled
        storage.add_task(
            name,
            deadline,
            important.value,
            deadline_time=deadline_time["value"] if deadline else "",
            steps=[{"text": name, "done": False}],
            difficulty_est=int(difficulty.value or 2),
            kategori="",
            jumlah_unit=0.0,
            menit_est=prediction["minutes"],
            description=(description_field.value or "").strip(),
            repeat=repeat,
            scheduled_date=scheduled,
            item_type="schedule" if routine.value else "task",
            repeat_end_date=(
                repeat_end_value.isoformat() if repeat_end_value else ""
            ),
            prediction_model_version=prediction["model_version"],
            prediction_global_minutes=prediction["global_minutes"],
            prediction_global_model_version=prediction["model_version"],
            prediction_global_dataset_version=prediction["global_dataset_version"],
            prediction_global_artifact_sha256=prediction["global_artifact_sha256"],
            prediction_personalization_version=prediction["personalization_version"],
            prediction_personalization_dataset_version=(
                prediction["personalization_dataset_version"]
            ),
            prediction_source=prediction["source"],
            prediction_importance=prediction["importance"],
            prediction_deadline_days=prediction["deadline_days"],
        )
        voice.cleanup()
        navigate("home")

    submit_button.on_click = submit

    def form_card(title: str, controls: list[ft.Control]) -> ft.Control:
        return ft.Container(
            bgcolor=CARD,
            border=ft.Border.all(1, BORDER),
            border_radius=16,
            padding=14,
            content=ft.Column(
                [
                    ft.Text(
                        title,
                        size=13,
                        weight=ft.FontWeight.W_800,
                        color=TEXT,
                    ),
                    *controls,
                ],
                spacing=10,
            ),
        )

    content = ft.Column(
        [
            ui_helpers.page_header("Tambah Tugas", on_back=cancel),
            form_card(
                "Nama + deskripsi",
                [
                    title_field,
                    description_field,
                    description_context,
                    voice.control(),
                ],
            ),
            form_card(
                "Deadline",
                [
                    no_deadline,
                    task_date_holder,
                    deadline_time_holder,
                    repeat_group,
                    routine,
                    repeat_end_holder,
                ],
            ),
            form_card(
                "Penting + tingkat kesulitan",
                [
                    important,
                    ft.Text("Seberat apa buat dimulai?", size=11.5, color=TEXT),
                    difficulty,
                    estimate_holder,
                ],
            ),
            ft.Row(
                [
                    ft.TextButton(
                        content=ft.Text("Batal", color=MUTED),
                        on_click=cancel,
                    ),
                    submit_button,
                ],
                alignment=ft.MainAxisAlignment.END,
                spacing=8,
            ),
            ft.Text(
                "FocusBuddy bukan alat diagnosis ADHD dan bukan pengganti tenaga medis.",
                size=10.5,
                color=TEXT,
                text_align=ft.TextAlign.CENTER,
            ),
        ],
        width=CONTENT_WIDTH,
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    render_deadline()
    return ft.Container(
        expand=True,
        bgcolor=BACKGROUND,
        alignment=ft.Alignment.TOP_CENTER,
        padding=ft.Padding(left=20, top=24, right=20, bottom=18),
        content=content,
    )
