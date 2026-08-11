"""Placeholder untuk playground model KALEM pada mode demo."""
from __future__ import annotations

import flet as ft

from app import theme, ui_helpers


def build(page: ft.Page, navigate) -> ft.Control:
    return ft.Column(
        [
            ui_helpers.page_header("DEMO MODEL", lambda e: navigate("demo_tools")),
            ui_helpers.card(
                ft.Column(
                    [
                        ft.Icon(ft.Icons.MODEL_TRAINING, size=36, color=theme.TERTIARY),
                        ft.Text(
                            "Playground model akan dibuat di sini.",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=theme.ON_BACKGROUND,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            "Untuk sekarang halaman ini sengaja dikosongkan sampai UI "
                            "dan format input-output model ditentukan.",
                            size=11.5,
                            color=theme.MUTED,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    spacing=8,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=24,
            ),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
