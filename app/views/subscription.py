"""Halaman langganan dan aktivasi Premium khusus demo."""
from __future__ import annotations

import flet as ft

from app import config, storage, theme, ui_helpers


_PREMIUM_BENEFITS = (
    (
        ft.Icons.ACCOUNT_TREE_OUTLINED,
        "Pecah tugas lebih leluasa",
        "Susun langkah kecil lebih sering saat tugas terasa berat untuk dimulai.",
    ),
    (
        ft.Icons.AUTO_AWESOME_OUTLINED,
        "Rekomendasi KALEM lebih lengkap",
        "Dapatkan lebih banyak opsi tindakan yang menyesuaikan kondisi harianmu.",
    ),
    (
        ft.Icons.INSIGHTS_OUTLINED,
        "Insight mood dan pola jangka panjang",
        "Buka seluruh temuan, riwayat bulan sebelumnya, dan pola beberapa minggu.",
    ),
    (
        ft.Icons.MEDICATION_OUTLINED,
        "Ringkasan rutinitas obat",
        "Lihat persentase rutin, pola yang terlewat, dan ringkasan untuk kontrol.",
    ),
)


def _benefit(icon: str, title: str, description: str) -> ft.Control:
    return ft.Row(
        [
            ft.Container(
                content=ft.Icon(icon, color=theme.PRIMARY, size=20),
                width=40,
                height=40,
                alignment=ft.Alignment.CENTER,
                bgcolor=ft.Colors.with_opacity(0.14, theme.PRIMARY),
                border_radius=12,
            ),
            ft.Column(
                [
                    ft.Text(
                        title,
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=theme.ON_BACKGROUND,
                    ),
                    ft.Text(description, size=11.5, color=theme.MUTED),
                ],
                spacing=2,
                expand=True,
            ),
        ],
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def build(page: ft.Page, navigate) -> ft.Control:
    premium = storage.is_premium()

    def toggle_demo(e) -> None:
        storage.set_premium(not storage.is_premium())
        navigate("subscription")

    status = ft.Container(
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE if premium else ft.Icons.LOCK_OPEN_OUTLINED,
                    color=theme.SUCCESS if premium else theme.MUTED,
                    size=18,
                ),
                ft.Text(
                    "Premium demo sedang aktif" if premium else "Kamu sedang memakai paket Free",
                    size=12,
                    weight=ft.FontWeight.BOLD,
                    color=theme.ON_BACKGROUND,
                    expand=True,
                ),
            ],
            spacing=8,
        ),
        bgcolor=theme.BACKGROUND,
        border=ft.Border.all(1, theme.SUCCESS if premium else theme.BORDER),
        border_radius=12,
        padding=ft.Padding.symmetric(vertical=10, horizontal=12),
    )

    demo_controls: list[ft.Control] = []
    if config.DEMO_MODE:
        demo_controls = [
            ui_helpers.card(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.SCIENCE_OUTLINED, color=theme.TERTIARY, size=18),
                                ft.Text(
                                    "MODE DEMO",
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color=theme.TERTIARY,
                                ),
                            ],
                            spacing=7,
                        ),
                        ft.Text(
                            "Tombol ini hanya menyimulasikan langganan untuk presentasi. "
                            "Tidak ada pembayaran atau transaksi yang diproses.",
                            size=11.5,
                            color=theme.MUTED,
                        ),
                        ft.Row(
                            [
                                ft.ElevatedButton(
                                    content=ft.Text(
                                        "Subs Off - Untuk DEMO"
                                        if premium
                                        else "Subs On - Untuk DEMO",
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    icon=(
                                        ft.Icons.TOGGLE_OFF_OUTLINED
                                        if premium
                                        else ft.Icons.TOGGLE_ON_OUTLINED
                                    ),
                                    bgcolor=theme.TERTIARY if not premium else theme.SURFACE,
                                    color=theme.ON_BACKGROUND,
                                    on_click=toggle_demo,
                                    elevation=0,
                                )
                            ]
                        ),
                    ],
                    spacing=10,
                ),
                padding=16,
            )
        ]

    return ft.Column(
        [
            ui_helpers.page_header("Langganan KALEM", lambda e: navigate("home")),
            ui_helpers.card(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.WORKSPACE_PREMIUM,
                                    color=theme.TERTIARY,
                                    size=28,
                                ),
                                ft.Column(
                                    [
                                        ft.Text(
                                            "KALEM Premium",
                                            size=19,
                                            weight=ft.FontWeight.BOLD,
                                            color=theme.ON_BACKGROUND,
                                            font_family=theme.FONT_DISPLAY,
                                        ),
                                        ft.Text(
                                            "Dukungan yang lebih lengkap untuk membaca ritme harianmu.",
                                            size=11.5,
                                            color=theme.MUTED,
                                        ),
                                    ],
                                    spacing=1,
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                        ),
                        status,
                        ft.Text(
                            "Langganan publik belum dibuka. Kamu tetap bisa melihat "
                            "pengalaman Premium melalui mode demo di bawah.",
                            size=11.5,
                            color=theme.MUTED,
                        ),
                    ],
                    spacing=12,
                )
            ),
            ui_helpers.card(
                ft.Column(
                    [
                        ui_helpers.section_header("Yang terbuka di Premium"),
                        *(_benefit(*benefit) for benefit in _PREMIUM_BENEFITS),
                    ],
                    spacing=14,
                ),
                padding=16,
            ),
            *demo_controls,
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
