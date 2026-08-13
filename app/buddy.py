"""Renderer karakter KALEM dan balon percakapan."""
from __future__ import annotations

import flet as ft

from app import theme

MOOD_ASSETS = {
    "semangat": "kalem_semangat.svg",
    "tenang": "kalem_tenang.svg",
    "cemas": "kalem_cemas.svg",
    "sedih": "kalem_sedih.svg",
    "lelah": "kalem_lelah.svg",
}

MOOD_SCORE = {"cemas": 1, "sedih": 2, "lelah": 3, "tenang": 4, "semangat": 5}

MOOD_LABELS = {
    "semangat": "Semangat",
    "tenang": "Tenang",
    "cemas": "Cemas",
    "sedih": "Sedih",
    "lelah": "Lelah",
}

MOOD_ORDER = ["cemas", "sedih", "lelah", "tenang", "semangat"]

DEFAULT_MOOD = "tenang"

TIRED_COMPANION_MESSAGE = (
    "Kamu kelihatan capek. Istirahat juga termasuk progress loh..."
)
ENERGETIC_COMPANION_MESSAGE = "Semangat untuk Hari Ini!"

GREETINGS = {
    "semangat": "Energi kamu lagi bagus. Yuk pakai buat satu hal yang penting.",
    "tenang": "Hari ini nggak harus produktif banget. Pelan-pelan aja.",
    "cemas": "Kalau kerasa berat, kita mulai dari yang paling kecil dulu ya.",
    "sedih": "Nggak apa-apa lagi nggak enak. Aku nemenin.",
    "lelah": "Kamu keliatan capek. Istirahat juga termasuk progress.",
}


def asset_for(mood: str) -> str:
    return MOOD_ASSETS.get(mood, MOOD_ASSETS[DEFAULT_MOOD])


def score_for(mood: str) -> int:
    return MOOD_SCORE.get(mood, MOOD_SCORE[DEFAULT_MOOD])


def greeting_for(mood: str) -> str:
    return GREETINGS.get(mood, GREETINGS[DEFAULT_MOOD])


def companion_for_energy(level: int) -> tuple[str, str]:
    """Satu sumber visual dan pesan maskot untuk Home, Tracker, dan Mood."""
    if int(level) <= 3:
        return "lelah", TIRED_COMPANION_MESSAGE
    return "semangat", ENERGETIC_COMPANION_MESSAGE


def face(mood: str = DEFAULT_MOOD, size: int = 90) -> ft.Image:
    return ft.Image(
        src=asset_for(mood),
        width=size,
        height=size,
        fit=ft.BoxFit.CONTAIN,
        error_content=ft.Icon(ft.Icons.FACE_RETOUCHING_NATURAL, size=size * 0.7, color=theme.PRIMARY),
    )


def speech_bubble(text: str) -> ft.Container:
    return ft.Container(
        content=ft.Text(text, size=13, color=theme.ON_BACKGROUND),
        bgcolor=theme.SURFACE,
        border=ft.Border.all(1, theme.BORDER),
        border_radius=16,
        padding=ft.Padding.symmetric(vertical=10, horizontal=14),
    )


def mood_picker(selected: str, on_pick) -> ft.Row:
    chips = []
    for mood in MOOD_ORDER:
        active = mood == selected
        chips.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Image(src=asset_for(mood), width=36, height=36, fit=ft.BoxFit.CONTAIN),
                        ft.Text(
                            MOOD_LABELS[mood],
                            size=10,
                            color="#FFFFFF" if active else theme.MUTED,
                        ),
                    ],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                width=62,
                padding=ft.Padding.symmetric(vertical=8, horizontal=4),
                bgcolor=theme.PRIMARY if active else theme.SURFACE,
                border=ft.Border.all(1, theme.PRIMARY if active else theme.BORDER),
                border_radius=14,
                on_click=lambda e, m=mood: on_pick(m),
                ink=True,
            )
        )
    return ft.Row(chips, spacing=8, scroll=ft.ScrollMode.AUTO)
