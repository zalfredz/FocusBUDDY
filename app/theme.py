"""Token visual dan tema Flet FocusBuddy."""
from __future__ import annotations

import flet as ft

PRIMARY = "#95D899"
SECONDARY = "#AEEEF8"
BACKGROUND = "#141416"
ON_BACKGROUND = "#FFFFFF"
TERTIARY = "#F3B88B"

SURFACE = "#484863"
MUTED = "#B9B7C3"
BORDER = "#65657D"
SUCCESS = "#7FAE90"
WARN = "#E0A458"
DANGER = "#FF8A8A"

FONT_BODY = "Lexend"
FONT_DISPLAY = "Quicksand"
FONT_AUTH = "Plus Jakarta Sans"

FONTS = {
    "Lexend": "https://fonts.googleapis.com/css2?family=Lexend",
    "Quicksand": "https://fonts.googleapis.com/css2?family=Quicksand:wght@600",
    "Plus Jakarta Sans": (
        "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:"
        "wght@300;400;500;600;700;800"
    ),
}

CARD_RADIUS = 20
SPACING = 16


def build_theme() -> ft.Theme:
    return ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=PRIMARY,
            on_primary="#181A35",
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
        navigation_bar_theme=ft.NavigationBarTheme(
            bgcolor="#484863",
            indicator_color="#DDE0FF",
            label_text_style=ft.TextStyle(
                color="#DDE0FF",
                font_family=FONT_AUTH,
                size=11,
            ),
        ),
    )
