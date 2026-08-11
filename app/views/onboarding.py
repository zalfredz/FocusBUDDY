"""Onboarding singkat untuk membentuk profil awal KALEM."""
from __future__ import annotations

import flet as ft

from app import buddy, storage, theme, ui_helpers

AGE_OPTIONS = ["<18", "18-24", "25-34", "35+"]


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

    name_field = ft.TextField(label="Nama panggilan kamu")
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
    body = ft.Column(spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    def finish(skipped: bool = False):
        answers["name"] = (name_field.value or "").strip() or "Teman"
        answers["skipped_detail"] = skipped
        preset = storage.PRODUCTIVE_PRESETS.get(answers.get("productive_time", ""))
        answers["productive_hours"] = [[preset[0], preset[1]]] if preset else []
        storage.save_profile(answers)
        storage.set_last_brief_date()
        navigate("med_setup" if answers.get("on_medication") == "ya" else "home")

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
        "age_range": "Buat nyesuain gaya bahasa KALEM biar pas sama kamu.",
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

    def render():
        i = step["index"]

        if i == 0:
            body.controls = [
                ui_helpers.card(
                    ft.Column(
                        [
                            buddy.face("tenang", 110),
                            ui_helpers.title("Halo! Aku KALEM."),
                            ft.Text(
                                "Bakal nemenin kamu nemuin ritme hari yang lebih pas. "
                                "Boleh kenalan dulu?",
                                size=13,
                                color=theme.MUTED,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            name_field,
                            ui_helpers.wide_button("Lanjut", lambda e: next_from_name()),
                        ],
                        spacing=14,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                ),
                ui_helpers.disclaimer(
                    "Developed By ATURLAH - FASILKOM UI"
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

        chips: list[ft.Control] = [
            ui_helpers.choice_chip(
                label,
                (value in selected) if multi else (value == selected),
                lambda e, v=value: pick(key, v, multi, limit),
            )
            for value, label in options.items()
        ]

        if is_triggers:
            chips += [
                ui_helpers.choice_chip(t, True, lambda e, v=t: drop_custom_trigger(v))
                for t in answers["custom_triggers"]
            ]
            if picked_count(key) < limit:
                chips.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.ADD, size=13, color=theme.MUTED),
                                ft.Text("Lainnya", size=12.5, color=theme.MUTED),
                            ],
                            spacing=3,
                            tight=True,
                        ),
                        border=ft.Border.all(1, theme.BORDER),
                        border_radius=12,
                        padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                        on_click=lambda e: open_custom(),
                        ink=True,
                    )
                )

        if is_status:
            chips += [
                ui_helpers.choice_chip(t, True, lambda e, v=t: drop_custom_status(v))
                for t in custom_statuses()
            ]
            if len(answers["status"]) < limit:
                chips.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.ADD, size=13, color=theme.MUTED),
                                ft.Text("Lainnya", size=12.5, color=theme.MUTED),
                            ],
                            spacing=3,
                            tight=True,
                        ),
                        border=ft.Border.all(1, theme.BORDER),
                        border_radius=12,
                        padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                        on_click=lambda e: open_status_custom(),
                        ink=True,
                    )
                )

        card_items: list[ft.Control] = [
            ui_helpers.title(question, 18),
            ft.Text(WHY[key], size=12, color=theme.MUTED),
            ft.Row(chips, spacing=8, wrap=True, run_spacing=8),
        ]

        if is_triggers and step["custom_open"] and picked_count(key) < limit:
            card_items.append(
                ft.Row(
                    [
                        custom_field,
                        ft.IconButton(
                            icon=ft.Icons.CHECK,
                            icon_color=theme.PRIMARY,
                            icon_size=20,
                            on_click=lambda e: add_custom_trigger(),
                        ),
                    ],
                    spacing=4,
                )
            )

        if is_status and step["status_custom_open"] and len(answers["status"]) < limit:
            card_items.append(
                ft.Row(
                    [
                        status_field,
                        ft.IconButton(
                            icon=ft.Icons.CHECK,
                            icon_color=theme.PRIMARY,
                            icon_size=20,
                            on_click=lambda e: add_custom_status(),
                        ),
                    ],
                    spacing=4,
                )
            )

        controls: list[ft.Control] = [
            ft.Row(
                [
                    ft.Container(
                        height=4,
                        expand=True,
                        bgcolor=theme.PRIMARY if n < i else theme.BORDER,
                        border_radius=2,
                    )
                    for n in range(len(QUESTIONS))
                ],
                spacing=4,
            ),
            ft.Text(f"{i} dari {len(QUESTIONS)}", size=11, color=theme.MUTED),
            ui_helpers.card(ft.Column(card_items, spacing=12)),
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
            controls.append(ft.Row(nav, spacing=8))

        if i > 1:
            controls.append(
                ft.Row(
                    [
                        ft.TextButton(
                            content=ft.Text("Lewati, langsung ke Beranda", color=theme.MUTED),
                            on_click=lambda e: skip_to_home(),
                        )
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                )
            )

        body.controls = controls
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
    return body
