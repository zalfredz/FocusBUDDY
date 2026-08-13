"""Onboarding singkat untuk membentuk profil awal KALEM."""
from __future__ import annotations

from datetime import date

import flet as ft

from app import storage
from app.date_utils import selected_calendar_date, years_before

BACKGROUND = "#141416"
TEXT_PRIMARY = "#FFFFFF"
TEXT_FIELD = "#343446"
INPUT_BG = "#24242F"
BUTTON_BG = "#DDE0FF"
BUTTON_TEXT = "#181A35"
KALEM_GREEN = "#95D899"
FONT = "Plus Jakarta Sans"
FORM_WIDTH = 340

MONTH_NAMES = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)


def _birth_date_label(value: str) -> str:
    try:
        selected = date.fromisoformat(value)
    except (TypeError, ValueError):
        return "Pilih tanggal lahir"
    return f"{selected.day} {MONTH_NAMES[selected.month - 1]} {selected.year}"


def build(page: ft.Page, navigate) -> ft.Control:
    answers: dict = {
        "name": "",
        "birth_date": "",
        "age_range": "",
        "status": [],
        "productive_time": "",
        "sleep_condition": "",
        "on_medication": "",
        "overwhelm_triggers": [],
        "custom_triggers": [],
    }
    step = {
        "index": 0,
        "error": "",
        "custom_open": False,
        "status_custom_open": False,
    }

    name_field = ft.TextField(
        label="Nama panggilan kamu",
        color=TEXT_PRIMARY,
        hint_style=ft.TextStyle(color="#B9B8C8", font_family=FONT),
        cursor_color=TEXT_PRIMARY,
        bgcolor=TEXT_FIELD,
        filled=True,
        border=ft.InputBorder.NONE,
        border_radius=12,
        height=46,
        width=FORM_WIDTH,
        content_padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        text_size=14,
        on_submit=lambda e: next_from_name(),
    )
    status_field = ft.TextField(
        hint_text="Tulis kesibukan kamu",
        text_size=12,
        height=42,
        content_padding=ft.Padding.symmetric(vertical=4, horizontal=10),
        expand=True,
        autofocus=True,
        on_submit=lambda e: add_custom_status(),
    )
    custom_field = ft.TextField(
        hint_text="Tulis sendiri, mis. rapat mendadak",
        text_size=12,
        height=42,
        content_padding=ft.Padding.symmetric(vertical=4, horizontal=10),
        expand=True,
        autofocus=True,
        on_submit=lambda e: add_custom_trigger(),
    )
    body = ft.Column(
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    today = date.today()
    birth_picker = ft.DatePicker(
        value=None,
        first_date=date(today.year - 100, 1, 1),
        current_date=years_before(today, 20),
        last_date=today,
        help_text="Pilih tanggal lahir",
        cancel_text="Batal",
        confirm_text="Pilih",
    )

    QUESTIONS = [
        ("birth_date", "Tanggal Lahir Kamu?"),
        ("status", "Apa kesibukan kamu saat ini?"),
        ("productive_time", "Kapan biasanya kamu paling enak buat fokus?"),
        ("sleep_condition", "Pola tidur kamu akhir-akhir ini gimana?"),
        ("on_medication", "Ada obat atau suplemen yang lagi kamu minum rutin?"),
        ("overwhelm_triggers", "Hal apa yang paling sering bikin kamu overwhelm?"),
    ]

    WHY = {
        "birth_date": "Tanggal lahir disimpan sebagai data profil. Usia dihitung otomatis saat diperlukan.",
        "status": "Biar KALEM tahu gambaran ritme hari-harimu.",
        "productive_time": "Biar KALEM tahu kapan harus bantu kamu fokus atau nurunin "
                           "ekspektasi pas kamu lagi capek.",
        "sleep_condition": "Biar KALEM tahu seberapa ramah target hari ini buat energi kamu.",
        "on_medication": "Biar KALEM bantu pantau sisa stok dan ngingetin jadwalnya. "
                         "Bisa dilewati kalau nggak ada.",
        "overwhelm_triggers": "Biar KALEM paham pemicunya dan bisa bantu kasih penenang "
                               "yang tepat pas kamu butuh.",
    }

    def finish(skipped: bool = False) -> None:
        answers["name"] = (name_field.value or "").strip() or "Teman"
        answers["skipped_detail"] = skipped
        preset = storage.PRODUCTIVE_PRESETS.get(answers.get("productive_time", ""))
        answers["productive_hours"] = [[preset[0], preset[1]]] if preset else []
        storage.save_profile(answers)
        if answers.get("on_medication") == "ya":
            setattr(page, "_focusbuddy_med_setup_return", "home")
            navigate("med_setup")
        else:
            navigate("home")

    def kalem_title(size: int = 30) -> ft.Text:
        return ft.Text(
            spans=[
                ft.TextSpan(
                    "Haloo\nAku ",
                    style=ft.TextStyle(
                        color=TEXT_PRIMARY,
                        font_family=FONT,
                        size=size,
                        height=1.22,
                        weight=ft.FontWeight.W_700,
                    ),
                ),
                ft.TextSpan(
                    "KALEM!",
                    style=ft.TextStyle(
                        color=KALEM_GREEN,
                        font_family=FONT,
                        size=size,
                        height=1.22,
                        weight=ft.FontWeight.W_700,
                    ),
                ),
            ],
            text_align=ft.TextAlign.LEFT,
        )

    def intro(progress_image: str) -> list[ft.Control]:
        return [
            kalem_title(26),
            ft.Text(
                "Agar pengalamanmu lebih terpersonalisasi, isi pertanyaannya ya.",
                size=14,
                color=TEXT_PRIMARY,
                font_family=FONT,
                text_align=ft.TextAlign.JUSTIFY,
            ),
            ft.Container(height=135),
            ft.Image(src=progress_image, height=42, fit=ft.BoxFit.CONTAIN),
        ]

    def pill_button(
        label: str,
        on_click,
        *,
        outlined: bool = False,
        expand: bool = True,
        width: int | None = None,
    ) -> ft.Control:
        return ft.Button(
            height=48,
            expand=expand,
            width=width,
            content=ft.Text(
                label,
                size=15,
                color=BUTTON_BG if outlined else BUTTON_TEXT,
                font_family=FONT,
                weight=ft.FontWeight.W_700,
            ),
            style=ft.ButtonStyle(
                bgcolor=BUTTON_TEXT if outlined else BUTTON_BG,
                color=BUTTON_BG if outlined else BUTTON_TEXT,
                padding=0,
                side=ft.BorderSide(1, BUTTON_BG) if outlined else None,
                shape=ft.RoundedRectangleBorder(radius=100),
            ),
            on_click=on_click,
        )

    def selected_dropdown_value(key: str) -> str | None:
        if key == "status":
            selected = answers["status"]
            if not selected:
                return "lainnya" if step["status_custom_open"] else None
            return selected[0] if selected[0] in storage.STATUS_OPTIONS else "lainnya"
        if key == "overwhelm_triggers":
            selected = answers["overwhelm_triggers"]
            if selected:
                return selected[0]
            if answers["custom_triggers"] or step["custom_open"]:
                return "lainnya"
            return None
        return answers.get(key) or None

    def dropdown(
        key: str,
        options: dict[str, str],
        hint: str,
        *,
        include_custom: bool = False,
    ) -> ft.Dropdown:
        choices = [
            ft.DropdownOption(
                key=value,
                text=label,
                content=ft.Text(
                    label,
                    color=TEXT_PRIMARY,
                    font_family=FONT,
                    size=13,
                ),
            )
            for value, label in options.items()
        ]
        if include_custom:
            choices.append(
                ft.DropdownOption(
                    key="lainnya",
                    text="Lainnya",
                    content=ft.Text(
                        "Lainnya",
                        color=TEXT_PRIMARY,
                        font_family=FONT,
                        size=13,
                    ),
                )
            )
        return ft.Dropdown(
            value=selected_dropdown_value(key),
            options=choices,
            hint_text=hint,
            text_size=13,
            color=TEXT_PRIMARY,
            text_style=ft.TextStyle(color=TEXT_PRIMARY, font_family=FONT, size=13),
            hint_style=ft.TextStyle(color="#B9B8C8", font_family=FONT),
            filled=True,
            fill_color=INPUT_BG,
            bgcolor=INPUT_BG,
            border=ft.InputBorder.NONE,
            border_radius=10,
            content_padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            dense=True,
            enable_search=False,
            on_select=lambda e: select_dropdown(key, e.control.value or ""),
        )

    def select_dropdown(key: str, value: str) -> None:
        step["error"] = ""
        if key == "status":
            step["status_custom_open"] = value == "lainnya"
            answers["status"] = [] if value == "lainnya" else [value]
        elif key == "overwhelm_triggers":
            step["custom_open"] = value == "lainnya"
            answers["overwhelm_triggers"] = [] if value == "lainnya" else [value]
            answers["custom_triggers"] = []
        else:
            answers[key] = value
        render()

    def choose_birth_date(e) -> None:
        selected = selected_calendar_date(
            birth_picker.value, getattr(e, "data", None)
        )
        if selected is None:
            return
        answers["birth_date"] = selected.isoformat()
        answers["age_range"] = storage.age_range_from_birth_date(answers["birth_date"])
        step["error"] = ""
        render()

    birth_picker.on_change = choose_birth_date

    def add_custom_status() -> None:
        text = (status_field.value or "").strip()[:32]
        if text:
            answers["status"] = [text]
            step["error"] = ""
        status_field.value = ""
        step["status_custom_open"] = not bool(text)
        render()

    def add_custom_trigger() -> None:
        text = (custom_field.value or "").strip()[:32]
        if text:
            answers["custom_triggers"] = [text]
            step["error"] = ""
        custom_field.value = ""
        step["custom_open"] = not bool(text)
        render()

    def answer_control(key: str) -> ft.Control:
        if key == "birth_date":
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.CALENDAR_MONTH, color=TEXT_PRIMARY, size=19),
                        ft.Text(
                            _birth_date_label(answers["birth_date"]),
                            size=13,
                            color=TEXT_PRIMARY,
                            font_family=FONT,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=TEXT_PRIMARY),
                    ],
                    spacing=9,
                ),
                height=48,
                bgcolor=INPUT_BG,
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=14),
                on_click=lambda e: page.show_dialog(birth_picker),
                ink=True,
            )
        if key == "status":
            return dropdown(
                key,
                {value: label for value, label in storage.STATUS_OPTIONS.items() if value != "lainnya"},
                "Pilih pekerjaan atau kesibukan",
                include_custom=True,
            )
        if key == "productive_time":
            return dropdown(key, storage.PRODUCTIVE_TIME_OPTIONS, "Pilih waktu produktif")
        if key == "sleep_condition":
            return dropdown(key, storage.SLEEP_OPTIONS, "Pilih pola tidur")
        if key == "on_medication":
            return dropdown(key, storage.MEDICATION_OPTIONS, "Pilih kondisi obat atau suplemen")
        return dropdown(
            key,
            storage.TRIGGER_OPTIONS,
            "Pilih pemicu yang paling sering",
            include_custom=True,
        )

    def custom_input(key: str) -> ft.Control | None:
        if key == "status" and step["status_custom_open"]:
            return ft.Row(
                [
                    status_field,
                    ft.IconButton(
                        icon=ft.Icons.CHECK,
                        icon_color=BUTTON_BG,
                        icon_size=20,
                        on_click=lambda e: add_custom_status(),
                    ),
                ],
                spacing=4,
            )
        if key == "overwhelm_triggers" and step["custom_open"]:
            return ft.Row(
                [
                    custom_field,
                    ft.IconButton(
                        icon=ft.Icons.CHECK,
                        icon_color=BUTTON_BG,
                        icon_size=20,
                        on_click=lambda e: add_custom_trigger(),
                    ),
                ],
                spacing=4,
            )
        return None

    def has_answer(key: str) -> bool:
        if key == "status":
            return bool(answers["status"])
        if key == "overwhelm_triggers":
            return bool(answers["overwhelm_triggers"] or answers["custom_triggers"])
        return bool(answers.get(key))

    def render() -> None:
        i = step["index"]
        if i == 0:
            body.controls = [
                ft.Container(
                    padding=ft.Padding(left=24, top=48, right=24, bottom=32),
                    content=ft.Column(
                        [
                            kalem_title(),
                            ft.Text(
                                "Agar pengalamanmu lebih terpersonalisasi, tolong isi semua "
                                "pertanyaannya ya!",
                                size=14,
                                color=TEXT_PRIMARY,
                                font_family=FONT,
                                text_align=ft.TextAlign.JUSTIFY,
                            ),
                            ft.Container(height=135),
                            ft.Image(src="Property 1=q1.png", height=42, fit=ft.BoxFit.CONTAIN),
                            ft.Column(
                                [
                                    ft.Text(
                                        "Mau dipanggil apa?",
                                        size=20,
                                        color=TEXT_PRIMARY,
                                        font_family=FONT,
                                        width=FORM_WIDTH,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    name_field,
                                ],
                                spacing=10,
                                tight=True,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(
                                [
                                    pill_button(
                                        "Selanjutnya",
                                        lambda e: next_from_name(),
                                    ),
                                ],
                                spacing=0,
                            ),
                            ft.Text(
                                "Developed By ATURLAH - FASILKOM UI",
                                size=10.5,
                                color=TEXT_PRIMARY,
                                font_family=FONT,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        spacing=14,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        tight=True,
                    ),
                )
            ]
            page.update()
            return

        if i > len(QUESTIONS):
            finish()
            return

        key, question = QUESTIONS[i - 1]
        input_control = answer_control(key)
        card_controls: list[ft.Control] = [
            ft.Text(
                WHY[key],
                size=11.5,
                color=BUTTON_BG,
                font_family=FONT,
                text_align=ft.TextAlign.JUSTIFY,
            ),
            input_control,
        ]
        extra = custom_input(key)
        if extra is not None:
            card_controls.append(extra)
        if step["error"]:
            card_controls.append(
                ft.Text(step["error"], size=11, color="#FF8A80", font_family=FONT)
            )

        question_controls: list[ft.Control] = [
            ft.Text(
                question,
                size=20,
                color=TEXT_PRIMARY,
                font_family=FONT,
                text_align=(
                    ft.TextAlign.CENTER
                    if key == "birth_date"
                    else ft.TextAlign.LEFT
                ),
            ),
            ft.Container(
                bgcolor=TEXT_FIELD,
                border_radius=16,
                padding=18,
                content=ft.Column(
                    card_controls,
                    spacing=12,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ),
        ]

        controls: list[ft.Control] = [
            *intro(f"Property 1=q{min(i + 1, 6)}.png"),
            ft.Column(
                question_controls,
                spacing=10,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            ft.Row(
                [
                    pill_button(
                        "Selanjutnya" if key == "birth_date" else "Lewati",
                        lambda e: advance(),
                    ),
                ],
                spacing=0,
            ),
        ]

        body.controls = [
            ft.Container(
                padding=ft.Padding(left=24, top=48, right=24, bottom=32),
                content=ft.Column(
                    controls,
                    spacing=14,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    tight=True,
                ),
            )
        ]
        page.update()

    def next_from_name() -> None:
        if not (name_field.value or "").strip():
            name_field.error = "Isi dulu ya"
            page.update()
            return
        name_field.error = None
        answers["name"] = (name_field.value or "").strip()
        step["index"] = 1
        step["error"] = ""
        render()

    def advance() -> None:
        key, _ = QUESTIONS[step["index"] - 1]
        if key == "birth_date" and not has_answer(key):
            step["error"] = "Pilih atau isi jawaban dulu ya."
            render()
            return
        step["error"] = ""
        if step["index"] == len(QUESTIONS):
            optional_keys = [question_key for question_key, _ in QUESTIONS[1:]]
            finish(
                skipped=any(
                    not has_answer(question_key) for question_key in optional_keys
                )
            )
            return
        step["index"] += 1
        step["custom_open"] = False
        step["status_custom_open"] = False
        render()

    render()
    return ft.Stack(
        [
            ft.Container(
                bgcolor=BACKGROUND,
                alignment=ft.Alignment.CENTER,
                content=ft.Image(
                    src="Property 1=good_mood.png",
                    width=620,
                    height=680,
                    fit=ft.BoxFit.CONTAIN,
                    opacity=0.70,
                ),
            ),
            ft.Container(
                bgcolor="#59141416",
                blur=ft.Blur(sigma_x=24, sigma_y=24),
                ignore_interactions=True,
            ),
            ft.Container(alignment=ft.Alignment.TOP_CENTER, content=body),
        ],
        fit=ft.StackFit.EXPAND,
        expand=True,
    )
