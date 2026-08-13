"""Alur pemulihan Kewalahan: grounding 5-4-3-2-1, napas, lalu check-in."""
from __future__ import annotations

import asyncio
from typing import Callable

import flet as ft

from app import buddy, storage, theme, ui_helpers
from app.core.reset_preferences import (
    CRISIS_HOTLINES,
    TELEHEALTH_PARTNERS,
    detect_distress,
)


BACKGROUND = "#232337"
PANEL = "#343446"
TEXT = "#FFFFFF"
SOFT_TEXT = "#DDE0FF"
PRIMARY = "#95D899"
SECONDARY = "#AEEEF8"
FONT = "Plus Jakarta Sans"
CONTENT_WIDTH = 340

BREATHING_STEPS = [
    ("Tarik napas...", 4, 1.0),
    ("Tahan...", 7, 1.0),
    ("Buang pelan-pelan...", 8, 0.55),
]

GROUNDING_STEPS = [
    {
        "verb": "lihat",
        "progress": "Property 1=q1 (2).png",
        "sense": "Eye.png",
    },
    {
        "verb": "sentuh",
        "progress": "Property 1=q2 (1).png",
        "sense": "front_hand.png",
    },
    {
        "verb": "dengar",
        "progress": "Property 1=q3 (1).png",
        "sense": "uil_ear.png",
    },
    {
        "verb": "cium",
        "progress": "Property 1=q4 (1).png",
        "sense": "Wind.png",
    },
    {
        "verb": "syukurin",
        "progress": "Property 1=q5 (1).png",
        "sense": "Heart.png",
    },
]

EVENT_CHOICE = "overwhelm"
STAGE_OPEN = "opened"
STAGE_GROUNDING_DONE = "grounding_54321_done"
STAGE_BREATHING_DONE = "breathing_478_done"
STAGE_CHECKIN_NOT_READY = "checkin_belum_bisa"
STAGE_CHECKIN_IMPROVED = "checkin_sedikit_lebih_baik"
STAGE_RETRY = "recovery_repeated"


def build(page: ft.Page, navigate) -> ft.Control:
    body = ft.Column(
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=0,
    )
    root = ft.Container(
        expand=True,
        bgcolor=BACKGROUND,
        alignment=ft.Alignment.CENTER,
        content=body,
    )
    mounted = {"active": True, "screen": 0}
    distress = detect_distress(storage.get_reset_events(), storage.get_mood_logs())

    recovery_event = storage.add_reset_event(EVENT_CHOICE)
    recovery_event_id = recovery_event["id"]
    storage.append_reset_stage(recovery_event_id, STAGE_OPEN)

    def cleanup() -> None:
        mounted["active"] = False
        mounted["screen"] += 1

    setattr(page, "_focusbuddy_view_cleanup", cleanup)

    def log_stage(stage: str) -> None:
        storage.append_reset_stage(recovery_event_id, stage)

    def show_screen(control: ft.Control, *, gradient: ft.Gradient | None = None) -> None:
        mounted["screen"] += 1
        root.bgcolor = None if gradient is not None else BACKGROUND
        root.gradient = gradient
        body.controls = [control]
        page.update()

    def action_button(
        label: str,
        on_click: Callable,
        *,
        outlined: bool = False,
        width: int = CONTENT_WIDTH,
    ) -> ft.Control:
        if outlined:
            return ft.OutlinedButton(
                width=width,
                height=48,
                content=ft.Text(
                    label,
                    color=SOFT_TEXT,
                    size=14,
                    weight=ft.FontWeight.W_700,
                    font_family=FONT,
                ),
                style=ft.ButtonStyle(
                    side=ft.BorderSide(1, SOFT_TEXT),
                    shape=ft.RoundedRectangleBorder(radius=20),
                ),
                on_click=on_click,
            )
        return ft.Button(
            width=width,
            height=48,
            content=ft.Text(
                label,
                color="#181A35",
                size=14,
                weight=ft.FontWeight.W_800,
                font_family=FONT,
            ),
            style=ft.ButtonStyle(
                bgcolor=SOFT_TEXT,
                shape=ft.RoundedRectangleBorder(radius=20),
            ),
            on_click=on_click,
        )

    def recovery_action_card(
        label: str,
        duration: str,
        icon: str,
        on_click: Callable,
        *,
        bgcolor: str,
    ) -> ft.Control:
        return ft.Container(
            width=CONTENT_WIDTH,
            height=64,
            bgcolor=bgcolor,
            border_radius=16,
            padding=ft.Padding.symmetric(vertical=9, horizontal=12),
            content=ft.Row(
                [
                    ft.Icon(icon, size=28, color="#181A35"),
                    ft.Column(
                        [
                            ft.Text(
                                label,
                                size=16,
                                weight=ft.FontWeight.W_800,
                                color="#181A35",
                                font_family=FONT,
                            ),
                            ft.Text(
                                duration,
                                size=10.5,
                                color="#3F4056",
                                font_family=FONT,
                            ),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=22, color="#181A35"),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=on_click,
            ink=True,
        )

    def hotline_rows() -> list[ft.Control]:
        rows: list[ft.Control] = []
        for hotline in CRISIS_HOTLINES:
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.CALL, color="#181A35", size=21),
                            ft.Column(
                                [
                                    ft.Text(
                                        hotline["number"],
                                        size=17,
                                        weight=ft.FontWeight.BOLD,
                                        color="#181A35",
                                    ),
                                    ft.Text(
                                        hotline["name"],
                                        size=10.5,
                                        color="#181A35",
                                    ),
                                ],
                                spacing=1,
                                expand=True,
                            ),
                            ft.Icon(ft.Icons.ARROW_OUTWARD, color="#181A35", size=16),
                        ],
                        spacing=10,
                    ),
                    padding=ft.Padding.symmetric(vertical=11, horizontal=13),
                    bgcolor=SOFT_TEXT,
                    border_radius=16,
                    url=hotline["tel"],
                    ink=True,
                )
            )
        return rows

    def professional_card(prominent: bool) -> ft.Control:
        partner_rows = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.CALL_OUTLINED, color=SOFT_TEXT, size=28),
                        ft.Column(
                            [
                                ft.Text(
                                    partner["name"],
                                    weight=ft.FontWeight.BOLD,
                                    size=13,
                                    color=TEXT,
                                ),
                                ft.Text(partner["desc"], size=10.5, color=SOFT_TEXT),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.ARROW_OUTWARD, color=SOFT_TEXT, size=18),
                    ],
                    spacing=10,
                ),
                padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                bgcolor=PANEL,
                border_radius=14,
                url=partner["url"],
                ink=True,
            )
            for partner in TELEHEALTH_PARTNERS
        ]
        heading: list[ft.Control] = [
            ft.Text(
                "Butuh Ngobrol Sama Profesional?",
                size=16,
                weight=ft.FontWeight.W_800,
                color=TEXT,
                font_family=FONT,
            ),
            ft.Text(
                distress.reason
                if prominent
                else "Kalau rasanya kebanyakan buat dihadapin sendiri, ini beberapa "
                "layanan yang bisa dihubungi.",
                size=12,
                color=SOFT_TEXT,
            ),
        ]
        return ft.Container(
            width=CONTENT_WIDTH,
            bgcolor="#181820",
            border=ft.Border.all(1, "#484863"),
            border_radius=20,
            padding=16,
            content=ft.Column(
                [*heading, *partner_rows, *hotline_rows()],
                spacing=9,
                tight=True,
            ),
        )

    def show_light_menu() -> None:
        show_screen(
            ft.Container(
                expand=True,
                padding=ft.Padding(left=22, top=30, right=22, bottom=28),
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.IconButton(
                                    icon=ft.Icons.ARROW_BACK,
                                    icon_color=SOFT_TEXT,
                                    on_click=lambda event: navigate("home"),
                                ),
                                ft.Text(
                                    "Pelan-pelan aja yaaa",
                                    size=26,
                                    weight=ft.FontWeight.W_900,
                                    color=TEXT,
                                    font_family=FONT,
                                ),
                            ],
                            spacing=4,
                        ),
                        buddy.face("tenang", 105),
                        ft.Text(
                            "Jangan ragu untuk take your time, KALEM akan bantu sebisanya",
                            width=CONTENT_WIDTH,
                            size=12.5,
                            color=SOFT_TEXT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        recovery_action_card(
                            "Sebut Sekitar",
                            "5 Menit",
                            ft.Icons.VISIBILITY_OUTLINED,
                            lambda event: show_grounding(next_stage="light"),
                            bgcolor="#A8EDC3",
                        ),
                        recovery_action_card(
                            "Latihan nafas",
                            "3 Menit",
                            ft.Icons.AIR,
                            lambda event: show_breathing(next_stage="light"),
                            bgcolor=SOFT_TEXT,
                        ),
                        professional_card(prominent=False),
                        ui_helpers.disclaimer(
                            "FocusBuddy bukan layanan krisis. Kalau kamu dalam bahaya langsung, "
                            "hubungi layanan darurat atau nomor di atas."
                        ),
                    ],
                    spacing=14,
                    scroll=ft.ScrollMode.AUTO,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        )

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

        show_screen(
            ft.Container(
                expand=True,
                padding=ft.Padding(left=24, top=36, right=24, bottom=32),
                content=ft.Column(
                    [
                        buddy.face("tenang", 128),
                        ft.Text(
                            "Sekarang rasanya gimana?",
                            width=CONTENT_WIDTH,
                            size=30,
                            weight=ft.FontWeight.W_900,
                            color=TEXT,
                            font_family=FONT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            "Nggak harus langsung pulih kok",
                            width=CONTENT_WIDTH,
                            size=12.5,
                            color=SOFT_TEXT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        action_button("Sedikit lebih baik", lambda event: answer(True)),
                        action_button(
                            "Belum bisa",
                            lambda event: answer(False),
                            outlined=True,
                        ),
                    ],
                    spacing=18,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        )

    def show_breathing(next_stage: str) -> None:
        running = {"active": True}
        circle = ft.Container(
            width=190,
            height=190,
            border_radius=95,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[PRIMARY, SECONDARY],
            ),
            shadow=ft.BoxShadow(
                blur_radius=32,
                spread_radius=3,
                color="#5595D899",
            ),
            scale=0.55,
            animate_scale=ft.Animation(1000, ft.AnimationCurve.EASE_IN_OUT),
            alignment=ft.Alignment.CENTER,
        )
        counter_text = ft.Text(
            "",
            size=44,
            weight=ft.FontWeight.W_900,
            color="#181A35",
            font_family=FONT,
        )
        circle.content = counter_text
        phase_text = ft.Text(
            "Siap-siap...",
            size=28,
            weight=ft.FontWeight.W_900,
            color=TEXT,
            font_family=FONT,
            text_align=ft.TextAlign.CENTER,
        )
        cycle_text = ft.Text(
            "Ikutin Lingkarannya Yaaa",
            width=CONTENT_WIDTH,
            size=12,
            color=SOFT_TEXT,
            text_align=ft.TextAlign.CENTER,
        )

        async def run_cycle() -> None:
            await asyncio.sleep(0.6)
            for label, seconds, target_scale in BREATHING_STEPS:
                if not mounted["active"] or not running["active"]:
                    return
                phase_text.value = label
                circle.animate_scale = ft.Animation(
                    seconds * 1000, ft.AnimationCurve.EASE_IN_OUT
                )
                circle.scale = target_scale
                for remaining in range(seconds, 0, -1):
                    if not mounted["active"] or not running["active"]:
                        return
                    counter_text.value = str(remaining)
                    page.update()
                    await asyncio.sleep(1)
            if not mounted["active"] or not running["active"]:
                return
            phase_text.value = "Selesai 🤍"
            counter_text.value = ""
            circle.animate_scale = ft.Animation(900, ft.AnimationCurve.EASE_OUT)
            circle.scale = 0.8
            page.update()
            await asyncio.sleep(0.8)
            if not mounted["active"] or not running["active"]:
                return
            log_stage(STAGE_BREATHING_DONE)
            if next_stage == "light":
                show_light_menu()
            else:
                show_outcome()

        def back(event) -> None:
            running["active"] = False
            show_light_menu()

        controls: list[ft.Control] = [
            phase_text,
            ft.Container(content=circle, height=220, alignment=ft.Alignment.CENTER),
            cycle_text,
        ]
        if next_stage == "light":
            controls.append(action_button("Kembali", back, outlined=True))
        show_screen(
            ft.Container(
                expand=True,
                padding=ft.Padding(left=24, top=36, right=24, bottom=32),
                content=ft.Column(
                    controls,
                    spacing=18,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
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
            step = GROUNDING_STEPS[index]
            question = ft.Text(
                spans=[
                    ft.TextSpan("Apa hal yang\n"),
                    ft.TextSpan(
                        f"kamu {step['verb']}",
                        style=ft.TextStyle(weight=ft.FontWeight.W_900),
                    ),
                    ft.TextSpan("\ndi depanmu\nsekarang?"),
                ],
                width=CONTENT_WIDTH,
                size=32,
                color=TEXT,
                font_family=FONT,
                style=ft.TextStyle(height=1.18),
            )
            show_screen(
                ft.Container(
                    expand=True,
                    padding=ft.Padding(left=24, top=34, right=24, bottom=28),
                    content=ft.Column(
                        [
                            ft.Image(
                                src=step["progress"],
                                width=CONTENT_WIDTH,
                                height=65,
                                fit=ft.BoxFit.CONTAIN,
                            ),
                            question,
                            ft.Image(
                                src=step["sense"],
                                width=180,
                                height=180,
                                fit=ft.BoxFit.CONTAIN,
                            ),
                            ft.Text(
                                "Sebutkan hal-hal itu dalam hati, pelan-pelan aja.",
                                width=CONTENT_WIDTH,
                                size=15,
                                color=SOFT_TEXT,
                                weight=ft.FontWeight.W_700,
                                font_family=FONT,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            action_button(
                                "Udah",
                                lambda event: (
                                    position.update(index=position["index"] + 1),
                                    render(),
                                ),
                            ),
                        ],
                        spacing=18,
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                )
            )

        render()

    show_grounding(next_stage="breathing")
    return root
