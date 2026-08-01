"""Morning Brief -- Kalem nyapa duluan, sekali sehari, sebelum Home.

Ini yang ngebalik arah interaksi FocusBuddy: fitur lain nunggu user buka
app dan ngisi sesuatu dulu; halaman ini yang ngajak duluan. Hambatan ADHD
paling kritis ada di titik INISIASI (Delay Aversion Model), dan app yang
nunggu dibuka nggak nolongin di titik itu.

Halaman ini nggak ngitung apa-apa sendiri -- ramalannya dari
`kalem_engine.build_morning_brief()`, yang di baliknya manggil
`kalem_ml.model_mood` (skor mood hari ini) + `kalem_ml.model_energi`
(beban kerja & burnout). Yang beda dari halaman Mood: hasilnya dibungkus
jadi AKSI DEFAULT (nyetel energi + durasi sesi hari itu), bukan cuma
kalimat info.
"""
from __future__ import annotations

import flet as ft

from app import buddy, storage, theme, ui_helpers
from app.core import kalem_engine


def build(page: ft.Page, navigate) -> ft.Control:
    profile, day = kalem_engine.snapshot()
    brief = kalem_engine.build_morning_brief(profile, day)

    def dismiss(route: str):
        """Tandai brief hari ini udah tampil, lalu pindah halaman.

        Ditandai di SEMUA jalan keluar -- biar brief nggak nongol lagi
        tiap balik ke Home di hari yang sama.
        """
        storage.set_last_brief_date()
        navigate(route)

    def accept(e):
        # Inilah yang bikin ramalan jadi AKSI, bukan cuma kalimat: level
        # energi hari ini langsung dikunci, jadi durasi sesi fokus di
        # Tracker DAN di tombol FOKUS Home ikut nyesuain.
        storage.set_today_energy(brief.energy_level)
        dismiss("home")

    def override(e):
        # Nggak ngunci apa-apa -- user yang nentuin sendiri di Tracker.
        dismiss("tracker")

    # ------------------------------------------------------------ isi kartu

    card_children: list[ft.Control] = [
        buddy.face(brief.mood, 120),
        ft.Text(
            brief.greeting,
            size=20,
            weight=ft.FontWeight.BOLD,
            color=theme.ON_BACKGROUND,
            font_family=theme.FONT_DISPLAY,
            text_align=ft.TextAlign.CENTER,
        ),
        ft.Text(
            brief.forecast,
            size=14,
            color=theme.ON_BACKGROUND,
            text_align=ft.TextAlign.CENTER,
        ),
    ]

    # Alasan ramalan -- ditunjukkin biar nggak kerasa kotak hitam.
    if brief.reasons:
        card_children.append(
            ft.Container(
                content=ft.Column(
                    [
                        ui_helpers.section_header("Kenapa Kalem mikir gitu"),
                        *[
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.CIRCLE, size=5, color=theme.SECONDARY),
                                    ft.Text(reason, size=12, color=theme.MUTED, expand=True),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                            )
                            for reason in brief.reasons
                        ],
                    ],
                    spacing=6,
                ),
                bgcolor=theme.BACKGROUND,
                border_radius=12,
                padding=12,
            )
        )

    card_children.append(
        ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.AUTO_AWESOME, size=18, color=theme.PRIMARY),
                    ft.Text(brief.plan, size=13, color=theme.ON_BACKGROUND, expand=True),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=theme.BACKGROUND,
            border_radius=12,
            padding=12,
        )
    )

    # --- Premium: pola lintas minggu ---
    if brief.long_pattern:
        card_children.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.INSIGHTS, size=15, color=theme.TERTIARY),
                                ft.Text("Pola beberapa minggu terakhir", size=10.5,
                                        weight=ft.FontWeight.BOLD, color=theme.TERTIARY),
                            ],
                            spacing=6,
                        ),
                        ft.Text(brief.long_pattern, size=12.5, color=theme.ON_BACKGROUND),
                    ],
                    spacing=6,
                ),
                bgcolor=theme.BACKGROUND,
                border=ft.Border.all(1, theme.TERTIARY),
                border_radius=12,
                padding=12,
            )
        )
    elif brief.ready and not storage.is_premium():
        card_children.append(
            ui_helpers.upgrade_hint(
                "Premium: Kalem nyambungin pola berminggu-minggu, bukan cuma hari ini."
            )
        )

    if brief.task_count:
        card_children.append(
            ft.Text(
                f"Ada {brief.task_count} tugas hari ini.",
                size=11.5,
                color=theme.MUTED,
                text_align=ft.TextAlign.CENTER,
            )
        )

    # Kalimat penyemangat versi user sendiri, dikutip balik pas harinya berat.
    if brief.encouragement and (brief.energy_level <= 2 or brief.burnout_risk):
        card_children.append(
            ft.Text(
                f"“{brief.encouragement}”",
                size=13,
                italic=True,
                color=theme.ON_BACKGROUND,
                text_align=ft.TextAlign.CENTER,
            )
        )

    accept_label = "Sesuai, mulai hari ini" if brief.ready else "Oke, mulai aja"
    card_children.append(ui_helpers.wide_button(accept_label, accept, icon=ft.Icons.CHECK))
    card_children.append(
        ft.TextButton(
            content=ft.Text("Aku ngerasa beda", size=12.5, color=theme.MUTED),
            on_click=override,
        )
    )

    return ft.Column(
        [
            ft.Container(height=8),
            ui_helpers.card(
                ft.Column(
                    card_children,
                    spacing=14,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
            ),
            ui_helpers.disclaimer(
                "Ramalan ini dari pola catatan kamu sendiri, bukan diagnosis. "
                "Kalau kamu ngerasa beda, kamu yang bener -- bukan modelnya."
            ),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
