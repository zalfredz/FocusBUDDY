"""Flow recovery OVERWHELM: grounding, napas, lalu check-in hasil."""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

import flet as ft

from app import buddy, storage, theme, ui_helpers
from app.core.reset_preferences import (
    CRISIS_HOTLINES,
    TELEHEALTH_PARTNERS,
    detect_distress,
)


BREATHING_STEPS = [
    ("Tarik napas...", 4, 1.0),
    ("Tahan...", 7, 1.0),
    ("Buang pelan-pelan...", 8, 0.55),
]

GROUNDING_STEPS = [
    (5, "hal yang bisa kamu LIHAT", ft.Icons.VISIBILITY),
    (4, "hal yang bisa kamu SENTUH", ft.Icons.BACK_HAND),
    (3, "suara yang bisa kamu DENGER", ft.Icons.HEARING),
    (2, "bau yang bisa kamu CIUM", ft.Icons.AIR),
    (1, "hal yang kamu SYUKURIN hari ini", ft.Icons.FAVORITE),
]

EVENT_CHOICE = "overwhelm"
STAGE_OPEN = "opened"
STAGE_GROUNDING_DONE = "grounding_54321_done"
STAGE_BREATHING_DONE = "breathing_478_done"
STAGE_CHECKIN_NOT_READY = "checkin_belum_bisa"
STAGE_CHECKIN_IMPROVED = "checkin_sedikit_lebih_baik"
STAGE_RETRY = "recovery_repeated"


def build(page: ft.Page, navigate) -> ft.Control:
    body = ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)
    distress = detect_distress(storage.get_reset_events(), storage.get_mood_logs())

    recovery_event = storage.add_reset_event(EVENT_CHOICE)
    recovery_event_id = recovery_event["id"]
    storage.append_reset_stage(recovery_event_id, STAGE_OPEN)

    def log_stage(stage: str) -> None:
        storage.append_reset_stage(recovery_event_id, stage)

    def hotline_rows() -> list[ft.Control]:
        rows: list[ft.Control] = []
        for hotline in CRISIS_HOTLINES:
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.CALL, color="#FFFFFF", size=22),
                            ft.Column(
                                [
                                    ft.Text(
                                        hotline["number"],
                                        size=19,
                                        weight=ft.FontWeight.BOLD,
                                        color="#FFFFFF",
                                    ),
                                    ft.Text(
                                        f"{hotline['name']} · {hotline['desc']}",
                                        size=11,
                                        color="#FFFFFF",
                                    ),
                                ],
                                spacing=1,
                                expand=True,
                            ),
                            ft.Icon(ft.Icons.ARROW_OUTWARD, color="#FFFFFF", size=16),
                        ],
                        spacing=12,
                    ),
                    padding=ft.Padding.symmetric(vertical=12, horizontal=14),
                    bgcolor=theme.PRIMARY,
                    border_radius=12,
                    url=hotline["tel"],
                    ink=True,
                )
            )
            if hotline.get("web"):
                rows.append(
                    ft.TextButton(
                        content=ft.Text(
                            "Buka Healing119.id", size=12, color=theme.PRIMARY
                        ),
                        icon=ft.Icons.OPEN_IN_NEW,
                        url=hotline["web"],
                    )
                )
        return rows

    def professional_card(prominent: bool) -> ft.Control:
        partner_rows = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.SUPPORT_AGENT, color=theme.PRIMARY, size=20),
                        ft.Column(
                            [
                                ft.Text(
                                    partner["name"],
                                    weight=ft.FontWeight.BOLD,
                                    size=13,
                                    color=theme.ON_BACKGROUND,
                                ),
                                ft.Text(partner["desc"], size=11, color=theme.MUTED),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.OPEN_IN_NEW, color=theme.MUTED, size=16),
                    ],
                    spacing=12,
                ),
                padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                bgcolor=theme.BACKGROUND,
                border_radius=12,
                url=partner["url"],
                ink=True,
            )
            for partner in TELEHEALTH_PARTNERS
        ]
        if prominent:
            header = ft.Column(
                [
                    ui_helpers.banner(
                        "KALEM lihat ini bukan cuma capek biasa",
                        theme.DANGER,
                        ft.Icons.FAVORITE,
                    ),
                    ft.Text(distress.reason, size=12, color=theme.MUTED),
                    ft.Text(
                        "Nggak apa-apa minta bantuan. Ngobrol dengan orang yang "
                        "terlatih bisa membantu saat rasanya terlalu berat.",
                        size=13,
                        color=theme.ON_BACKGROUND,
                    ),
                ],
                spacing=8,
            )
        else:
            header = ft.Column(
                [
                    ui_helpers.section_header("Ngobrol dengan profesional"),
                    ft.Text(
                        "Kalau rasanya kebanyakan untuk dihadapi sendiri, layanan "
                        "yang sudah tersedia ini bisa kamu hubungi.",
                        size=12,
                        color=theme.MUTED,
                    ),
                ],
                spacing=6,
            )
        rows = (
            [*hotline_rows(), *partner_rows]
            if prominent
            else [*partner_rows, *hotline_rows()]
        )
        return ui_helpers.card(
            ft.Column([header, *rows], spacing=10), bgcolor=theme.SURFACE
        )

    def set_activity(
        title: str,
        inner: ft.Control,
        on_back: Optional[Callable] = None,
    ) -> None:
        controls: list[ft.Control] = [
            ui_helpers.page_header(title, on_back=on_back),
            ui_helpers.card(inner),
        ]
        if on_back is not None:
            controls.append(ui_helpers.soft_button("Kembali", on_back))
        body.controls = controls
        page.update()

    def show_light_menu() -> None:
        body.controls = [
            ui_helpers.page_header(
                "OVERWHELM", on_back=lambda event: navigate("home")
            ),
            buddy.face("tenang", 100),
            ui_helpers.title("Pelan-pelan aja.", 19),
            ft.Text(
                "Kalau masih butuh waktu, pilih satu bantuan yang terasa paling ringan.",
                size=12.5,
                color=theme.MUTED,
                text_align=ft.TextAlign.CENTER,
            ),
            ui_helpers.wide_button(
                "Balik ke sini",
                lambda event: show_grounding(next_stage="light"),
                icon=ft.Icons.VISIBILITY,
            ),
            ui_helpers.wide_button(
                "Latihan napas 4-7-8",
                lambda event: show_breathing(next_stage="light"),
                icon=ft.Icons.AIR,
            ),
            professional_card(prominent=False),
            ui_helpers.disclaimer(
                "FocusBuddy bukan layanan krisis. Kalau kamu dalam bahaya langsung, "
                "hubungi layanan darurat atau nomor di atas."
            ),
        ]
        page.update()

    def show_outcome() -> None:
        def answer(improved: bool) -> None:
            if improved:
                log_stage(STAGE_CHECKIN_IMPROVED)
                storage.complete_reset_event(recovery_event_id, improved=True)
                show_light_menu()
                return
            log_stage(STAGE_CHECKIN_NOT_READY)
            log_stage(STAGE_RETRY)
            show_grounding(next_stage="breathing")

        body.controls = [
            ui_helpers.page_header(""),
            buddy.face("tenang", 110),
            ui_helpers.title("Sekarang rasanya gimana?", 19),
            ft.Text(
                "Jawaban kamu yang menentukan langkah berikutnya. Nggak harus "
                "langsung terasa pulih.",
                size=12.5,
                color=theme.MUTED,
                text_align=ft.TextAlign.CENTER,
            ),
            ui_helpers.wide_button(
                "Sedikit lebih baik",
                lambda event: answer(True),
                icon=ft.Icons.FAVORITE,
            ),
            ft.OutlinedButton(
                content=ft.Text("Belum bisa"),
                on_click=lambda event: answer(False),
            ),
        ]
        page.update()

    def show_breathing(next_stage: str) -> None:
        running = {"active": True}
        circle = ft.Container(
            width=170,
            height=170,
            border_radius=85,
            bgcolor=ft.Colors.with_opacity(0.30, theme.PRIMARY),
            border=ft.Border.all(2, theme.PRIMARY),
            scale=0.55,
            animate_scale=ft.Animation(1000, ft.AnimationCurve.EASE_IN_OUT),
            alignment=ft.Alignment.CENTER,
        )
        counter_text = ft.Text(
            "", size=44, weight=ft.FontWeight.BOLD, color=theme.PRIMARY
        )
        circle.content = counter_text
        phase_text = ft.Text(
            "Siap-siap...",
            size=19,
            weight=ft.FontWeight.BOLD,
            color=theme.ON_BACKGROUND,
        )
        cycle_text = ft.Text(
            "Satu putaran 4-7-8.", size=12, color=theme.MUTED
        )

        async def run_cycle() -> None:
            await asyncio.sleep(0.6)
            for label, seconds, target_scale in BREATHING_STEPS:
                if not running["active"]:
                    return
                phase_text.value = label
                circle.animate_scale = ft.Animation(
                    seconds * 1000, ft.AnimationCurve.EASE_IN_OUT
                )
                circle.scale = target_scale
                for remaining in range(seconds, 0, -1):
                    if not running["active"]:
                        return
                    counter_text.value = str(remaining)
                    page.update()
                    await asyncio.sleep(1)
            if not running["active"]:
                return
            phase_text.value = "Selesai 🤍"
            counter_text.value = ""
            cycle_text.value = "Satu sesi selesai."
            circle.animate_scale = ft.Animation(900, ft.AnimationCurve.EASE_OUT)
            circle.scale = 0.8
            page.update()
            await asyncio.sleep(0.8)
            if not running["active"]:
                return
            log_stage(STAGE_BREATHING_DONE)
            if next_stage == "light":
                show_light_menu()
                return
            show_outcome()

        def back(event) -> None:
            running["active"] = False
            show_light_menu()

        set_activity(
            "Latihan napas 4-7-8",
            ft.Column(
                [
                    phase_text,
                    ft.Container(
                        content=circle, height=200, alignment=ft.Alignment.CENTER
                    ),
                    cycle_text,
                ],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            back if next_stage == "light" else None,
        )
        page.run_task(run_cycle)

    def show_grounding(next_stage: str) -> None:
        position = {"index": 0}

        def finish_grounding() -> None:
            log_stage(STAGE_GROUNDING_DONE)
            if next_stage == "light":
                show_light_menu()
            else:
                show_breathing(next_stage="outcome")

        def render() -> None:
            index = position["index"]
            if index >= len(GROUNDING_STEPS):
                finish_grounding()
                return
            count, instruction, icon = GROUNDING_STEPS[index]
            inner = ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                height=4,
                                expand=True,
                                bgcolor=(
                                    theme.PRIMARY if number <= index else theme.BORDER
                                ),
                                border_radius=2,
                            )
                            for number in range(len(GROUNDING_STEPS))
                        ],
                        spacing=4,
                    ),
                    ft.Icon(icon, size=40, color=theme.SECONDARY),
                    ft.Text(
                        str(count),
                        size=52,
                        weight=ft.FontWeight.BOLD,
                        color=theme.PRIMARY,
                    ),
                    ft.Text(
                        instruction,
                        size=15,
                        color=theme.ON_BACKGROUND,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        "Nggak usah diketik, sebut aja dalam hati. Pelan-pelan.",
                        size=11.5,
                        color=theme.MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ui_helpers.wide_button(
                        "Udah",
                        lambda event: (
                            position.update(index=position["index"] + 1),
                            render(),
                        ),
                        icon=ft.Icons.CHECK,
                    ),
                ],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
            set_activity(
                "Balik ke sini dulu.",
                inner,
                (lambda event: show_light_menu())
                if next_stage == "light"
                else None,
            )

        render()

    show_grounding(next_stage="breathing")
    return body
