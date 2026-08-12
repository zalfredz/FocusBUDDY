"""Onboarding singkat untuk membentuk profil awal KALEM."""
from __future__ import annotations

import flet as ft

from app import buddy, storage, theme, ui_helpers

AGE_OPTIONS = ["<18", "18-24", "25-34", "35+"]

BACKGROUND = "#141416"
TEXT_PRIMARY = "#FFFFFF"
TEXT_FIELD = "#343446"
BUTTON_BG = "#DDE0FF"
BUTTON_TEXT = "#181A35"
FONT = "Plus Jakarta Sans"


def build(page: ft.Page, navigate) -> ft.Control:
    answers: dict = {
        "name": "",
        "age_range": "",
        "status": [],
        "productive_time": "",
        "sleep_condition": "",
        "on_medication": "",
        "overwhelm_triggers": [],
        "custom_triggers": [],
    }
    step = {"index": 0, "custom_open": False, "status_custom_open": False}

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

    def finish(skipped: bool = False):
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

    QUESTIONS = [
        ("age_range", "Berapa usia kamu sekarang?", {a: a for a in AGE_OPTIONS}, False, 1),
        ("status", "Apa kesibukan kamu saat ini?",
         {key: label for key, label in storage.STATUS_OPTIONS.items() if key != "lainnya"},
         True, storage.MAX_STATUS),
        ("productive_time", "Kapan biasanya kamu paling enak buat fokus?",
         storage.PRODUCTIVE_TIME_OPTIONS, False, 1),
        ("sleep_condition", "Pola tidur kamu akhir-akhir ini gimana?",
         storage.SLEEP_OPTIONS, False, 1),
        ("on_medication", "Ada obat atau suplemen yang lagi kamu minum rutin?",
         storage.MEDICATION_OPTIONS, False, 1),
        ("overwhelm_triggers", "Hal apa yang paling sering bikin kamu overwhelm?",
         storage.TRIGGER_OPTIONS, True, storage.MAX_TRIGGERS),
    ]

    WHY = {
        "age_range": "Disimpan sebagai konteks profil dan bisa kamu ubah kapan pun.",
        "status": f"Biar KALEM tahu gambaran ritme hari-harimu. Boleh pilih maksimal "
                  f"{storage.MAX_STATUS} ya.",
        "productive_time": "Biar KALEM tahu kapan harus bantu kamu fokus atau nurunin "
                           "ekspektasi pas kamu lagi capek.",
        "sleep_condition": "Biar KALEM tahu seberapa ramah target hari ini buat energi kamu.",
        "on_medication": "Biar KALEM bantu pantau sisa stok dan ngingetin jadwalnya. "
                         "Bisa dilewati kalau nggak ada.",
        "overwhelm_triggers": f"Biar KALEM paham pemicunya dan bisa bantu kasih penenang "
                              f"yang tepat pas kamu butuh. (Pilih maks. {storage.MAX_TRIGGERS})",
    }

    def picked_count(key: str) -> int:
        if key == "overwhelm_triggers":
            return len(answers["overwhelm_triggers"]) + len(answers["custom_triggers"])
        return len(answers[key])

    def pick(key: str, value: str, multi: bool, limit: int):
        if multi:
            current = answers[key]
            if value in current:
                current.remove(value)
            elif picked_count(key) < limit:
                current.append(value)
        else:
            answers[key] = value
            step["index"] += 1
        render()

    def add_custom_trigger():
        raw = (custom_field.value or "").strip()
        text = raw[:32]
        if (
            text
            and text not in answers["custom_triggers"]
            and picked_count("overwhelm_triggers") < storage.MAX_TRIGGERS
        ):
            answers["custom_triggers"].append(text)
        custom_field.value = ""
        step["custom_open"] = False
        render()

    def drop_custom_trigger(value: str):
        if value in answers["custom_triggers"]:
            answers["custom_triggers"].remove(value)
        render()

    def custom_statuses() -> list[str]:
        return [value for value in answers["status"] if value not in storage.STATUS_OPTIONS]

    def add_custom_status():
        raw = (status_field.value or "").strip()
        text = raw[:32]
        if text and text not in answers["status"] and len(answers["status"]) < storage.MAX_STATUS:
            answers["status"].append(text)
        status_field.value = ""
        step["status_custom_open"] = False
        render()

    def drop_custom_status(value: str):
        if value in answers["status"]:
            answers["status"].remove(value)
        render()

    def option_tile(label: str, selected: bool, on_click) -> ft.Control:
        return ft.Container(
            content=ft.Text(
                label,
                size=12.5,
                color=BUTTON_TEXT,
                font_family=FONT,
                weight=ft.FontWeight.W_700,
                text_align=ft.TextAlign.CENTER,
            ),
            height=46,
            expand=True,
            alignment=ft.Alignment.CENTER,
            bgcolor="#AEEEF8" if selected else BUTTON_BG,
            border=ft.Border.all(2, "#95D899" if selected else BUTTON_BG),
            border_radius=10,
            padding=ft.Padding.symmetric(horizontal=8),
            on_click=on_click,
            ink=True,
        )

    def option_grid(controls: list[ft.Control]) -> ft.Control:
        rows: list[ft.Control] = []
        for index in range(0, len(controls), 2):
            pair = controls[index:index + 2]
            if len(pair) == 1:
                pair.append(ft.Container(expand=True))
            rows.append(ft.Row(pair, spacing=8))
        return ft.Column(rows, spacing=8, tight=True)

    def pill_button(label: str, on_click, *, outlined: bool = False) -> ft.Control:
        return ft.Button(
            height=48,
            expand=True,
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

    def intro(name: str, progress_image: str) -> list[ft.Control]:
        return [
            ui_helpers.brand_text(
                f"Hi {name}! Aku Kalem!",
                size=26,
                color=TEXT_PRIMARY,
                font_family=FONT,
                weight=ft.FontWeight.W_400,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Text(
                "Agar pengalamanmu lebih terpersonalisasi, isi pertanyaannya ya.",
                size=14,
                color=TEXT_PRIMARY,
                font_family=FONT,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(height=210),
            ft.Image(src=progress_image, height=48, fit=ft.BoxFit.CONTAIN),
        ]

    def render():
        i = step["index"]

        if i == 0:
            body.controls = [
                ft.Container(
                    padding=ft.Padding(left=24, top=48, right=24, bottom=32),
                    content=ft.Column(
                        [
                            ft.Text(
                                "Halo! Aku KALEM.",
                                size=32,
                                color="#95D899",
                                font_family=FONT,
                                weight=ft.FontWeight.W_700,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Text(
                                "Agar pengalamanmu lebih terpersonalisasi,\n"
                                "tolong isi semua pertanyaannya ya!",
                                size=14,
                                color=TEXT_PRIMARY,
                                font_family=FONT,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Container(height=210),
                            ft.Image(
                                src="Property 1=q1.png",
                                height=48,
                                fit=ft.BoxFit.CONTAIN,
                            ),
                            ft.Text(
                                "Mau dipanggil apa?",
                                size=20,
                                color=TEXT_PRIMARY,
                                font_family=FONT,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            name_field,
                            ft.Row([pill_button("Lanjut", lambda e: next_from_name())]),
                            ft.Text(
                                "Developed By ATURLAH - FASILKOM UI",
                                size=10.5,
                                color=TEXT_PRIMARY,
                                font_family=FONT,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        spacing=18,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        tight=True,
                    ),
                ),
            ]
            page.update()
            return

        if i > len(QUESTIONS):
            finish()
            return

        key, question, options, multi, limit = QUESTIONS[i - 1]
        selected = answers[key]
        is_triggers = key == "overwhelm_triggers"
        is_status = key == "status"

        option_controls: list[ft.Control] = [
            option_tile(
                label,
                (value in selected) if multi else (value == selected),
                lambda e, v=value: pick(key, v, multi, limit),
            )
            for value, label in options.items()
        ]

        if is_triggers:
            option_controls += [
                option_tile(t, True, lambda e, v=t: drop_custom_trigger(v))
                for t in answers["custom_triggers"]
            ]
            if picked_count(key) < limit:
                option_controls.append(
                    option_tile("Lainnya", step["custom_open"], lambda e: open_custom())
                )

        if is_status:
            option_controls += [
                option_tile(t, True, lambda e, v=t: drop_custom_status(v))
                for t in custom_statuses()
            ]
            if len(answers["status"]) < limit:
                option_controls.append(
                    option_tile(
                        "Lainnya",
                        step["status_custom_open"],
                        lambda e: open_status_custom(),
                    )
                )

        card_items: list[ft.Control] = [
            ft.Text(
                question,
                size=20,
                color=TEXT_PRIMARY,
                font_family=FONT,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(
                bgcolor=TEXT_FIELD,
                border_radius=16,
                padding=18,
                content=ft.Column(
                    [
                        ft.Text(WHY[key], size=11.5, color=BUTTON_BG),
                        option_grid(option_controls),
                    ],
                    spacing=12,
                    tight=True,
                ),
            ),
        ]

        if is_triggers and step["custom_open"] and picked_count(key) < limit:
            card_items[1].content.controls.append(
                ft.Row(
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
            )

        if is_status and step["status_custom_open"] and len(answers["status"]) < limit:
            card_items[1].content.controls.append(
                ft.Row(
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
            )

        progress_image = f"Property 1=q{min(i + 1, 6)}.png"
        controls: list[ft.Control] = [
            *intro(answers["name"] or (name_field.value or "Teman"), progress_image),
            *card_items,
        ]

        nav: list[ft.Control] = []
        if i > 1:
            nav.append(ft.TextButton(content=ft.Text("Kembali"), on_click=lambda e: go_back()))
        if multi:
            last = i == len(QUESTIONS)
            nav.append(
                ui_helpers.primary_button(
                    "Selesai" if last else "Lanjut",
                    (lambda e: finish()) if last else (lambda e: go_next()),
                    expand=True,
                )
            )
        if nav:
            controls.append(
                ft.Row(
                    [
                        pill_button(
                            "Selesai" if i == len(QUESTIONS) else "Lanjut",
                            (lambda e: finish())
                            if i == len(QUESTIONS)
                            else (lambda e: go_next()),
                        ),
                        pill_button("Kembali", lambda e: go_back(), outlined=True),
                    ],
                    spacing=8,
                )
            )

        if i > 1:
            controls.append(
                ft.Row(
                    [
                        ft.TextButton(
                            content=ft.Text("Lewati, langsung ke Beranda", color=BUTTON_BG),
                            on_click=lambda e: skip_to_home(),
                        )
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                )
            )

        body.controls = [
            ft.Container(
                padding=ft.Padding(left=24, top=48, right=24, bottom=32),
                content=ft.Column(
                    controls,
                    spacing=18,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    tight=True,
                ),
            )
        ]
        page.update()

    def open_custom():
        step["custom_open"] = True
        render()

    def open_status_custom():
        step["status_custom_open"] = True
        render()

    def next_from_name():
        if not (name_field.value or "").strip():
            name_field.error = "Isi dulu ya"
            page.update()
            return
        name_field.error = None
        step["index"] = 1
        render()

    def go_next():
        step["index"] += 1
        step["custom_open"] = False
        step["status_custom_open"] = False
        render()

    def go_back():
        step["index"] = max(step["index"] - 1, 0)
        step["custom_open"] = False
        step["status_custom_open"] = False
        render()

    def skip_to_home():
        finish(skipped=True)

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
