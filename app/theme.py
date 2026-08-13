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
        visual_density=ft.VisualDensity.COMFORTABLE,
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
        date_picker_theme=ft.DatePickerTheme(
            bgcolor="#24242F",
            header_bgcolor="#343446",
            header_foreground_color=ON_BACKGROUND,
            divider_color=BORDER,
            weekday_text_style=ft.TextStyle(
                color=MUTED,
                font_family=FONT_AUTH,
            ),
            day_foreground_color={
                ft.ControlState.DISABLED: "#6F6E7D",
                ft.ControlState.SELECTED: "#181A35",
                ft.ControlState.DEFAULT: ON_BACKGROUND,
            },
            year_foreground_color={
                ft.ControlState.DISABLED: "#6F6E7D",
                ft.ControlState.SELECTED: "#181A35",
                ft.ControlState.DEFAULT: ON_BACKGROUND,
            },
            cancel_button_style=ft.ButtonStyle(color=PRIMARY),
            confirm_button_style=ft.ButtonStyle(color=PRIMARY),
            shape=ft.RoundedRectangleBorder(radius=24),
        ),
        time_picker_theme=ft.TimePickerTheme(
            bgcolor="#24242F",
            dial_bgcolor="#343446",
            dial_hand_color=PRIMARY,
            dial_text_color=ON_BACKGROUND,
            hour_minute_color="#343446",
            hour_minute_text_color=ON_BACKGROUND,
            entry_mode_icon_color=PRIMARY,
            help_text_style=ft.TextStyle(
                color=ON_BACKGROUND,
                font_family=FONT_AUTH,
            ),
            cancel_button_style=ft.ButtonStyle(color=PRIMARY),
            confirm_button_style=ft.ButtonStyle(color=PRIMARY),
            shape=ft.RoundedRectangleBorder(radius=24),
        ),
        dialog_theme=ft.DialogTheme(
            bgcolor="#1C1C26",
            title_text_style=ft.TextStyle(
                color=ON_BACKGROUND,
                font_family=FONT_AUTH,
                size=18,
                weight=ft.FontWeight.W_700,
            ),
            content_text_style=ft.TextStyle(
                color=ON_BACKGROUND,
                font_family=FONT_AUTH,
                size=13,
            ),
            shape=ft.RoundedRectangleBorder(radius=22),
        ),
        navigation_bar_theme=ft.NavigationBarTheme(
            bgcolor="#1C1C26",
            indicator_color="#484863",
            label_behavior=ft.NavigationBarLabelBehavior.ONLY_SHOW_SELECTED,
            label_text_style={
                ft.ControlState.SELECTED: ft.TextStyle(
                    color="#DDE0FF",
                    font_family=FONT_AUTH,
                    size=12,
                    weight=ft.FontWeight.W_700,
                ),
                ft.ControlState.DEFAULT: ft.TextStyle(
                    color="#DDE0FF",
                    font_family=FONT_AUTH,
                    size=11,
                ),
            },
        ),
    )
