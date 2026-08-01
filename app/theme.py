"""Palet warna & tipografi FocusBuddy.

Catatan: di Flet 0.86 (Material 3), field `background`/`on_background` pada
ColorScheme sudah dihapus dan diganti `surface`/`on_surface`. Warna dari
spesifikasi tetap dipakai persis, cuma dipetakan ke nama field yang baru.
"""
from __future__ import annotations

import flet as ft

# --- Palet inti (sesuai spesifikasi) ---
PRIMARY = "#8FBCA0"      # hijau sage -- warna utama Kalem
SECONDARY = "#A9C6DE"    # biru langit lembut
BACKGROUND = "#FAF6EF"   # krem hangat
ON_BACKGROUND = "#4A473F"  # coklat gelap untuk teks
TERTIARY = "#F3B88B"      # peach -- aksen hangat

# --- Turunan untuk kebutuhan UI ---
SURFACE = "#FFFFFF"
MUTED = "#8C877C"        # teks sekunder
BORDER = "#EDE6DA"
SUCCESS = "#7FAE90"
WARN = "#E0A458"
DANGER = "#D97B66"       # dipakai hemat: hanya alert nyata (obat habis, SOS)

FONT_BODY = "Lexend"
FONT_DISPLAY = "Quicksand"

FONTS = {
    "Lexend": "https://fonts.googleapis.com/css2?family=Lexend",
    "Quicksand": "https://fonts.googleapis.com/css2?family=Quicksand:wght@600",
}

CARD_RADIUS = 20
SPACING = 16


def build_theme() -> ft.Theme:
    # Nggak perlu nyetel `text_theme`: Flet udah nurunin warna teks dari
    # `on_surface` di ColorScheme bawah ini.
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
