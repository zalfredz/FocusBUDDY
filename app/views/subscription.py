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

_DEMO_CARD_NUMBER = "4242424242424242"
_DEMO_GOPAY_NUMBER = "081200000000"
_DEMO_PRICE = "Rp29.000 / bulan"


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

    def deactivate_demo(e) -> None:
        storage.set_premium(False)
        navigate("subscription")

    def open_demo_checkout(e) -> None:
        payment_state = {"method": "card", "masked": ""}
        card_field = ft.TextField(
            label="Nomor kartu demo",
            hint_text="4242 4242 4242 4242",
            helper="Gunakan nomor dummy di atas. Jangan masukkan kartu asli.",
            keyboard_type=ft.KeyboardType.NUMBER,
            max_length=19,
            password=True,
            can_reveal_password=False,
            autofocus=True,
        )
        gopay_field = ft.TextField(
            label="Nomor GoPay demo",
            hint_text="0812 0000 0000",
            helper="Gunakan nomor dummy di atas. Tidak ada OTP yang dikirim.",
            keyboard_type=ft.KeyboardType.PHONE,
            max_length=15,
            visible=False,
        )
        consent = ft.Checkbox(
            label="Saya paham ini hanya simulasi dan tidak memproses pembayaran nyata.",
            value=False,
        )
        error = ft.Text("", size=10.5, color=theme.DANGER, visible=False)
        method = ft.RadioGroup(
            value="card",
            content=ft.Row(
                [
                    ft.Radio(value="card", label="Kartu"),
                    ft.Radio(value="gopay", label="GoPay"),
                ],
                spacing=4,
            ),
        )

        def digits(value: str) -> str:
            return "".join(character for character in value if character.isdigit())

        def change_method(ev) -> None:
            payment_state["method"] = method.value or "card"
            card_field.visible = payment_state["method"] == "card"
            gopay_field.visible = payment_state["method"] == "gopay"
            error.visible = False
            page.update()

        method.on_change = change_method

        def activate_demo(ev) -> None:
            page.pop_dialog()
            storage.set_premium(True)
            navigate("subscription")

        def show_confirmation(ev) -> None:
            selected_method = method.value or "card"
            number = digits(
                card_field.value if selected_method == "card" else gopay_field.value
            )
            expected = (
                _DEMO_CARD_NUMBER if selected_method == "card" else _DEMO_GOPAY_NUMBER
            )
            if number != expected:
                error.value = (
                    "Gunakan nomor kartu demo 4242 4242 4242 4242."
                    if selected_method == "card"
                    else "Gunakan nomor GoPay demo 0812 0000 0000."
                )
                error.visible = True
                page.update()
                return
            if not consent.value:
                error.value = "Centang persetujuan simulasi sebelum lanjut."
                error.visible = True
                page.update()
                return

            payment_state["masked"] = (
                "•••• •••• •••• 4242"
                if selected_method == "card"
                else "0812 •••• 0000"
            )
            page.pop_dialog()
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Konfirmasi pembayaran demo", size=17),
                    content=ft.Column(
                        [
                            ft.Container(
                                content=ft.Icon(
                                    ft.Icons.VERIFIED_OUTLINED,
                                    size=36,
                                    color=theme.TERTIARY,
                                ),
                                alignment=ft.Alignment.CENTER,
                            ),
                            ft.Text(
                                "Tidak ada transaksi nyata yang akan dilakukan.",
                                size=11.5,
                                color=theme.MUTED,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Divider(color=theme.BORDER, height=1),
                            ft.Row(
                                [
                                    ft.Text("Paket", size=11.5, color=theme.MUTED),
                                    ft.Text(
                                        "KALEM Premium",
                                        size=11.5,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.Row(
                                [
                                    ft.Text("Metode", size=11.5, color=theme.MUTED),
                                    ft.Text(
                                        "Kartu" if selected_method == "card" else "GoPay",
                                        size=11.5,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.Row(
                                [
                                    ft.Text("Akun", size=11.5, color=theme.MUTED),
                                    ft.Text(
                                        payment_state["masked"],
                                        size=11.5,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.Row(
                                [
                                    ft.Text("Total", size=11.5, color=theme.MUTED),
                                    ft.Text(
                                        _DEMO_PRICE,
                                        size=12,
                                        weight=ft.FontWeight.BOLD,
                                        color=theme.PRIMARY,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                        ],
                        spacing=10,
                        tight=True,
                    ),
                    actions=[
                        ft.TextButton(
                            content=ft.Text("Batal"),
                            on_click=lambda event: page.pop_dialog(),
                        ),
                        ui_helpers.primary_button(
                            "Konfirmasi demo",
                            activate_demo,
                            icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                        ),
                    ],
                )
            )

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Checkout Premium — DEMO", size=17),
                content=ft.Column(
                    [
                        ui_helpers.banner(
                            "SIMULASI SAJA — jangan masukkan data pembayaran asli.",
                            theme.WARN,
                            ft.Icons.SCIENCE_OUTLINED,
                        ),
                        ft.Row(
                            [
                                ft.Text("KALEM Premium", size=13, weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    _DEMO_PRICE,
                                    size=12,
                                    weight=ft.FontWeight.BOLD,
                                    color=theme.PRIMARY,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Text("Metode pembayaran demo", size=11, color=theme.MUTED),
                        method,
                        card_field,
                        gopay_field,
                        consent,
                        error,
                    ],
                    spacing=8,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                actions=[
                    ft.TextButton(
                        content=ft.Text("Batal"),
                        on_click=lambda event: page.pop_dialog(),
                    ),
                    ui_helpers.primary_button(
                        "Lanjut konfirmasi",
                        show_confirmation,
                        icon=ft.Icons.ARROW_FORWARD,
                    ),
                ],
            )
        )

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
                            "Checkout ini hanya simulasi presentasi. Input pembayaran "
                            "tidak disimpan dan tidak ada transaksi yang diproses.",
                            size=11.5,
                            color=theme.MUTED,
                        ),
                        ft.Row(
                            [
                                ft.ElevatedButton(
                                    content=ft.Text(
                                        "Subs Off - Untuk DEMO"
                                        if premium
                                        else "Coba pembayaran demo",
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    icon=(
                                        ft.Icons.TOGGLE_OFF_OUTLINED
                                        if premium
                                        else ft.Icons.TOGGLE_ON_OUTLINED
                                    ),
                                    bgcolor=theme.TERTIARY if not premium else theme.SURFACE,
                                    color=theme.ON_BACKGROUND,
                                    on_click=deactivate_demo if premium else open_demo_checkout,
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
            ui_helpers.page_header("Langganan KALEM", lambda e: navigate("settings")),
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
