"""Check-in harian dua langkah: mood lalu tenaga."""
from __future__ import annotations

import flet as ft

from app import buddy, storage

BACKGROUND = "#141416"
OPTION_BG = "#1C1C26"
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


def _energy_illustration_asset(level: int) -> str:
    if level <= 2:
        return "Property 1=bad_mood.png"
    if level <= 4:
        return "Property 1=med_mood.png"
    return "Property 1=good_mood.png"


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
    energy_controls: dict[str, ft.Control] = {}

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

    def mood_illustration() -> ft.Control:
        return ft.Image(
            src=buddy.asset_for(str(state["mood"])),
            width=220,
            height=235,
            fit=ft.BoxFit.CONTAIN,
        )

    def energy_illustration(level: int) -> ft.Control:
        return ft.Image(
            src=_energy_illustration_asset(level),
            width=215,
            height=235,
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
            width=50,
            height=66,
            padding=ft.Padding.symmetric(vertical=6, horizontal=2),
            bgcolor=OPTION_ACTIVE if active else OPTION_BG,
            border=ft.Border.all(2, ACCENT if active else OPTION_BG),
            border_radius=9,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Image(
                        src=buddy.asset_for(mood),
                        width=32,
                        height=32,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                    ft.Text(
                        buddy.MOOD_LABELS[mood],
                        size=8.5,
                        color=TEXT_PRIMARY,
                        font_family=FONT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                spacing=2,
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
        level = max(1, min(6, int(round(float(e.control.value or 1)))))
        state["energy"] = level
        e.control.value = level
        e.control.active_color = _energy_color(level)
        e.control.thumb_color = _energy_color(level)
        label = energy_controls.get("label")
        image = energy_controls.get("image")
        if isinstance(label, ft.Text):
            label.value = ENERGY_LABELS[level]
        if isinstance(image, ft.Image):
            image.src = _energy_illustration_asset(level)
        page.update()

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
                mood_illustration(),
                ft.Container(
                    width=CONTENT_WIDTH,
                    padding=ft.Padding.symmetric(vertical=10, horizontal=8),
                    bgcolor="#59484863",
                    border_radius=14,
                    content=ft.Row(
                        [mood_card(mood) for mood in buddy.MOOD_ORDER],
                        spacing=6,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ),
                continue_button(go_to_energy),
            ]
        else:
            energy = int(state["energy"])
            energy_label = ft.Text(
                ENERGY_LABELS[energy],
                size=14,
                color=TEXT_PRIMARY,
                font_family=FONT,
                weight=ft.FontWeight.W_700,
                text_align=ft.TextAlign.CENTER,
            )
            energy_image = energy_illustration(energy)
            energy_slider = ft.Slider(
                min=1,
                max=6,
                divisions=5,
                value=energy,
                label="{value}",
                round=0,
                active_color=_energy_color(energy),
                inactive_color="#65657D",
                thumb_color=_energy_color(energy),
                on_change=pick_energy,
            )
            energy_controls.update(
                label=energy_label,
                image=energy_image,
                slider=energy_slider,
            )
            controls = [
                heading("Tenaga kamu\nsekarang", "gimana?"),
                energy_image,
                ft.Container(
                    width=CONTENT_WIDTH,
                    padding=ft.Padding(left=14, top=16, right=14, bottom=12),
                    bgcolor="#59484863",
                    border_radius=14,
                    content=ft.Column(
                        [
                            energy_label,
                            energy_slider,
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
