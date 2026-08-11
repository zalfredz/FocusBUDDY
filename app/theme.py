"""Token visual dan tema Flet FocusBuddy."""
from __future__ import annotations

import flet as ft

PRIMARY = "#8FBCA0"
SECONDARY = "#A9C6DE"
BACKGROUND = "#FAF6EF"
ON_BACKGROUND = "#4A473F"
TERTIARY = "#F3B88B"

SURFACE = "#FFFFFF"
MUTED = "#8C877C"
BORDER = "#EDE6DA"
SUCCESS = "#7FAE90"
WARN = "#E0A458"
DANGER = "#D97B66"

FONT_BODY = "Lexend"
FONT_DISPLAY = "Quicksand"

FONTS = {
    "Lexend": "https://fonts.googleapis.com/css2?family=Lexend",
    "Quicksand": "https://fonts.googleapis.com/css2?family=Quicksand:wght@600",
}

CARD_RADIUS = 20
SPACING = 16


def build_theme() -> ft.Theme:
    return ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=PRIMARY,
            on_primary="#FFFFFF",
            secondary=SECONDARY,
            on_secondary=ON_BACKGROUND,
            tertiary=TERTIARY,
            on_tertiary=ON_BACKGROUND,
            surface=BACKGROUND,
            on_surface=ON_BACKGROUND,
            on_surface_variant=MUTED,
            outline=BORDER,
            error=DANGER,
        ),
        font_family=FONT_BODY,
    )
