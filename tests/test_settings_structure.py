"""Behavior contract untuk struktur Pengaturan dan navigasi subhalaman."""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import flet as ft

from app import storage
from app.cloud import FocusBuddyCloud, oauth_code_from_url
from app.views import favorites, med_setup, settings


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  [OK] " if condition else "  [FAIL] ") + message)
    if not condition:
        FAILURES.append(message)


class FakePage:
    def __init__(self) -> None:
        self.dialogs: list = []
        self.overlay: list = []
        self._focusbuddy_cloud_status = "Tersinkron ke database"
        self._focusbuddy_cloud_user = SimpleNamespace(
            name="Akun Rahasia", email="rahasia@example.com"
        )
        self._focusbuddy_logout = lambda event: None

    def update(self) -> None:
        pass

    def show_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def run_task(self, fn, *args) -> None:
        pass


def walk(control):
    if control is None:
        return
    yield control
    for child in getattr(control, "controls", []) or []:
        yield from walk(child)
    for action in getattr(control, "actions", []) or []:
        yield from walk(action)
    yield from walk(getattr(control, "content", None))


def text_values(root) -> list[str]:
    return [
        item.value
        for item in walk(root)
        if isinstance(getattr(item, "value", None), str)
    ]


def contains_text(control, value: str) -> bool:
    return value in text_values(control)


def clickable(root, text: str):
    return next(
        (
            item
            for item in walk(root)
            if getattr(item, "on_click", None) is not None and contains_text(item, text)
        ),
        None,
    )


def icon_button(root, *, icon=None, tooltip=None):
    return next(
        (
            item
            for item in walk(root)
            if isinstance(item, ft.IconButton)
            and (icon is None or item.icon == icon)
            and (tooltip is None or item.tooltip == tooltip)
        ),
        None,
    )


def scenario_main_settings_is_clean() -> None:
    print("\n=== Pengaturan utama ringkas dan berurutan ===")
    page = FakePage()
    routes: list[str] = []
    root = settings.build(page, routes.append)
    shown = text_values(root)

    for value in (
        "PENGATURAN" if "PENGATURAN" in shown else "Pengaturan",
        "PROFIL",
        "Nama",
        "AL",
        "Usia",
        "18–24",
        "Pengingat Obat",
        "Favorit Kamu",
        "YANG KALEM PELAJARI",
        "PRIVASI & DATA",
        "AKUN & CLOUD",
        "Akun Rahasia",
        "rahasia@example.com",
        "Tersinkron ke database",
        "Keluar dari akun",
    ):
        check(value in shown, f"Pengaturan utama menampilkan '{value}'")

    hidden = (
        "Apa kesibukan kamu saat ini?",
        "Kapan biasanya kamu paling enak buat fokus?",
        "Pola tidur kamu akhir-akhir ini gimana?",
        "Hal apa yang paling sering bikin kamu overwhelm?",
    )
    for value in hidden:
        check(value not in shown, f"Pengaturan utama tidak menampilkan '{value}'")

    check(
        not any(isinstance(item, (ft.TextField, ft.RangeSlider)) for item in walk(root)),
        "field detail profil tidak dirender di halaman utama",
    )
    check(
        shown.index("PRIVASI & DATA") < shown.index("AKUN & CLOUD"),
        "card akun/auth tampil setelah Privasi & Data",
    )

    settings_button = icon_button(root, tooltip="Pengaturan Profil")
    check(settings_button is not None, "icon Settings profil tersedia")
    if settings_button is not None:
        settings_button.on_click(None)
    check(routes == ["profile_settings"], "icon Settings membuka Pengaturan Profil")

    back = icon_button(root, icon=ft.Icons.ARROW_BACK)
    check(back is not None, "Pengaturan punya tombol kembali di kiri atas")
    if back is not None:
        back.on_click(None)
    check(routes[-1:] == ["home"], "tombol kembali Pengaturan menuju Home")


def scenario_profile_detail_edits_existing_fields() -> None:
    print("\n=== Pengaturan Profil mengedit field existing dan kembali ===")
    page = FakePage()
    routes: list[str] = []
    root = settings.build_profile(page, routes.append)
    shown = text_values(root)

    required_copy = (
        "Pengaturan Profil",
        "Berapa usia kamu sekarang?",
        "Apa kesibukan kamu saat ini?",
        "Biar KALEM tahu gambaran ritme hari-harimu. Boleh pilih maksimal 3 ya.",
        "Kapan biasanya kamu paling enak buat fokus?",
        "Biar KALEM tahu kapan harus bantu kamu fokus atau nurunin ekspektasi pas kamu lagi capek.",
        "Pola tidur kamu akhir-akhir ini gimana?",
        "Biar KALEM tahu seberapa ramah target hari ini buat energi kamu.",
        "Hal apa yang paling sering bikin kamu overwhelm?",
        "Biar KALEM paham pemicunya dan bisa bantu kasih penenang yang tepat pas kamu butuh. (Pilih maks. 4)",
    )
    for value in required_copy:
        check(value in shown, f"Profil Detail menampilkan copy '{value}'")

    name = next(
        (item for item in walk(root) if isinstance(item, ft.TextField)
         and item.label == "Nama panggilan kamu"),
        None,
    )
    check(name is not None, "nama tetap bisa diedit")
    if name is not None:
        name.value = "Alya"

    for label in (
        "25-34",
        "Mahasiswa / pelajar",
        "Kerja kantoran",
        "Sering begadang",
        "Deadline mepet",
    ):
        control = clickable(root, label)
        check(control is not None, f"pilihan '{label}' bisa diedit")
        if control is not None:
            control.on_click(SimpleNamespace(control=control))

    slider = next((item for item in walk(root) if isinstance(item, ft.RangeSlider)), None)
    check(slider is not None, "jam produktif tetap bisa diedit")
    if slider is not None:
        slider.on_change(SimpleNamespace(control=SimpleNamespace(start_value=8, end_value=12)))

    save = clickable(root, "Simpan Profil")
    check(save is not None, "tombol Simpan Profil tersedia")
    if save is not None:
        save.on_click(None)

    profile = storage.get_profile()
    check(profile["name"] == "Alya", "nama tersimpan pada field existing")
    check(profile["age_range"] == "25-34", "usia tersimpan pada field existing")
    check(profile["status"] == ["kerja"], "kesibukan tersimpan pada field existing")
    check(profile["productive_hours"] == [[8, 12]], "jam produktif tetap tersimpan")
    check(profile["sleep_condition"] == "begadang", "pola tidur tetap tersimpan")
    check(profile["overwhelm_triggers"] == ["deadline"], "pemicu overwhelm tetap tersimpan")
    check(profile["on_medication"] == "kadang", "field profil lain tidak hilang saat save")
    check(routes == ["settings"], "Simpan kembali ke Pengaturan")

    refreshed = text_values(settings.build(page, routes.append))
    check("Alya" in refreshed and "25–34" in refreshed,
          "nama dan usia terbaru muncul di Pengaturan utama")

    routes.clear()
    back = icon_button(root, icon=ft.Icons.ARROW_BACK)
    check(back is not None, "Pengaturan Profil punya tombol kembali di kiri atas")
    if back is not None:
        back.on_click(None)
    check(routes == ["settings"], "tombol kembali Profil menuju Pengaturan")


def scenario_link_cards_and_back_buttons() -> None:
    print("\n=== Link Settings dan tombol kembali halaman turunan ===")
    page = FakePage()
    routes: list[str] = []
    root = settings.build(page, routes.append)

    medication = clickable(root, "Pengingat Obat")
    favorite = clickable(root, "Favorit Kamu")
    check(medication is not None and favorite is not None,
          "card Pengingat Obat dan Favorit tetap bisa ditekan")
    if medication is not None:
        medication.on_click(None)
    if favorite is not None:
        favorite.on_click(None)
    check(routes == ["med_setup", "favorites"], "kedua card membuka route existing")

    for name, builder in (("Pengingat Obat", med_setup.build), ("Favorit Kamu", favorites.build)):
        destinations: list[str] = []
        child = builder(page, destinations.append)
        back = icon_button(child, icon=ft.Icons.ARROW_BACK)
        check(back is not None, f"{name} punya tombol kembali di kiri atas")
        if back is not None:
            back.on_click(None)
        check(destinations == ["settings"], f"{name} kembali ke Pengaturan")


def scenario_auth_backend_remains_available() -> None:
    print("\n=== Auth dan backend tetap tersedia ===")
    import app.main as main

    check(FocusBuddyCloud is not None and callable(oauth_code_from_url),
          "client cloud dan parser OAuth tetap tersedia")
    check("settings" in main.ROUTES and "profile_settings" in main.ROUTES,
          "router menambahkan Profil Detail tanpa menghapus Settings")


def prepare() -> None:
    state = storage.reset_all_data()
    state["profile"].update(
        {
            "name": "AL",
            "age_range": "18-24",
            "status": ["mahasiswa"],
            "productive_hours": [[6, 11]],
            "sleep_condition": "cukup",
            "overwhelm_triggers": [],
            "custom_triggers": [],
            "on_medication": "kadang",
            "onboarded": True,
        }
    )
    storage.save_state(state)


def main() -> int:
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    with tempfile.TemporaryDirectory(prefix="focusbuddy_settings_") as directory:
        storage.DATA_DIR = Path(directory)
        storage.DATA_FILE = storage.DATA_DIR / "data.json"
        storage.BACKUP_FILE = storage.DATA_DIR / "data.json.bak"
        try:
            for scenario in (
                scenario_main_settings_is_clean,
                scenario_profile_detail_edits_existing_fields,
                scenario_link_cards_and_back_buttons,
                scenario_auth_backend_remains_available,
            ):
                prepare()
                scenario()
        finally:
            storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"GAGAL: {len(FAILURES)} behavior Settings belum terpenuhi")
        return 1
    print("SEMUA BEHAVIOR SETTINGS LULUS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
