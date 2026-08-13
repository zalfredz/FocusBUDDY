"""Halaman Insight pagi KALEM."""
from __future__ import annotations

import flet as ft

from app import buddy, storage, theme
from app.core import kalem_engine

BACKGROUND = "#141416"
TEXT = "#FFFFFF"
PRIMARY = "#DDE0FF"
INK = "#181A35"
FONT = "Plus Jakarta Sans"
CONTENT_WIDTH = 340
MIN_INSIGHT_LOGS = 5


def prediction_copy(energy_level: int, burnout_risk: bool = False) -> str:
    if burnout_risk or energy_level <= 2:
        return "SEMANGAT!! Hari ini mungkin berat"
    if energy_level >= 5:
        return "Semangat kamu FULL hari ini"
    return "Kemungkinan biasa aja"


def build(page: ft.Page, navigate) -> ft.Control:
    profile, day = kalem_engine.snapshot()
    brief = kalem_engine.build_morning_brief(profile, day)
    name = str(profile.get("name") or "Teman")
    log_count = min(len(day.mood_logs), MIN_INSIGHT_LOGS)
    progress = log_count / MIN_INSIGHT_LOGS

    def dismiss(route: str) -> None:
        storage.set_last_brief_date()
        navigate(route)

    def accept(event) -> None:
        storage.set_today_energy(brief.energy_level)
        dismiss("home")

    def override(event) -> None:
        dismiss("mood")

    greeting = ft.Text(
        spans=[
            ft.TextSpan(
                f"Hai {name}!\nAku ",
                style=ft.TextStyle(
                    color=TEXT,
                    size=29,
                    height=1.22,
                    weight=ft.FontWeight.W_500,
                    font_family=FONT,
                ),
            ),
            ft.TextSpan(
                "Kalem!",
                style=ft.TextStyle(
                    color="#95D899",
                    size=29,
                    height=1.22,
                    weight=ft.FontWeight.W_800,
                    font_family=FONT,
                ),
            ),
        ],
        width=CONTENT_WIDTH,
        text_align=ft.TextAlign.LEFT,
    )

    def mascot_row(mood: str, bubble_text: str) -> ft.Control:
        return ft.Row(
            [
                buddy.face(mood, 104),
                ft.Container(
                    content=ft.Text(
                        bubble_text,
                        size=10.5,
                        color=TEXT,
                        font_family=FONT,
                    ),
                    expand=True,
                    bgcolor="#26342F",
                    border=ft.Border.all(1, "#708B82"),
                    border_radius=10,
                    padding=ft.Padding.symmetric(vertical=10, horizontal=11),
                    shadow=ft.BoxShadow(blur_radius=18, color="#443FA66B"),
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    progress_card = ft.Container(
        width=CONTENT_WIDTH,
        bgcolor="#1C1C26",
        border=ft.Border.all(1, "#484863"),
        border_radius=20,
        padding=ft.Padding.symmetric(vertical=13, horizontal=14),
        content=ft.Column(
            [
                ft.Text(
                    "Progress catatan Kalem",
                    size=12.5,
                    color=TEXT,
                    font_family=FONT,
                ),
                ft.Row(
                    [
                        ft.ProgressBar(
                            value=progress,
                            color="#95ABFF",
                            bgcolor="#111115",
                            bar_height=14,
                            border_radius=8,
                            expand=True,
                        ),
                        ft.Text(
                            f"{round(progress * 100)}%",
                            size=13,
                            weight=ft.FontWeight.W_700,
                            color="#95ABFF",
                            font_family=FONT,
                        ),
                    ],
                    spacing=12,
                ),
            ],
            spacing=8,
        ),
    )

    primary_button = ft.Button(
        width=CONTENT_WIDTH,
        height=48,
        content=ft.Text(
            "Oke, Mulai Aja",
            size=15,
            weight=ft.FontWeight.W_800,
            color=INK,
            font_family=FONT,
        ),
        style=ft.ButtonStyle(
            bgcolor=PRIMARY,
            shape=ft.RoundedRectangleBorder(radius=100),
        ),
        on_click=accept,
    )
    override_button = ft.OutlinedButton(
        width=CONTENT_WIDTH,
        height=48,
        content=ft.Text(
            "Aku ngerasa beda",
            size=14,
            weight=ft.FontWeight.W_700,
            color=PRIMARY,
            font_family=FONT,
        ),
        style=ft.ButtonStyle(
            side=ft.BorderSide(1, PRIMARY),
            shape=ft.RoundedRectangleBorder(radius=100),
        ),
        on_click=override,
    )

    if brief.ready:
        reason = brief.reasons[0] if brief.reasons else "catatan harian kamu mulai membentuk pola"
        focus_label = f"{brief.focus_minutes} menit"
        before_focus, separator, after_focus = brief.plan.partition(focus_label)
        plan_spans = [ft.TextSpan(before_focus)]
        if separator:
            plan_spans.extend(
                [
                    ft.TextSpan(
                        focus_label,
                        style=ft.TextStyle(weight=ft.FontWeight.W_800),
                    ),
                    ft.TextSpan(after_focus),
                ]
            )
        pattern_text = (
            brief.long_pattern
            or "KALEM nyambungin pola berminggu-minggu, bukan cuma hari ini"
        )
        insight_content: list[ft.Control] = [
            greeting,
            ft.Text(
                spans=[
                    ft.TextSpan(
                        "Ramalan hari ini:\n",
                        style=ft.TextStyle(size=15, color=TEXT, font_family=FONT),
                    ),
                    ft.TextSpan(
                        prediction_copy(brief.energy_level, brief.burnout_risk),
                        style=ft.TextStyle(
                            size=19,
                            color=TEXT,
                            weight=ft.FontWeight.W_800,
                            font_family=FONT,
                        ),
                    ),
                ],
                width=CONTENT_WIDTH,
            ),
            mascot_row(
                brief.mood,
                f"Aku mikir begitu karena {reason}",
            ),
            ft.Text(
                spans=plan_spans,
                width=CONTENT_WIDTH,
                size=15,
                color=TEXT,
                font_family=FONT,
            ),
            ft.Container(
                width=CONTENT_WIDTH,
                border=ft.Border.all(2, "#F1C98F"),
                border_radius=18,
                padding=ft.Padding.symmetric(vertical=13, horizontal=14),
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.WORKSPACE_PREMIUM,
                            size=25,
                            color="#F1C98F",
                        ),
                        ft.Text(
                            pattern_text,
                            size=12.5,
                            color="#F1C98F",
                            font_family=FONT,
                            weight=ft.FontWeight.W_600,
                            expand=True,
                        ),
                    ],
                    spacing=11,
                ),
            ),
        ]
    else:
        insight_content = [
            greeting,
            ft.Text(
                "Aku belum ada cukup data buat meramal hari kamu.",
                width=CONTENT_WIDTH,
                size=13,
                color=TEXT,
                font_family=FONT,
            ),
            mascot_row(
                "semangat",
                "Yuk cerita dikit sama aku biar aku lebih kenal sama kamu dan "
                "pengalamanmu jadi lebih terpersonalisasi",
            ),
            progress_card,
        ]

    return ft.Container(
        expand=True,
        bgcolor=BACKGROUND,
        padding=ft.Padding(left=24, top=30, right=24, bottom=28),
        content=ft.Column(
            [
                *insight_content,
                primary_button,
                override_button,
                ft.Text(
                    "Ramalan ini dari pola catatan kamu sendiri, bukan diagnosis. "
                    "Kalau kamu ngerasa beda, kamu yang benar, bukan modelnya.",
                    width=CONTENT_WIDTH,
                    size=10.5,
                    color=theme.MUTED,
                    font_family=FONT,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
