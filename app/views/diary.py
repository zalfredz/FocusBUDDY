"""Halaman diary harian."""
from __future__ import annotations

import flet as ft

from app import buddy, clock, storage, theme, ui_helpers
from app.core.mood_model import extract_keywords, extract_tags, recurring_tag_prompt

PROMPTS = [
    "Apa satu hal yang paling nempel di kepala kamu hari ini?",
    "Ada yang bikin kamu lega hari ini?",
    "Hal apa yang paling nguras energi kamu hari ini?",
    "Kalau boleh ngulang satu bagian hari ini, bagian mana?",
]


def build(page: ft.Page, navigate) -> ft.Control:
    latest = storage.latest_mood()
    mood = latest["mood"] if latest else buddy.DEFAULT_MOOD
    today_iso = clock.today().isoformat()
    existing_today = latest["diary"] if latest and latest["date"] == today_iso else ""

    prompt = recurring_tag_prompt(storage.get_mood_logs()) or PROMPTS[
        clock.today().toordinal() % len(PROMPTS)
    ]

    story_field = ft.TextField(
        value=existing_today,
        hint_text="Tulis sebisanya. Nggak harus rapi, nggak harus panjang.",
        multiline=True,
        min_lines=5,
        max_lines=10,
        border_color=theme.BORDER,
        focused_border_color=theme.PRIMARY,
    )
    saved_note = ft.Text("", size=12, color=theme.PRIMARY)
    entries_column = ft.Column(spacing=10)

    def render_entries():
        entries = storage.diary_entries()
        if not entries:
            entries_column.controls = [
                ui_helpers.empty_state("Belum ada cerita tersimpan.", ft.Icons.MENU_BOOK)
            ]
            return
        items: list[ft.Control] = []
        for entry in entries[:10]:
            tag_chips = [
                ft.Container(
                    content=ft.Text(tag, size=10, color=theme.ON_BACKGROUND),
                    bgcolor=theme.BACKGROUND,
                    border_radius=8,
                    padding=ft.Padding.symmetric(vertical=3, horizontal=8),
                )
                for tag in (entry.get("tags") or [])[:4]
            ]
            items.append(
                ui_helpers.card(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Image(
                                        src=buddy.asset_for(entry.get("mood", buddy.DEFAULT_MOOD)),
                                        width=26,
                                        height=26,
                                        fit=ft.BoxFit.CONTAIN,
                                    ),
                                    ft.Text(entry["date"], size=11, color=theme.MUTED, expand=True),
                                ],
                                spacing=8,
                            ),
                            ft.Text(entry["diary"], size=12.5, color=theme.ON_BACKGROUND),
                            ft.Row(tag_chips, spacing=6, wrap=True) if tag_chips else ft.Container(),
                        ],
                        spacing=8,
                    ),
                    padding=14,
                )
            )
        entries_column.controls = items

    def save_story(e):
        text = (story_field.value or "").strip()
        if not text:
            story_field.error = "Ceritanya masih kosong"
            page.update()
            return
        story_field.error = None

        current = storage.today_mood()
        current_mood = current["mood"] if current else mood
        tags = extract_keywords(text) + [
            t for t in extract_tags(text) if t not in extract_keywords(text)
        ]
        storage.add_mood_log(
            mood=current_mood,
            score=buddy.score_for(current_mood),
            energy=current.get("energy", 3) if current else 3,
            diary=text,
            tags=tags[:6],
            quick_tags=current.get("quick_tags", []) if current else [],
            ate_today=current.get("ate_today") if current else None,
            rested_enough=current.get("rested_enough") if current else None,
        )
        saved_note.value = "Tersimpan. Makasih udah cerita 🤍"
        render_entries()
        page.update()

    render_entries()

    return ft.Column(
        [
            ui_helpers.page_header("Cerita Kamu", on_back=lambda e: navigate("mood")),
            ui_helpers.card(
                ft.Column(
                    [
                        ft.Row(
                            [
                                buddy.face(mood, 64),
                                ft.Container(
                                    content=buddy.speech_bubble(prompt),
                                    expand=True,
                                ),
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        story_field,
                        ui_helpers.wide_button("Kirim ke Kalem", save_story, icon=ft.Icons.SEND),
                        saved_note,
                    ],
                    spacing=12,
                )
            ),
            ui_helpers.section_header("Cerita sebelumnya"),
            entries_column,
            ui_helpers.disclaimer(
                "Cerita kamu disimpan lokal di perangkat ini aja (~/.focusbuddy/data.json), "
                "nggak dikirim ke server mana pun."
            ),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
