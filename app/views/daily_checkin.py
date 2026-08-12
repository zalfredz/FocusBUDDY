"""Check-in harian dua langkah: mood lalu tenaga."""
from __future__ import annotations

import flet as ft

from app import buddy, storage

BACKGROUND = "#343446"
OPTION_BG = "#484863"
OPTION_ACTIVE = "#5B5B7A"
TEXT_PRIMARY = "#FFFFFF"
TEXT_MUTED = "#D7D6E3"
BUTTON_BG = "#DDE0FF"
BUTTON_TEXT = "#343446"
ACCENT = "#AEEEF8"
FONT = "Plus Jakarta Sans"
SCREEN_WIDTH = None
CONTENT_WIDTH = 300

ENERGY_LABELS = {
    1: "Sangat Lelah",
    2: "Lelah",
    3: "Agak Lelah",
    4: "Cukup Bertenaga",
    5: "Bertenaga",
    6: "Sangat Bertenaga",
}


def _energy_from_score(score: int) -> int:
    return {1: 1, 2: 2, 3: 3, 4: 5, 5: 6}.get(score, 3)


def _energy_slider_asset(level: int) -> str:
    if level <= 2:
        return "Property 1=bad_mood (1).png"
    if level <= 4:
        return "Property 1=med_mood (1).png"
    return "Property 1=good_mood (5).png"


def _energy_color(level: int) -> str:
    if level <= 2:
        return "#FF8A8A"
    if level <= 4:
        return "#E0A458"
    return "#AEEEF8"


def build(page: ft.Page, navigate) -> ft.Control:
    state = {
        "step": 0,
        "mood": buddy.DEFAULT_MOOD,
        "energy": _energy_from_score(buddy.score_for(buddy.DEFAULT_MOOD)),
    }
    body = ft.Column(
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    def heading(prefix: str, emphasis: str) -> ft.Control:
        return ft.Text(
            spans=[
                ft.TextSpan(
                    f"{prefix}\n",
                    style=ft.TextStyle(
                        color=TEXT_PRIMARY,
                        font_family=FONT,
                        size=27,
                        height=1.05,
                        weight=ft.FontWeight.W_400,
                    ),
                ),
                ft.TextSpan(
                    emphasis,
                    style=ft.TextStyle(
                        color=TEXT_PRIMARY,
                        font_family=FONT,
                        size=27,
                        height=1.05,
                        weight=ft.FontWeight.W_700,
                    ),
                ),
            ],
            width=CONTENT_WIDTH,
            font_family=FONT,
        )

    def illustration() -> ft.Control:
        return ft.Image(
            src="Property 1=bad_mood.png",
            width=245,
            height=270,
            fit=ft.BoxFit.CONTAIN,
        )

    def continue_button(on_click) -> ft.Control:
        return ft.Button(
            width=CONTENT_WIDTH,
            height=48,
            content=ft.Text(
                "Lanjut",
                size=15,
                color=BUTTON_TEXT,
                font_family=FONT,
                weight=ft.FontWeight.W_700,
            ),
            style=ft.ButtonStyle(
                bgcolor=BUTTON_BG,
                color=BUTTON_TEXT,
                padding=0,
                shape=ft.RoundedRectangleBorder(radius=100),
            ),
            on_click=on_click,
        )

    def mood_card(mood: str) -> ft.Control:
        active = state["mood"] == mood
        return ft.Container(
            width=62,
            height=74,
            padding=ft.Padding.symmetric(vertical=7, horizontal=4),
            bgcolor=OPTION_ACTIVE if active else OPTION_BG,
            border=ft.Border.all(2, ACCENT if active else OPTION_BG),
            border_radius=9,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Image(
                        src=buddy.asset_for(mood),
                        width=38,
                        height=38,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                    ft.Text(
                        buddy.MOOD_LABELS[mood],
                        size=9.5,
                        color=TEXT_PRIMARY,
                        font_family=FONT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                spacing=3,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=lambda e, value=mood: pick_mood(value),
            ink=True,
        )

    def pick_mood(mood: str) -> None:
        state["mood"] = mood
        state["energy"] = _energy_from_score(buddy.score_for(mood))
        render()

    def go_to_energy(e) -> None:
        state["step"] = 1
        render()

    def pick_energy(e) -> None:
        state["energy"] = int(e.control.data)
        render()

    def energy_button(level: int) -> ft.Control:
        active = state["energy"] == level
        category_color = _energy_color(level)
        return ft.Container(
            content=ft.Text(
                str(level),
                size=14,
                color=BUTTON_TEXT if active else TEXT_PRIMARY,
                font_family=FONT,
                weight=ft.FontWeight.W_700,
                text_align=ft.TextAlign.CENTER,
            ),
            data=level,
            height=44,
            expand=True,
            alignment=ft.Alignment.CENTER,
            bgcolor=category_color if active else OPTION_BG,
            border=ft.Border.all(2, category_color if active else "#5B5B7A"),
            border_radius=10,
            on_click=pick_energy,
            ink=True,
        )

    def finish(e) -> None:
        mood = str(state["mood"])
        energy = int(state["energy"])
        storage.add_mood_log(
            mood=mood,
            score=buddy.score_for(mood),
            energy=energy,
            diary="",
            quick_tags=[],
        )
        storage.set_today_energy(energy)
        navigate("home")

    def render() -> None:
        if state["step"] == 0:
            controls: list[ft.Control] = [
                heading("Mood kamu\nsekarang", "gimana?"),
                illustration(),
                ft.Container(
                    width=CONTENT_WIDTH,
                    padding=ft.Padding.symmetric(vertical=12, horizontal=10),
                    bgcolor="#59484863",
                    border_radius=14,
                    content=ft.Row(
                        [mood_card(mood) for mood in buddy.MOOD_ORDER],
                        spacing=8,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                ),
                continue_button(go_to_energy),
            ]
        else:
            energy = int(state["energy"])
            controls = [
                heading("Tenaga kamu\nsekarang", "gimana?"),
                illustration(),
                ft.Container(
                    width=CONTENT_WIDTH,
                    padding=ft.Padding(left=14, top=16, right=14, bottom=12),
                    bgcolor="#59484863",
                    border_radius=14,
                    content=ft.Column(
                        [
                            ft.Text(
                                ENERGY_LABELS[energy],
                                size=14,
                                color=TEXT_PRIMARY,
                                font_family=FONT,
                                weight=ft.FontWeight.W_700,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Image(
                                src=_energy_slider_asset(energy),
                                width=CONTENT_WIDTH - 28,
                                height=64,
                                fit=ft.BoxFit.FILL,
                            ),
                            ft.Row(
                                [energy_button(level) for level in range(1, 7)],
                                spacing=6,
                            ),
                        ],
                        spacing=10,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
                continue_button(finish),
            ]

        body.controls = [
            ft.Container(
                width=SCREEN_WIDTH,
                bgcolor=BACKGROUND,
                padding=ft.Padding(left=24, top=36, right=24, bottom=36),
                content=ft.Column(
                    controls,
                    spacing=18,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        ]
        page.update()

    render()
    return ft.Container(
        expand=True,
        bgcolor=BACKGROUND,
        alignment=ft.Alignment.TOP_CENTER,
        content=body,
    )
