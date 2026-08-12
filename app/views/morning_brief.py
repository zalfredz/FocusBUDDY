"""Halaman ringkasan kondisi dan target harian."""
from __future__ import annotations

import flet as ft

from app import storage, ui_helpers
from app.core import kalem_engine

BACKGROUND = "#141416"
TEXT_PRIMARY = "#FFFFFF"
TYPEBOX_BG = "#484863"
BUTTON_BG = "#DDE0FF"
BUTTON_TEXT = "#484863"
FONT = "Plus Jakarta Sans"


def build(page: ft.Page, navigate) -> ft.Control:
    profile, day = kalem_engine.snapshot()
    brief = kalem_engine.build_morning_brief(profile, day)
    plan_text = ft.Text(
        brief.plan,
        size=13.5,
        color=TEXT_PRIMARY,
        font_family=FONT,
        weight=ft.FontWeight.W_400,
        text_align=ft.TextAlign.CENTER,
    )

    def dismiss(route: str):
        storage.set_last_brief_date()
        navigate(route)

    def accept(e):
        storage.set_today_energy(brief.energy_level)
        dismiss("home")

    def override(e):
        dismiss("mood")

    name = str(profile.get("name") or "Teman")
    before_name, separator, after_name = brief.greeting.partition(name)
    greeting = ft.Text(
        spans=(
            [
                ft.TextSpan(
                    before_name,
                    style=ft.TextStyle(
                        color=TEXT_PRIMARY,
                        font_family=FONT,
                        size=26,
                        weight=ft.FontWeight.W_400,
                    ),
                ),
                ft.TextSpan(
                    name,
                    style=ft.TextStyle(
                        color="#95D899",
                        font_family=FONT,
                        size=26,
                        weight=ft.FontWeight.W_700,
                    ),
                ),
                ft.TextSpan(
                    after_name,
                    style=ft.TextStyle(
                        color=TEXT_PRIMARY,
                        font_family=FONT,
                        size=26,
                        weight=ft.FontWeight.W_400,
                    ),
                ),
            ]
            if separator
            else [
                ft.TextSpan(
                    brief.greeting,
                    style=ft.TextStyle(
                        color=TEXT_PRIMARY,
                        font_family=FONT,
                        size=26,
                        weight=ft.FontWeight.W_700,
                    ),
                )
            ]
        ),
        text_align=ft.TextAlign.CENTER,
        font_family=FONT,
    )

    content_items: list[ft.Control] = [
        greeting,
        ft.Text(
            brief.forecast,
            size=14,
            color=TEXT_PRIMARY,
            font_family=FONT,
            text_align=ft.TextAlign.CENTER,
        ),
    ]

    if brief.reasons:
        content_items.append(
            ft.Container(
                bgcolor=TYPEBOX_BG,
                border_radius=14,
                padding=14,
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    [
                        ft.Text(
                            "Kenapa KALEM mikir gitu",
                            size=12,
                            weight=ft.FontWeight.W_700,
                            color=TEXT_PRIMARY,
                            font_family=FONT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        *[
                            ft.Text(
                                reason,
                                size=12,
                                color=TEXT_PRIMARY,
                                font_family=FONT,
                                text_align=ft.TextAlign.CENTER,
                            )
                            for reason in brief.reasons
                        ],
                    ],
                    spacing=7,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        )

    content_items.append(plan_text)

    if brief.long_pattern:
        content_items.append(
            ft.Container(
                bgcolor=TYPEBOX_BG,
                border_radius=14,
                padding=14,
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    [
                        ft.Text(
                            "Pola beberapa minggu terakhir",
                            size=11,
                            weight=ft.FontWeight.W_700,
                            color=TEXT_PRIMARY,
                            font_family=FONT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            brief.long_pattern,
                            size=12.5,
                            color=TEXT_PRIMARY,
                            font_family=FONT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        )
    elif brief.ready and not storage.is_premium():
        content_items.append(
            ft.Container(
                bgcolor=TYPEBOX_BG,
                border_radius=14,
                padding=14,
                alignment=ft.Alignment.CENTER,
                content=ft.Text(
                    "Premium: KALEM nyambungin pola berminggu-minggu, "
                    "bukan cuma hari ini.",
                    size=12,
                    color=TEXT_PRIMARY,
                    font_family=FONT,
                    text_align=ft.TextAlign.CENTER,
                ),
            )
        )

    if brief.task_count:
        content_items.append(
            ft.Text(
                f"Ada {brief.task_count} tugas hari ini.",
                size=11.5,
                color=TEXT_PRIMARY,
                font_family=FONT,
                text_align=ft.TextAlign.CENTER,
            )
        )

    if brief.encouragement and (brief.energy_level <= 2 or brief.burnout_risk):
        content_items.append(
            ft.Text(
                f'"{brief.encouragement}"',
                size=13,
                italic=True,
                color=TEXT_PRIMARY,
                font_family=FONT,
                text_align=ft.TextAlign.CENTER,
            )
        )

    accept_label = "Sesuai, mulai hari ini" if brief.ready else "Oke, mulai aja"
    content_items.extend(
        [
            ui_helpers.primary_button(
                accept_label,
                accept,
                icon=ft.Icons.CHECK,
                expand=True,
            ),
            ft.TextButton(
                content=ft.Text(
                    "Aku ngerasa beda",
                    size=12.5,
                    color=TEXT_PRIMARY,
                    font_family=FONT,
                ),
                on_click=override,
            ),
            ft.Text(
                "Ramalan ini dari pola catatan kamu sendiri, bukan diagnosis. "
                "Kalau kamu ngerasa beda, kamu yang bener -- bukan modelnya.",
                size=10.5,
                color=TEXT_PRIMARY,
                font_family=FONT,
                text_align=ft.TextAlign.CENTER,
            ),
        ]
    )

    foreground = ft.Container(
        padding=ft.Padding(left=24, top=36, right=24, bottom=36),
        content=ft.Column(
            [
                ft.ResponsiveRow(
                    [
                        ft.Container(
                            col={"xs": 12, "sm": 10, "md": 7, "lg": 4.5, "xl": 3.4},
                            content=ft.Column(
                                content_items,
                                spacing=18,
                                tight=True,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        )
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=0,
                ),
            ],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        ),
    )

    return ft.Stack(
        [
            ft.Container(
                bgcolor=BACKGROUND,
                alignment=ft.Alignment.CENTER,
                content=ft.Image(
                    src="Property 1=med_mood.png",
                    width=520,
                    height=620,
                    fit=ft.BoxFit.CONTAIN,
                    opacity=0.55,
                ),
            ),
            ft.Container(bgcolor="#66141416", blur=8),
            foreground,
        ],
        fit=ft.StackFit.EXPAND,
        expand=True,
    )
