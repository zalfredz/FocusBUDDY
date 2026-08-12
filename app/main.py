"""Entry point aplikasi Flet FocusBuddy."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import flet as ft

from app import config, focus_session, storage, theme, ui_helpers
from app.cloud import CloudUnavailable, FocusBuddyCloud, oauth_code_from_url
from app.views import (
    daily_checkin,
    demo_tools,
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
    subscription,
    task_add,
    tracker,
)

ASSETS_DIR = str(Path(__file__).resolve().parent / "assets")

NAV_ROUTES = [
    ("tracker", "Tracker", ft.Icons.CALENDAR_MONTH),
    ("home", "Beranda", ft.Icons.HOME_ROUNDED),
    ("mood", "Mood", ft.Icons.FAVORITE_ROUNDED),
]

ROUTES = {
    "home": home.build,
    "daily_checkin": daily_checkin.build,
    "tracker": tracker.build,
    "mood": mood.build,
    "diary": diary.build,
    "reset": reset.build,
    "med_setup": med_setup.build,
    "onboarding": onboarding.build,
    "favorites": favorites.build,
    "settings": settings.build,
    "profile_settings": settings.build_profile,
    "subscription": subscription.build,
    "task_add": task_add.build,
    "morning_brief": morning_brief.build,
    "inbox": inbox.build,
}

if config.DEMO_MODE:
    ROUTES["demo_tools"] = demo_tools.build

FULLSCREEN_ROUTES = {"onboarding", "morning_brief", "daily_checkin", "task_add"}

FOKUS_BOLEH = {"home"}

NAV_INDEX = {name: i for i, (name, _, _) in enumerate(NAV_ROUTES)}
_log = logging.getLogger(__name__)


def focus_navigation_allowed(route: str) -> bool:
    return not focus_session.is_active() or route in FOKUS_BOLEH


def main_navigation_visible(route: str) -> bool:
    """Navigation tetap terlihat; guard Focus yang menolak perpindahannya."""
    return route not in FULLSCREEN_ROUTES


async def _read_preference_string(
    preferences: Any,
    key: str,
    *,
    attempts: int = 8,
    delay_seconds: float = 0.15,
) -> str:
    for attempt in range(max(1, attempts)):
        value = await preferences.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if attempt + 1 < attempts:
            await asyncio.sleep(delay_seconds)
    return ""


async def _restore_saved_cloud_session(
    cloud: FocusBuddyCloud,
    preferences: Any,
    token_key: str,
) -> bool:
    saved = await preferences.get(token_key)
    if not isinstance(saved, str) or not saved:
        return False
    try:
        tokens = json.loads(saved)
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            return False
        cloud.restore_session(access_token, refresh_token)
        return cloud.user() is not None
    except Exception:
        return False


async def _save_cloud_session(
    cloud: FocusBuddyCloud,
    preferences: Any,
    token_key: str,
    *,
    attempts: int = 4,
    delay_seconds: float = 0.15,
) -> bool:
    session = cloud.session()
    if not session:
        return False
    payload = json.dumps(
        {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
        }
    )
    for attempt in range(max(1, attempts)):
        try:
            if await preferences.set(token_key, payload):
                return True
        except Exception:
            pass
        if attempt + 1 < attempts:
            await asyncio.sleep(delay_seconds)
    return False


async def _exchange_or_restore_oauth(
    cloud: FocusBuddyCloud,
    preferences: Any,
    code: str,
    pkce_key: str,
    token_key: str,
) -> str:
    verifier = await _read_preference_string(preferences, pkce_key)
    if verifier:
        cloud.restore_pkce_verifier(verifier)
        try:
            cloud.exchange_code(code, verifier)
            return "exchange"
        except Exception:
            if await _restore_saved_cloud_session(cloud, preferences, token_key):
                return "session"
            raise
    if await _restore_saved_cloud_session(cloud, preferences, token_key):
        return "session"
    raise RuntimeError("PKCE verifier tidak tersedia saat callback")


def _oauth_candidates_from_page(page: ft.Page, raw_route: str = "") -> tuple[Any, ...]:
    candidates: list[Any] = []
    try:
        page.query()
        candidates.append(page.query.to_dict)
    except Exception:
        pass
    candidates.extend((raw_route, page.route, page.url))
    return tuple(candidates)


def _canonical_local_login_url(page_url: str, redirect_uri: str) -> str:
    def origin(value: str) -> tuple[str, str, int | None]:
        parsed = urlparse(value or "")
        scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
        return scheme, (parsed.hostname or "").lower(), parsed.port

    current = origin(page_url)
    target = origin(redirect_uri)
    loopback = {"localhost", "127.0.0.1", "::1"}
    if (
        current[1] in loopback
        and target[1] in loopback
        and current != target
    ):
        parsed = urlparse(redirect_uri)
        return f"{target[0]}://{parsed.netloc}/"
    return ""


def _hydrate_user_state(cloud: FocusBuddyCloud, user_id: str) -> str:
    had_user_cache = storage.current_data_file().exists()
    remote = cloud.download_state(user_id)
    if remote is not None:
        storage.save_state(remote)
        return "database"
    if had_user_cache:
        cloud.upload_state(user_id, storage.load_state())
        return "cache"
    cloud.upload_state(user_id, storage.load_state())
    return "baru"


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
    oauth_processing = False

    async def save_session() -> bool:
        return await _save_cloud_session(cloud, preferences, token_key)

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
        nonlocal app_started
        user = cloud.user()
        if user is None:
            show_login("Sesi Google belum tersedia. Coba masuk lagi.")
            return

        storage.set_cloud_save_hook(None)
        storage.configure_user_storage(user.id)
        cloud_status = "Tersinkron ke database"
        try:
            _hydrate_user_state(cloud, user.id)
        except Exception:
            cloud_status = "Sinkronisasi tertunda — koneksi akan dicoba lagi"
            storage.load_state()

        storage.set_cloud_save_hook(
            lambda state: cloud.enqueue_state(user.id, state)
        )
        setattr(page, "_focusbuddy_cloud_user", user)
        setattr(page, "_focusbuddy_cloud_status", cloud_status)
        setattr(page, "_focusbuddy_logout", logout)
        if not await save_session():
            _log.warning("Sesi OAuth aktif tetapi token browser belum tersimpan")
        app_started = True
        build_application()

    async def complete_oauth(raw_route: str = "") -> bool:
        nonlocal oauth_processing
        code, error = oauth_code_from_url(
            *_oauth_candidates_from_page(page, raw_route)
        )
        if error:
            show_login(f"Login Google gagal: {error}")
            return True
        if not code:
            return False
        if oauth_processing:
            return True
        oauth_processing = True
        show_login("Menyambungkan akun Google…", busy=True)
        try:
            try:
                await _exchange_or_restore_oauth(
                    cloud, preferences, code, pkce_key, token_key
                )
                if not await save_session():
                    _log.warning(
                        "OAuth berhasil tetapi token browser belum tersimpan"
                    )
                try:
                    await preferences.remove(pkce_key)
                except Exception:
                    _log.warning("PKCE browser belum bisa dibersihkan")
            except Exception:
                _log.exception("OAuth callback FocusBuddy gagal")
                show_login("Login belum berhasil. Silakan coba lagi.")
                return True

            try:
                await start_app()
                if page.route != "/":
                    await page.push_route("/")
            except Exception:
                _log.exception("Aplikasi gagal dimuat setelah OAuth berhasil")
                show_login(
                    "Akun berhasil tersambung, tapi aplikasi belum selesai dimuat. "
                    "Coba refresh halaman."
                )
            return True
        finally:
            oauth_processing = False

    async def login_google(e) -> None:
        show_login("Membuka halaman Google…", busy=True)
        try:
            url = cloud.begin_google_login()
            verifier = cloud.pkce_verifier()
            if not verifier:
                raise RuntimeError("PKCE verifier tidak terbentuk")
            saved = await preferences.set(pkce_key, verifier)
            if not saved:
                raise RuntimeError("PKCE verifier tidak bisa disimpan")
            await launcher.launch_url(url, web_only_window_name="_self")
        except Exception:
            _log.exception("Tidak dapat memulai OAuth FocusBuddy")
            show_login("Nggak bisa membuka login Google. Coba beberapa saat lagi.")

    def show_login(message: str = "", busy: bool = False) -> None:
        message_color = theme.DANGER if "gagal" in message.lower() else theme.MUTED
        heading = ft.Text(
            spans=[
                ft.TextSpan(
                    "Selamat datang di\n",
                    style=ft.TextStyle(
                        color="#FFFFFF",
                        font_family=theme.FONT_AUTH,
                        size=33,
                        height=1.0,
                        weight=ft.FontWeight.W_300,
                    ),
                ),
                ft.TextSpan(
                    "FocusBuddy",
                    style=ft.TextStyle(
                        color="#95D899",
                        font_family=theme.FONT_AUTH,
                        size=33,
                        height=1.0,
                        weight=ft.FontWeight.W_700,
                    ),
                ),
            ],
            font_family=theme.FONT_AUTH,
            text_align=ft.TextAlign.LEFT,
        )
        page.clean()
        page.add(
            ft.Container(
                expand=True,
                bgcolor="#141416",
                alignment=ft.Alignment.CENTER,
                padding=ft.Padding(left=24, top=32, right=24, bottom=32),
                content=ft.Container(
                    content=ft.Column(
                        [
                            heading,
                            ft.Image(
                                src="Property 1=good_mood.png",
                                width=300,
                                height=300,
                                fit=ft.BoxFit.CONTAIN,
                            ),
                            ft.Column(
                                [
                                    ft.Button(
                                        width=230,
                                        height=48,
                                        content=ft.Row(
                                            [
                                                ft.Image(
                                                    src="google_logo.svg",
                                                    width=18,
                                                    height=18,
                                                ),
                                                ft.Text(
                                                    "Masuk dengan Google",
                                                    size=15,
                                                    weight=ft.FontWeight.W_800,
                                                    color="#1C1B2C",
                                                    font_family=theme.FONT_AUTH,
                                                ),
                                            ],
                                            alignment=ft.MainAxisAlignment.CENTER,
                                            spacing=10,
                                            tight=True,
                                        ),
                                        style=ft.ButtonStyle(
                                            bgcolor="#FFFFFF",
                                            color="#1C1B2C",
                                            padding=0,
                                            shape=ft.RoundedRectangleBorder(radius=100),
                                        ),
                                        on_click=login_google,
                                        disabled=busy,
                                    ),
                                    ft.ProgressRing(width=20, height=20, visible=busy),
                                    ft.Text(
                                        message,
                                        size=11.5,
                                        color=message_color,
                                        font_family=theme.FONT_AUTH,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=8,
                                tight=True,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=28,
                        scroll=ft.ScrollMode.AUTO,
                    ),
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

        storage.touch_last_open()

        def _tolak_keluar_fokus(tujuan: str) -> bool:
            if focus_navigation_allowed(tujuan):
                return False

            s = focus_session.snapshot()
            apa = s["label"] or s["task_title"] or "satu hal"

            def lanjut(e):
                page.pop_dialog()

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
                                "Selesaikan, pause, atau akhiri sesi dari layar Focus dulu.",
                                size=11.5,
                                color=theme.MUTED,
                            ),
                        ],
                        spacing=8,
                        tight=True,
                    ),
                    actions=[
                        ui_helpers.primary_button(
                            "Lanjut fokus", lanjut, icon=ft.Icons.BOLT
                        ),
                    ],
                )
            )
            return True

        def navigate(route: str) -> None:
            if _tolak_keluar_fokus(route):
                nav_bar.selected_index = NAV_INDEX.get("home", 0)
                page.update()
                return

            cleanup = getattr(page, "_focusbuddy_view_cleanup", None)
            if callable(cleanup):
                cleanup()
                setattr(page, "_focusbuddy_view_cleanup", None)

            if route != "onboarding" and not storage.get_profile().get("onboarded"):
                route = "onboarding"

            if route == "home" and storage.ready_for_morning_brief():
                route = "morning_brief"

            if (
                route == "home"
                and not focus_session.is_active()
                and storage.today_mood() is None
            ):
                route = "daily_checkin"

            builder = ROUTES.get(route, home.build)
            content.content = builder(page, navigate)
            if route in NAV_INDEX:
                nav_bar.selected_index = NAV_INDEX[route]
            nav_shell.visible = main_navigation_visible(route)
            page.update()

        nav_bar = ft.NavigationBar(
            selected_index=0,
            bgcolor="#484863",
            indicator_color="#DDE0FF",
            indicator_shape=ft.RoundedRectangleBorder(radius=24),
            on_change=lambda e: navigate(NAV_ROUTES[e.control.selected_index][0]),
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icon(icon, color="#DDE0FF"),
                    selected_icon=ft.Icon(icon, color="#484863"),
                    label=label,
                )
                for _, label, icon in NAV_ROUTES
            ],
        )

        nav_shell = ft.Container(
            content=nav_bar,
            bgcolor="#484863",
            border_radius=100,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            margin=ft.Padding(left=20, top=4, right=20, bottom=12),
        )

        page.add(ft.Column([content, nav_shell], expand=True, spacing=0))
        navigate("home")

    callback_code, _ = oauth_code_from_url(
        *_oauth_candidates_from_page(page, page.route)
    )
    canonical_url = _canonical_local_login_url(
        page.url or "", config.SUPABASE_REDIRECT_URI
    )
    if canonical_url and not callback_code:
        show_login("Menyiapkan login Google…", busy=True)
        await launcher.launch_url(canonical_url, web_only_window_name="_self")
        return

    oauth_completed = await complete_oauth(page.route)
    if not oauth_completed:
        pending_verifier = await preferences.get(pkce_key)
        if isinstance(pending_verifier, str) and pending_verifier:
            show_login("Menyambungkan akun Google…", busy=True)
            for _ in range(12):
                await asyncio.sleep(0.15)
                if app_started:
                    oauth_completed = True
                    break
                if await complete_oauth(page.route):
                    oauth_completed = True
                    break

    if not oauth_completed:
        try:
            restored = await _restore_saved_cloud_session(
                cloud, preferences, token_key
            )
        except Exception:
            restored = False

        if restored:
            try:
                await start_app()
            except Exception:
                _log.exception("Aplikasi gagal dimuat dari sesi tersimpan")
                show_login(
                    "Sesi kamu masih aktif, tapi aplikasi belum selesai dimuat. "
                    "Coba refresh halaman."
                )
        else:
            await preferences.remove(token_key)
            show_login()


if __name__ == "__main__":
    ft.run(main, assets_dir=ASSETS_DIR)
