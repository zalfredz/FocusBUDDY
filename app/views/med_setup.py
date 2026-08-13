"""Halaman setup, stok, dan kepatuhan obat tanpa rekomendasi dosis."""
from __future__ import annotations

import flet as ft

from app import buddy, clock, storage, theme, ui_helpers
from app.core import bpom
from app.core.medication_model import (
    ONLINE_PHARMACY_PARTNERS,
    REMINDER_THRESHOLD_DAYS,
    check_status,
    maps_search_url,
    missed_streak,
)


def build(page: ft.Page, navigate) -> ft.Control:
    back_route = getattr(page, "_focusbuddy_med_setup_return", "home")
    existing = storage.get_medication()
    status = check_status(existing)

    bpom_holder = ft.Container()

    def check_name(e=None):
        typed = (name_field.value or "").strip()
        if not typed or not bpom.available():
            bpom_holder.content = None
            page.update()
            return

        match = bpom.lookup(typed)

        if not match.found:
            bpom_holder.content = _note_row(
                ft.Icons.HELP_OUTLINE,
                theme.MUTED,
                "Nggak ketemu di daftar obat BPOM. Tetap bisa disimpan kok — "
                "jamu, suplemen, dan racikan apotek emang terdaftar di daftar "
                "yang beda, jadi wajar nggak muncul di sini.",
            )
            page.update()
            return

        rows: list[ft.Control] = []
        saran = bpom.suggestion_for(typed, match)
        catatan_zat = bpom.ingredient_note(match)

        if saran:
            rows.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SPELLCHECK, size=15, color=theme.WARN),
                        ft.Text(f"Maksudnya {saran}?", size=12,
                                color=theme.ON_BACKGROUND, expand=True),
                        ft.TextButton(
                            content=ft.Text("Pakai", size=11.5),
                            on_click=lambda ev, n=saran: use_name(n),
                        ),
                    ],
                    spacing=6,
                )
            )
        elif catatan_zat:
            rows.append(_note_row(ft.Icons.SCIENCE, theme.SECONDARY, catatan_zat))
        else:
            rows.append(
                _note_row(
                    ft.Icons.VERIFIED,
                    theme.SUCCESS,
                    f"Terdaftar di BPOM — {match.name}",
                )
            )

        rows.append(
            ft.Text(bpom.summary(match), size=10.5, color=theme.MUTED)
        )

        if match.butuh_resep:
            rows.append(
                _note_row(
                    ft.Icons.LOCK_OUTLINE,
                    theme.TERTIARY,
                    f"Golongan {match.golongan.lower()} — cuma boleh dengan resep dokter.",
                )
            )
        if match.registrasi_kedaluwarsa:
            rows.append(
                _note_row(
                    ft.Icons.SCHEDULE,
                    theme.MUTED,
                    f"Izin edarnya tercatat berlaku sampai {match.berlaku_sampai}. "
                    "Ini soal registrasi, bukan tanggal kedaluwarsa obatnya.",
                )
            )

        bpom_holder.content = ft.Container(
            content=ft.Column(rows, spacing=5),
            bgcolor=theme.BACKGROUND,
            border_radius=10,
            padding=ft.Padding.symmetric(vertical=8, horizontal=10),
        )
        page.update()

    def use_name(name: str):
        name_field.value = name
        check_name()

    name_field = ft.TextField(
        label="Nama obat",
        value=existing["name"] if existing else "",
        hint_text="mis. Concerta 18mg",
        on_change=check_name,
    )
    stock_field = ft.TextField(
        label="Sisa pil saat ini",
        value=str(int(existing["pills_left"])) if existing else "",
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    dose_field = ft.TextField(
        label="Berapa pil sehari? - Sesuai resep dokter",
        value=str(existing["pills_per_day"]) if existing else "1",
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    for field in (name_field, stock_field, dose_field):
        field.color = theme.ON_BACKGROUND
        field.cursor_color = theme.ON_BACKGROUND
        field.label_style = ft.TextStyle(color=theme.ON_BACKGROUND)
        field.hint_style = ft.TextStyle(color=theme.MUTED)
        field.bgcolor = "#343446"
        field.filled = True
        field.border_color = theme.BORDER
        field.focused_border_color = theme.PRIMARY

    status_holder = ft.Container(visible=False)
    pharmacy_holder = ft.Column(spacing=10, visible=False)

    def render_status():
        current = check_status(storage.get_medication())
        if not current.active:
            status_holder.visible = False
            return

        color = theme.DANGER if current.needs_reminder else theme.SUCCESS
        message = current.message or (
            f"Stok {current.name} cukup buat sekitar {current.days_left} hari lagi."
        )

        children: list[ft.Control] = [
            ui_helpers.banner(message, color, "med"),
            ft.Text(
                f"Pil kamu sisa {current.pills_remaining:g} nihh. KALEM bakal ingetin "
                f"kalau stok obat kamu ga cukup buat {REMINDER_THRESHOLD_DAYS} hari kedepan",
                size=12,
                color=theme.MUTED,
            ),
        ]

        if current.taken_today:
            children.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE, color=theme.SUCCESS, size=16),
                        ft.Text("Udah diabsen hari ini.", size=12, color=theme.SUCCESS),
                    ],
                    spacing=6,
                )
            )

        missed = missed_streak(storage.get_medication())
        if missed:
            children.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.INFO_OUTLINE, color=theme.WARN, size=16),
                        ft.Text(
                            f"{missed} hari terakhir belum keabsen — KALEM nganggapnya "
                            "belum diminum, jadi ekspektasi hari ini diturunin dikit. "
                            "Kalau ternyata udah diminum, stok di atas boleh dibenerin.",
                            size=11.5,
                            color=theme.MUTED,
                            expand=True,
                        ),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                )
            )

        children.append(
            ui_helpers.wide_button(
                "Cari Apotek Terdekat", show_pharmacies, icon=ft.Icons.LOCATION_ON
            )
        )
        status_holder.content = ft.Column(children, spacing=10)
        status_holder.visible = True

    def show_pharmacies(e):
        rows: list[ft.Control] = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.MAP, color=theme.PRIMARY, size=20),
                        ft.Column(
                            [
                                ft.Text("Cari di Google Maps",
                                        size=13, weight=ft.FontWeight.BOLD,
                                        color=theme.ON_BACKGROUND),
                                ft.Text("Pakai lokasi kamu saat ini", size=11, color=theme.MUTED),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.OPEN_IN_NEW, color=theme.MUTED, size=16),
                    ],
                    spacing=10,
                ),
                padding=ft.Padding.symmetric(vertical=12, horizontal=12),
                bgcolor=theme.BACKGROUND,
                border_radius=12,
                url=maps_search_url("apotek terdekat"),
                ink=True,
            ),
            ft.Divider(color=theme.BORDER, height=1),
            ui_helpers.section_header("TEBUS ONLINE"),
        ]
        rows += [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.SHOPPING_BAG, color=theme.SECONDARY, size=18),
                        ft.Column(
                            [
                                ft.Text(p["name"], size=13, weight=ft.FontWeight.BOLD,
                                        color=theme.ON_BACKGROUND),
                                ft.Text(p["desc"], size=11, color=theme.MUTED),
                            ],
                            spacing=0,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.OPEN_IN_NEW, color=theme.MUTED, size=16),
                    ],
                    spacing=10,
                ),
                padding=ft.Padding.symmetric(vertical=8, horizontal=10),
                bgcolor=theme.BACKGROUND,
                border_radius=12,
                url=p["url"],
                ink=True,
            )
            for p in ONLINE_PHARMACY_PARTNERS
        ]
        pharmacy_holder.controls = rows
        pharmacy_holder.visible = True
        page.update()

    def save(e):
        name = (name_field.value or "").strip()
        try:
            pills_left = int(float(stock_field.value or 0))
            per_day = float(dose_field.value or 1)
        except ValueError:
            stock_field.error = "Masukin angka ya"
            page.update()
            return
        stock_field.error = None

        if not name:
            name_field.error = "Isi nama obatnya dulu"
            page.update()
            return
        name_field.error = None

        if pills_left <= 0 or per_day <= 0:
            stock_field.error = "Stok dan dosis harus lebih dari 0"
            page.update()
            return

        storage.set_medication(name, pills_left, per_day)
        found = bpom.lookup(name)
        if found.found:
            storage.set_medication_registry(
                {"nama_resmi": found.name, "nie": found.nie,
                 "golongan": found.golongan, "cocok": found.matched_by}
            )
        refresh_cards()
        page.update()

    def turn_off(e):
        storage.disable_medication()
        status_holder.visible = False
        pharmacy_holder.visible = False
        refresh_cards()
        page.update()

    def refresh_cards():
        render_status()
        adherence_holder.content = _adherence_card(check_status(storage.get_medication()))

    adherence_holder = ft.Container()
    refresh_cards()
    check_name()

    actions: list[ft.Control] = [
        ui_helpers.primary_button("Simpan", save, icon=ft.Icons.SAVE, expand=True)
    ]
    if status.active:
        actions.append(ft.TextButton(content=ft.Text("Matikan"), on_click=turn_off))

    kalem_note = ft.Row(
        [
            buddy.face("tenang", 54),
            ft.Container(
                content=buddy.speech_bubble(
                    "Biar kamu nggak perlu repot mikirin sisa stok obat lagi."
                ),
                expand=True,
            ),
        ],
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    return ft.Column(
        [
            ui_helpers.page_header(
                "Pengingat Obat",
                on_back=lambda e: navigate(back_route),
                leading=ui_helpers.med_icon(26, theme.TERTIARY),
            ),
            kalem_note,
            ui_helpers.card(
                ft.Column([name_field, bpom_holder, stock_field, dose_field,
                          ft.Row(actions, spacing=8)], spacing=12)
            ),
            status_holder,
            pharmacy_holder,
            adherence_holder,
            ui_helpers.disclaimer(
                "Fitur ini bukan alat medis atau pengganti dokter. KALEM tidak menyarankan "
                "dosis dan semua angka menyesuaikan resep dokter kamu"
            ),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


def _note_row(icon: str, color: str, text: str) -> ft.Control:
    return ft.Row(
        [
            ft.Icon(icon, size=15, color=color),
            ft.Text(text, size=11.5, color=theme.MUTED, expand=True),
        ],
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def _adherence_card(status) -> ft.Control:
    if not status.active:
        return ft.Container()

    if not storage.is_premium():
        return ui_helpers.card(
            ft.Column(
                [
                    ui_helpers.section_header("Riwayat kepatuhan"),
                    ui_helpers.upgrade_hint(
                        "Fitur Freemium: Lihat persentase rutin, pola hari yang terlewat, "
                        "dan ringkasan siap pakai untuk tunjukkan ke dokter saat kontrol."
                    ),
                ],
                spacing=8,
            ),
            padding=14,
        )

    med = storage.get_medication() or {}
    log = med.get("take_log", [])
    from datetime import date, timedelta

    today = clock.today()
    try:
        start = date.fromisoformat(med.get("start_date", ""))
        age = (today - start).days + 1
    except (TypeError, ValueError):
        age = 30
    window = max(1, min(30, age))
    days = [today - timedelta(days=i) for i in range(window)]
    taken = set(log)
    hits = sum(1 for d in days if d.isoformat() in taken)
    pct = round(hits / window * 100)

    streak = 0
    for d in days:
        if d.isoformat() in taken:
            streak += 1
        else:
            break

    dots = ft.Row(
        [
            ft.Container(
                width=8,
                height=8,
                border_radius=4,
                bgcolor=theme.PRIMARY if d.isoformat() in taken else theme.BORDER,
            )
            for d in reversed(days)
        ],
        spacing=2,
        wrap=True,
        run_spacing=3,
    )

    return ui_helpers.card(
        ft.Column(
            [
                ft.Row(
                    [
                        ui_helpers.section_header("Riwayat kepatuhan"),
                        ft.Container(expand=True),
                        ft.Icon(ft.Icons.WORKSPACE_PREMIUM, size=14, color=theme.TERTIARY),
                    ],
                ),
                ft.Text(
                    f"{pct}% kamu absen ({hits} dari {window} hari"
                    + (" sejak dicatat)." if window < 30 else " terakhir)."),
                    size=13,
                    weight=ft.FontWeight.BOLD,
                    color=theme.ON_BACKGROUND,
                ),
                ft.Text(
                    f"Lagi {streak} hari berturut-turut." if streak
                    else "Belum absen hari ini.",
                    size=11.5,
                    color=theme.MUTED,
                ),
                dots,
                ft.Text(
                    "Angka ini cuma seakurat absen kamu — bukan rekam medis. "
                    "Kalau mau ditunjukin ke dokter, sampaikan juga hari-hari "
                    "yang lupa diabsen.",
                    size=10.5,
                    color=theme.MUTED,
                ),
            ],
            spacing=8,
        ),
        padding=14,
    )
