"""Pengaturan profil dan kontrol data pengguna."""
from __future__ import annotations

from datetime import date

import flet as ft

from app import storage, theme, ui_helpers
from app.date_utils import format_date_id, selected_calendar_date, years_before
from models import fitur as kfitur

DEFAULT_NEW_RANGE = [19, 22]


def build(page: ft.Page, navigate) -> ft.Control:
    """Halaman utama Pengaturan yang ringkas."""
    profile = storage.get_profile()
    name = (profile.get("name") or "Teman").strip()

    def confirm_reset(e):
        ui_helpers.show_reset_confirm(page, lambda: (storage.reset_all_data(), navigate("home")))

    def open_favorites(e) -> None:
        setattr(page, "_focusbuddy_favorites_return", "settings")
        navigate("favorites")

    profile_card = ui_helpers.card(
        ft.Column(
            [
                ft.Row(
                    [
                        ui_helpers.section_header("Profil"),
                        ft.IconButton(
                            icon=ft.Icons.SETTINGS_OUTLINED,
                            icon_size=19,
                            icon_color=theme.MUTED,
                            tooltip="Pengaturan Profil",
                            on_click=lambda e: navigate("profile_settings"),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Text("Nama", size=11, color=theme.MUTED),
                ft.Text(name, size=14, weight=ft.FontWeight.BOLD, color="#95D899"),
                ft.Text(
                    f"Hai {name} KALEM disini. KALEM bakal jadi temen kamu yang bisa "
                    "bantu di segala situasi. Jangan lupa untuk lengkapin personalisasi "
                    "di settings supaya KALEM makin kenal kamu. "
                    f"Please Enjoy {name}.",
                    size=12,
                    color=theme.MUTED,
                    text_align=ft.TextAlign.JUSTIFY,
                ),
            ],
            spacing=5,
        ),
        padding=16,
    )

    return ft.Column(
        [
            ui_helpers.page_header("Pengaturan", on_back=lambda e: navigate("home")),
            profile_card,
            _med_link_card(page, navigate),
            ui_helpers.nav_link_card(
                ft.Icons.FAVORITE_BORDER,
                theme.TERTIARY,
                "Favorit Kamu",
                f"{storage.favorites_filled()}/{len(storage.FAVORITE_FIELDS)} terisi.",
                open_favorites,
            ),
            ui_helpers.nav_link_card(
                ft.Icons.WORKSPACE_PREMIUM,
                theme.TERTIARY,
                "Subscription KALEM",
                "Freemium aktif" if storage.is_premium() else "Paket Free",
                lambda e: navigate("subscription"),
            ),
            _kartu_model(),
            _account_actions(page, confirm_reset),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


def build_profile(page: ft.Page, navigate) -> ft.Control:
    """Subhalaman untuk mengedit seluruh konteks profil KALEM."""
    profile = storage.get_profile()
    state = {
        "name": profile.get("name", ""),
        "birth_date": profile.get("birth_date", ""),
        "status": list(profile.get("status") or []),
        "sleep_condition": profile.get("sleep_condition", ""),
        "overwhelm_triggers": list(profile.get("overwhelm_triggers") or []),
        "custom_triggers": list(profile.get("custom_triggers") or []),
        "productive_hours": [list(r) for r in (profile.get("productive_hours") or [])],
        "status_input_open": False,
        "trigger_input_open": False,
    }

    name_field = ft.TextField(label="Nama panggilan kamu", value=state["name"])
    birth_date_holder = ft.Container()
    status_holder = ft.Container()
    sleep_holder = ft.Container()
    hours_holder = ft.Container()
    triggers_holder = ft.Container()
    status_field = ft.TextField(
        hint_text="Tulis kesibukan kamu",
        text_size=12,
        height=42,
        content_padding=ft.Padding.symmetric(vertical=4, horizontal=10),
        expand=True,
        on_submit=lambda e: add_custom_status(e),
    )
    trigger_field = ft.TextField(
        hint_text="Tulis sendiri, mis. rapat mendadak",
        text_size=12,
        height=42,
        content_padding=ft.Padding.symmetric(vertical=4, horizontal=10),
        expand=True,
        autofocus=True,
        on_submit=lambda e: add_custom_trigger(e),
    )

    today = date.today()
    try:
        initial_birth_date = date.fromisoformat(state["birth_date"])
    except (TypeError, ValueError):
        initial_birth_date = None
    birth_date_picker = ft.DatePicker(
        value=initial_birth_date,
        first_date=date(today.year - 100, 1, 1),
        current_date=initial_birth_date or years_before(today, 20),
        last_date=today,
        help_text="Pilih tanggal lahir",
        cancel_text="Batal",
        confirm_text="Pilih",
    )


    def render_birth_date():
        birth_date_holder.content = ft.Column(
            [
                ui_helpers.subtitle("Ulang Tahun Kamu", 12),
                ft.Container(
                    height=48,
                    bgcolor=theme.BACKGROUND,
                    border=ft.Border.all(1, theme.BORDER),
                    border_radius=12,
                    padding=ft.Padding.symmetric(horizontal=14),
                    on_click=lambda e: page.show_dialog(birth_date_picker),
                    ink=True,
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.CALENDAR_MONTH,
                                size=19,
                                color=theme.ON_BACKGROUND,
                            ),
                            ft.Text(
                                format_date_id(
                                    state["birth_date"], "Pilih tanggal lahir"
                                ),
                                size=12.5,
                                color=theme.ON_BACKGROUND,
                                expand=True,
                            ),
                            ft.Icon(
                                ft.Icons.CHEVRON_RIGHT,
                                size=18,
                                color=theme.MUTED,
                            ),
                        ],
                        spacing=10,
                    ),
                ),
            ],
            spacing=6,
        )

    def choose_birth_date(event) -> None:
        selected = selected_calendar_date(
            birth_date_picker.value, getattr(event, "data", None)
        )
        if selected is None:
            return
        state["birth_date"] = selected.isoformat()
        birth_date_picker.value = selected
        render_birth_date()
        page.update()

    birth_date_picker.on_change = choose_birth_date


    def render_status():
        custom_statuses = [v for v in state["status"] if v not in storage.STATUS_OPTIONS]
        chips = [
            ui_helpers.choice_chip(
                label, value in state["status"], lambda e, v=value: toggle_status(v)
            )
            for value, label in storage.STATUS_OPTIONS.items()
            if value != "lainnya"
        ]
        chips += [
            ui_helpers.choice_chip(v, True, lambda e, value=v: drop_custom_status(value))
            for v in custom_statuses
        ]
        if len(state["status"]) < storage.MAX_STATUS:
            chips.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.ADD, size=13, color=theme.MUTED),
                            ft.Text("Lainnya", size=12.5, color=theme.MUTED),
                        ],
                        spacing=3,
                        tight=True,
                    ),
                    border=ft.Border.all(1, theme.BORDER),
                    border_radius=12,
                    padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                    on_click=lambda e: open_status_input(),
                    ink=True,
                )
            )
        children: list[ft.Control] = [
            ui_helpers.subtitle("Kesibukan saat ini", 12),
            ft.Row(chips, spacing=6, wrap=True, run_spacing=6),
        ]
        if state["status_input_open"] and len(state["status"]) < storage.MAX_STATUS:
            children.append(
                ft.Row(
                    [
                        status_field,
                        ft.IconButton(
                            icon=ft.Icons.CHECK,
                            icon_color=theme.PRIMARY,
                            icon_size=20,
                            on_click=add_custom_status,
                        ),
                    ],
                    spacing=4,
                )
            )
        status_holder.content = ft.Column(children, spacing=6)

    def toggle_status(value: str):
        current = state["status"]
        if value in current:
            current.remove(value)
        elif len(current) < storage.MAX_STATUS:
            current.append(value)
        render_status()
        page.update()

    def open_status_input():
        state["status_input_open"] = True
        render_status()
        page.update()

    def add_custom_status(e):
        text = (status_field.value or "").strip()[:32]
        if text and text not in state["status"] and len(state["status"]) < storage.MAX_STATUS:
            state["status"].append(text)
        status_field.value = ""
        state["status_input_open"] = False
        render_status()
        page.update()

    def drop_custom_status(value: str):
        if value in state["status"]:
            state["status"].remove(value)
        render_status()
        page.update()


    def render_sleep():
        chips = [
            ui_helpers.choice_chip(
                label, value == state["sleep_condition"], lambda e, v=value: pick_sleep(v)
            )
            for value, label in storage.SLEEP_OPTIONS.items()
        ]
        sleep_holder.content = ft.Column(
            [
                ui_helpers.subtitle("Gimana tidur akhir-akhir ini?", 12),
                ft.Row(chips, spacing=6, wrap=True, run_spacing=6),
            ],
            spacing=6,
        )

    def pick_sleep(value: str):
        state["sleep_condition"] = value
        render_sleep()
        page.update()


    def render_hours():
        rows: list[ft.Control] = [
            ui_helpers.subtitle("Jam Produktif Kamu", 12),
        ]

        if not state["productive_hours"]:
            rows.append(
                ft.Text(
                    "Belum diatur. KALEM nggak bakal nebak-nebak jam produktif kamu.",
                    size=11.5,
                    color=theme.MUTED,
                    italic=True,
                )
            )

        for i, (start, end) in enumerate(state["productive_hours"]):
            label = ft.Text(
                storage.fmt_range(start, end),
                size=13.5,
                weight=ft.FontWeight.BOLD,
                color=theme.ON_BACKGROUND,
                expand=True,
            )
            slider = ft.RangeSlider(
                start_value=float(start),
                end_value=float(end),
                min=float(storage.HOUR_MIN),
                max=float(storage.HOUR_MAX),
                divisions=storage.HOUR_MAX - storage.HOUR_MIN,
                active_color=theme.PRIMARY,
                inactive_color=theme.BORDER,
                on_change=lambda e, idx=i, lbl=label: slide(idx, e, lbl),
            )
            rows.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    label,
                                    ft.IconButton(
                                        icon=ft.Icons.CLOSE,
                                        icon_size=16,
                                        icon_color=theme.MUTED,
                                        tooltip="Hapus rentang ini",
                                        on_click=lambda e, idx=i: drop_range(idx),
                                    ),
                                ],
                                spacing=4,
                            ),
                            slider,
                        ],
                        spacing=0,
                    ),
                    bgcolor=theme.BACKGROUND,
                    border_radius=12,
                    padding=ft.Padding.symmetric(vertical=8, horizontal=12),
                )
            )

        rows.append(
            ft.TextButton(
                content=ft.Text("+ Tambah rentang", size=12, color=theme.PRIMARY),
                on_click=lambda e: add_range(),
            )
        )
        hours_holder.content = ft.Column(rows, spacing=8)

    def slide(index: int, e, label: ft.Text):
        start = int(round(e.control.start_value))
        end = int(round(e.control.end_value))
        if end <= start:
            end = min(start + 1, storage.HOUR_MAX)
        state["productive_hours"][index] = [start, end]
        label.value = storage.fmt_range(start, end)
        page.update()

    def add_range():
        state["productive_hours"].append(list(DEFAULT_NEW_RANGE))
        render_hours()
        page.update()

    def drop_range(index: int):
        state["productive_hours"].pop(index)
        render_hours()
        page.update()


    def render_triggers():
        picked = state["overwhelm_triggers"] + state["custom_triggers"]
        full = len(picked) >= storage.MAX_TRIGGERS

        chips: list[ft.Control] = [
            ui_helpers.choice_chip(
                label, value in state["overwhelm_triggers"], lambda e, v=value: toggle_trigger(v)
            )
            for value, label in storage.TRIGGER_OPTIONS.items()
        ]
        chips += [
            ui_helpers.choice_chip(t, True, lambda e, v=t: drop_custom_trigger(v))
            for t in state["custom_triggers"]
        ]

        if not full:
            chips.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.ADD, size=13, color=theme.MUTED),
                            ft.Text("Lainnya", size=12.5, color=theme.MUTED),
                        ],
                        spacing=3,
                        tight=True,
                    ),
                    border=ft.Border.all(1, theme.BORDER),
                    border_radius=12,
                    padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                    on_click=lambda e: open_trigger_input(),
                    ink=True,
                )
            )

        children: list[ft.Control] = [
            ui_helpers.subtitle("Hal yang buat kamu khawatir", 12),
            ft.Row(chips, spacing=6, wrap=True, run_spacing=6),
        ]

        if state["trigger_input_open"] and not full:
            children.append(
                ft.Row(
                    [
                        trigger_field,
                        ft.IconButton(
                            icon=ft.Icons.CHECK,
                            icon_color=theme.PRIMARY,
                            icon_size=20,
                            on_click=add_custom_trigger,
                        ),
                    ],
                    spacing=4,
                )
            )

        triggers_holder.content = ft.Column(children, spacing=6)

    def toggle_trigger(value: str):
        current = state["overwhelm_triggers"]
        total = len(current) + len(state["custom_triggers"])
        if value in current:
            current.remove(value)
        elif total < storage.MAX_TRIGGERS:
            current.append(value)
        render_triggers()
        page.update()

    def open_trigger_input():
        state["trigger_input_open"] = True
        render_triggers()
        page.update()

    def add_custom_trigger(e):
        raw = (trigger_field.value or "").strip()
        text = raw[:32]
        total = len(state["overwhelm_triggers"]) + len(state["custom_triggers"])
        if text and text not in state["custom_triggers"] and total < storage.MAX_TRIGGERS:
            state["custom_triggers"].append(text)
        trigger_field.value = ""
        state["trigger_input_open"] = False
        render_triggers()
        page.update()

    def drop_custom_trigger(value: str):
        if value in state["custom_triggers"]:
            state["custom_triggers"].remove(value)
        render_triggers()
        page.update()


    def save_profile(e):
        state["name"] = (name_field.value or "").strip() or "Teman"
        storage.save_profile(
            {
                "name": state["name"],
                "birth_date": state["birth_date"],
                "status": state["status"],
                "sleep_condition": state["sleep_condition"],
                "overwhelm_triggers": state["overwhelm_triggers"],
                "custom_triggers": state["custom_triggers"],
                "productive_hours": state["productive_hours"],
            }
        )
        navigate("settings")

    render_birth_date()
    render_status()
    render_sleep()
    render_hours()
    render_triggers()

    return ft.Column(
        [
            ui_helpers.page_header(
                "Pengaturan Profil", on_back=lambda e: navigate("settings")
            ),
            ui_helpers.card(
                ft.Column(
                    [
                        name_field,
                        birth_date_holder,
                        status_holder,
                        hours_holder,
                        sleep_holder,
                        triggers_holder,
                        ui_helpers.wide_button("Simpan Profil", save_profile, icon=ft.Icons.SAVE),
                    ],
                    spacing=14,
                )
            ),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


def _kartu_model() -> ft.Control:
    import models as ml

    ringkas = kfitur.ringkas_untuk_ui()
    st = ml.status_semua()

    baris: list[ft.Control] = []

    def item(judul: str, siap: bool, teks: str):
        baris.append(
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE if siap else ft.Icons.HOURGLASS_EMPTY,
                        size=15,
                        color=theme.SUCCESS if siap else theme.MUTED,
                    ),
                    ft.Column(
                        [
                            ft.Text(judul, size=12.5, weight=ft.FontWeight.BOLD,
                                    color=theme.ON_BACKGROUND),
                            ft.Text(teks, size=11, color=theme.MUTED),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )

    d = st["durasi"]
    item("Perkiraan waktu tugas", d["siap"],
         f"Dilatih dari {d['n_latih']} tugas contoh"
         + (f" · kecepatan kamu: {ringkas['sesi_7h']} sesi minggu ini" if ringkas["sesi_7h"] else ""))

    m = st["mood"]
    item("Pola mood", m["siap_pola"],
         f"{m['n_catatan']} catatan"
         + (" · udah bisa baca pola" if m["siap_model"] else " · butuh 5 buat mulai baca pola"))

    o = st["overwhelm"]
    item("Deteksi hari berat", o["siap"],
         f"Belajar dari {o['n_latih']} hari" if o["siap"]
         else f"Butuh {o['min_hari']} hari check-in dulu")

    k = st["kalem"]
    item("KALEM belajar cara memulai", k["siap"],
         f"Belajar dari {k['n_latih']} keputusan fokus"
         if k["siap"] else f"Butuh {k['min_records']} keputusan fokus dulu")

    pn = st["penenang"]
    item("Opsi jeda yang cocok", bool(pn["terukur"]),
         f"{pn['n_pakai']}x kamu pakai halaman jeda" if pn["n_pakai"]
         else "Belum ada data — urutannya ngikutin jawaban onboarding")

    if ringkas["kalibrasi"] != 1.0:
        arah = "lebih lama" if ringkas["kalibrasi"] > 1 else "lebih cepat"
        baris.append(
            ft.Text(
                f"Catatan: sesi kamu biasanya {arah} dari yang diperkirakan "
                f"(faktor {ringkas['kalibrasi']}). KALEM udah nyesuain.",
                size=10.5,
                color=theme.MUTED,
            )
        )

    return ui_helpers.card(
        ft.Column(
            [
                ui_helpers.section_header("Yang KALEM Pelajari"),
                ft.Text(
                    "Semua ini dipelajari dari pemakaian akun kamu sendiri, tidak "
                    "dicampur dengan akun lain. Makin sering dipakai, makin nyesuain.",
                    size=11.5,
                    color=theme.MUTED,
                ),
                *baris,
            ],
            spacing=10,
        ),
        padding=16,
    )


def _med_link_card(page: ft.Page, navigate) -> ft.Container:
    def open_medication(e) -> None:
        setattr(page, "_focusbuddy_med_setup_return", "settings")
        navigate("med_setup")

    return ft.Container(
        content=ft.Row(
            [
                ui_helpers.med_icon(24, theme.TERTIARY),
                ft.Column(
                    [
                        ft.Text("Pengingat Obat", weight=ft.FontWeight.BOLD, color=theme.ON_BACKGROUND),
                        ft.Text("Setup obat, stok, & jadwal absen.", size=11.5, color=theme.MUTED),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=theme.MUTED, size=20),
            ],
            spacing=12,
        ),
        bgcolor=theme.SURFACE,
        border=ft.Border.all(1, theme.BORDER),
        border_radius=theme.CARD_RADIUS,
        padding=16,
        on_click=open_medication,
        ink=True,
    )


def _account_actions(page: ft.Page, confirm_reset) -> ft.Control:
    logout = getattr(page, "_focusbuddy_logout", None)

    def danger_button(label: str, icon: str, on_click, *, visible: bool = True):
        return ft.Row(
            [
                ft.Button(
                    height=48,
                    expand=True,
                    bgcolor="#EA3F46",
                    color="#FFFFFF",
                    icon=icon,
                    icon_color="#FFFFFF",
                    content=ft.Text(
                        label,
                        color="#FFFFFF",
                        size=14,
                        weight=ft.FontWeight.W_600,
                    ),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=24),
                    ),
                    on_click=on_click,
                )
            ],
            spacing=0,
            visible=visible,
        )

    return ft.Column(
        [
            ft.Text(
                "Logout",
                size=18,
                weight=ft.FontWeight.W_700,
                color=theme.ON_BACKGROUND,
            ),
            danger_button(
                "Keluar dari akun",
                ft.Icons.LOGOUT,
                logout,
                visible=logout is not None,
            ),
            ft.Container(height=8),
            ft.Text(
                "Hapus semua data",
                size=18,
                weight=ft.FontWeight.W_700,
                color=theme.ON_BACKGROUND,
            ),
            danger_button(
                "Hapus semua data",
                ft.Icons.DELETE_OUTLINE,
                confirm_reset,
            ),
        ],
        spacing=8,
    )
