"""FocusBuddy -- entry point.

Jalankan:
    flet run --web app/main.py     (browser, paling gampang buat demo)
    flet run app/main.py           (jendela desktop)
    flet run --android app/main.py (HP, via app Flet)
"""
from __future__ import annotations

from pathlib import Path

import flet as ft

from app import storage, theme
from app.views import (
    diary,
    favorites,
    home,
    inbox,
    med_setup,
    mood,
    morning_brief,
    onboarding,
    reset,
    settings,
    tracker,
)

# Sejajar dengan main.py (app/assets/) -- ini konvensi yang dipakai `flet run`
# CLI: dia auto-set env var FLET_ASSETS_DIR ke <script_dir>/assets dan itu
# override parameter assets_dir di bawah kalau nggak sejajar begini.
ASSETS_DIR = str(Path(__file__).resolve().parent / "assets")

# Route yang muncul di navigation bar bawah.
NAV_ROUTES = [
    ("home", "Beranda", ft.Icons.HOME_ROUNDED),
    ("tracker", "Tracker", ft.Icons.CALENDAR_MONTH),
    ("mood", "Mood", ft.Icons.FAVORITE_ROUNDED),
]

# Semua route (termasuk yang cuma bisa dicapai dari dalam halaman lain).
ROUTES = {
    "home": home.build,
    "tracker": tracker.build,
    "mood": mood.build,
    "diary": diary.build,
    "reset": reset.build,
    "med_setup": med_setup.build,
    "onboarding": onboarding.build,
    "favorites": favorites.build,
    "settings": settings.build,
    "morning_brief": morning_brief.build,
    "inbox": inbox.build,
}

# Halaman yang nutupin seluruh layar -- nav bar disembunyiin biar user
# nggak bisa kabur di tengah onboarding / brief pagi.
FULLSCREEN_ROUTES = {"onboarding", "morning_brief"}

NAV_INDEX = {name: i for i, (name, _, _) in enumerate(NAV_ROUTES)}


def main(page: ft.Page) -> None:
    page.title = "FocusBuddy"
    page.theme = theme.build_theme()
    page.theme_mode = ft.ThemeMode.LIGHT
    page.fonts = theme.FONTS
    page.bgcolor = theme.BACKGROUND
    page.padding = 0
    page.window.width = 420
    page.window.height = 880

    content = ft.Container(expand=True, padding=20)

    def navigate(route: str) -> None:
        # Selama onboarding belum kelar, semua rute dibelokin ke sini.
        # Pengecekannya HARUS di router, bukan di dalam build() halaman:
        # kalau build() manggil navigate() sendiri, hasilnya bakal ketimpa
        # sama nilai balik build() yang lagi jalan -> layar kosong.
        if route != "onboarding" and not storage.get_profile().get("onboarded"):
            route = "onboarding"

        # Sekali sehari, Kalem nyapa duluan sebelum Home biasa tampil.
        # Cuma dicegat di jalur "home" -- tab lain tetap bisa dibuka
        # langsung, biar brief-nya kerasa sapaan, bukan tembok.
        elif route == "home" and storage.needs_morning_brief():
            route = "morning_brief"

        builder = ROUTES.get(route, home.build)
        content.content = builder(page, navigate)
        # Halaman di luar nav bar (reset/diary/med_setup) nggak mindahin
        # highlight tab -- biar user tetep tau dia lagi "dari mana".
        if route in NAV_INDEX:
            nav_bar.selected_index = NAV_INDEX[route]
        nav_bar.visible = route not in FULLSCREEN_ROUTES
        page.update()

    nav_bar = ft.NavigationBar(
        selected_index=0,
        bgcolor=theme.SURFACE,
        indicator_color=theme.PRIMARY,
        on_change=lambda e: navigate(NAV_ROUTES[e.control.selected_index][0]),
        destinations=[
            ft.NavigationBarDestination(icon=icon, label=label) for _, label, icon in NAV_ROUTES
        ],
    )

    page.add(ft.Column([content, nav_bar], expand=True, spacing=0))
    navigate("home")


if __name__ == "__main__":
    ft.run(main, assets_dir=ASSETS_DIR)
