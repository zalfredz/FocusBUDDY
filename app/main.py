"""FocusBuddy -- entry point.

Jalankan:
    flet run --web --port 8550 app/main.py  (browser lokal)
    flet run app/main.py           (jendela desktop)
"""
from __future__ import annotations

import json
from pathlib import Path

import flet as ft

from app import focus_session, storage, theme, ui_helpers
from app.cloud import CloudUnavailable, FocusBuddyCloud, oauth_code_from_url
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

# Rute yang tetap boleh dibuka walau sesi fokus lagi jalan. Halaman jeda
# WAJIB ada di sini -- ngunci jalan keluar orang yang lagi kewalahan itu
# kebalikan dari tujuan app ini.
FOKUS_BOLEH = {"home", "reset"}

NAV_INDEX = {name: i for i, (name, _, _) in enumerate(NAV_ROUTES)}


async def main(page: ft.Page) -> None:
    page.title = "FocusBuddy"
    page.theme = theme.build_theme()
    page.theme_mode = ft.ThemeMode.LIGHT
    page.fonts = theme.FONTS
    page.bgcolor = theme.BACKGROUND
    page.padding = 0
    page.window.width = 420
    page.window.height = 880

    try:
        cloud = FocusBuddyCloud()
    except CloudUnavailable:
        page.add(
            ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                padding=28,
                content=ft.Text(
                    "Database demo belum dikonfigurasi. Isi SUPABASE_URL dan "
                    "SUPABASE_PUBLISHABLE_KEY di environment hosting.",
                    text_align=ft.TextAlign.CENTER,
                    color=theme.MUTED,
                ),
            )
        )
        return
    preferences = ft.SharedPreferences()
    launcher = ft.UrlLauncher()
    token_key = "focusbuddy.supabase.session.v1"
    pkce_key = "focusbuddy.supabase.pkce.v1"
    app_started = False

    async def save_session() -> None:
        session = cloud.session()
        if not session:
            return
        await preferences.set(
            token_key,
            json.dumps(
                {
                    "access_token": session.access_token,
                    "refresh_token": session.refresh_token,
                }
            ),
        )

    async def logout(e=None) -> None:
        nonlocal app_started
        storage.set_cloud_save_hook(None)
        focus_session.stop()
        try:
            cloud.sign_out()
        finally:
            await preferences.remove(token_key)
            await preferences.remove(pkce_key)
            storage.clear_user_storage()
        app_started = False
        show_login()

    async def start_app() -> None:
        """Pilih cache per-user, tarik cloud, lalu baru bangun seluruh UI."""
        nonlocal app_started
        user = cloud.user()
        if user is None:
            show_login("Sesi Google belum tersedia. Coba masuk lagi.")
            return

        storage.set_cloud_save_hook(None)
        storage.configure_user_storage(user.id)
        had_user_cache = storage.current_data_file().exists()
        cloud_status = "Tersinkron ke database"
        try:
            remote = cloud.download_state(user.id)
            if remote is not None:
                storage.save_state(remote)
            elif had_user_cache:
                cloud.upload_state(user.id, storage.load_state())
            else:
                cloud.upload_state(user.id, storage.load_state())
        except Exception:
            # Sesi tetap bisa dibuka dari cache server sementara. Save
            # berikutnya akan dicoba lagi oleh worker cloud.
            cloud_status = "Sinkronisasi tertunda — koneksi akan dicoba lagi"
            storage.load_state()

        storage.set_cloud_save_hook(
            lambda state: cloud.enqueue_state(user.id, state)
        )
        setattr(page, "_focusbuddy_cloud_user", user)
        setattr(page, "_focusbuddy_cloud_status", cloud_status)
        setattr(page, "_focusbuddy_logout", logout)
        await save_session()
        app_started = True
        build_application()

    async def complete_oauth(raw_route: str = "") -> bool:
        code, error = oauth_code_from_url(raw_route, page.route, page.url)
        if error:
            show_login(f"Login Google gagal: {error}")
            return True
        if not code:
            return False
        show_login("Menyambungkan akun Google…", busy=True)
        try:
            verifier = await preferences.get(pkce_key)
            if isinstance(verifier, str):
                cloud.restore_pkce_verifier(verifier)
            cloud.exchange_code(code)
            await preferences.remove(pkce_key)
            await start_app()
            if page.route != "/":
                page.go("/")
        except Exception:
            show_login("Login belum berhasil. Silakan coba lagi.")
        return True

    async def login_google(e) -> None:
        show_login("Membuka halaman Google…", busy=True)
        try:
            url = cloud.begin_google_login()
            verifier = cloud.pkce_verifier()
            if not verifier:
                raise RuntimeError("PKCE verifier tidak terbentuk")
            await preferences.set(pkce_key, verifier)
            await launcher.launch_url(url, web_only_window_name="_self")
        except Exception:
            show_login("Nggak bisa membuka login Google. Coba beberapa saat lagi.")

    def show_login(message: str = "", busy: bool = False) -> None:
        page.clean()
        page.add(
            ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                padding=28,
                content=ft.Column(
                    [
                        ft.Image(src="kalem_tenang.svg", width=112, height=112),
                        ft.Text(
                            "FocusBuddy",
                            size=28,
                            weight=ft.FontWeight.BOLD,
                            color=theme.ON_BACKGROUND,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            "Masuk supaya tugas, mood, diary, dan progres kamu "
                            "punya ruang cloud yang terpisah dari pengguna lain.",
                            size=13,
                            color=theme.MUTED,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Button(
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.LOGIN, size=18),
                                    ft.Text("Lanjut dengan Google"),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                tight=True,
                            ),
                            on_click=login_google,
                            disabled=busy,
                        ),
                        ft.ProgressRing(width=22, height=22, visible=busy),
                        ft.Text(
                            message,
                            size=11.5,
                            color=theme.DANGER if "gagal" in message.lower() else theme.MUTED,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            "Dengan lanjut, akun Google dipakai hanya untuk identitas login. "
                            "Data aplikasi disimpan di Supabase dengan akses per akun.",
                            size=10.5,
                            color=theme.MUTED,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=16,
                    tight=True,
                ),
            )
        )

    async def on_route_change(e: ft.RouteChangeEvent) -> None:
        if not app_started:
            await complete_oauth(e.route)

    page.on_route_change = on_route_change

    def build_application() -> None:
        page.clean()
        content = ft.Container(expand=True, padding=20)

        # Dicatat sekali per pembukaan app sesudah identitas storage terpasang.
        storage.touch_last_open()

        def _tolak_keluar_fokus(tujuan: str) -> bool:
            """True kalau navigasi ditahan karena sesi fokus lagi jalan."""
            if not focus_session.is_running() or tujuan in FOKUS_BOLEH:
                return False

            s = focus_session.snapshot()
            apa = s["label"] or s["task_title"] or "satu hal"

            def lanjut(e):
                page.pop_dialog()

            def tetap_pindah(e):
                page.pop_dialog()
                focus_session.pause()
                navigate(tujuan)

            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Lagi fokus, nih 🌿", size=16),
                    content=ft.Column(
                        [
                            ft.Text(
                                f"Kamu lagi ngerjain \"{apa}\" — sisa {s['clock']}.",
                                size=13,
                            ),
                            ft.Text(
                                "Yuk selesaiin itu dulu. Kalau emang perlu pindah, "
                                "sesinya aku jeda dulu ya biar nggak keitung putus.",
                                size=11.5,
                                color=theme.MUTED,
                            ),
                        ],
                        spacing=8,
                        tight=True,
                    ),
                    actions=[
                        ft.TextButton(
                            content=ft.Text("Pindah aja", color=theme.MUTED),
                            on_click=tetap_pindah,
                        ),
                        ui_helpers.primary_button(
                            "Lanjut fokus", lanjut, icon=ft.Icons.BOLT
                        ),
                    ],
                )
            )
            return True

        def navigate(route: str) -> None:
            # Selama onboarding belum kelar, semua rute dibelokin ke sini.
            if route != "onboarding" and not storage.get_profile().get("onboarded"):
                route = "onboarding"

            if _tolak_keluar_fokus(route):
                nav_bar.selected_index = NAV_INDEX.get("home", 0)
                page.update()
                return

            # Sekali sehari, Kalem nyapa duluan sebelum Home biasa tampil.
            if route == "home" and storage.needs_morning_brief():
                route = "morning_brief"

            builder = ROUTES.get(route, home.build)
            content.content = builder(page, navigate)
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
                ft.NavigationBarDestination(icon=icon, label=label)
                for _, label, icon in NAV_ROUTES
            ],
        )

        page.add(ft.Column([content, nav_bar], expand=True, spacing=0))
        navigate("home")

    # Callback OAuth bisa menjadi route awal setelah halaman web dimuat ulang.
    # Kalau bukan callback, coba pulihkan sesi dari storage browser.
    if not await complete_oauth(page.route):
        saved = await preferences.get(token_key)
        if isinstance(saved, str) and saved:
            try:
                tokens = json.loads(saved)
                cloud.restore_session(tokens["access_token"], tokens["refresh_token"])
                await start_app()
            except Exception:
                await preferences.remove(token_key)
                show_login("Sesi sebelumnya sudah berakhir. Silakan masuk lagi.")
        else:
            show_login()


if __name__ == "__main__":
    ft.run(main, assets_dir=ASSETS_DIR)
