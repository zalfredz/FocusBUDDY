"""Halaman diary harian."""
from __future__ import annotations

import flet as ft

from app import buddy, storage, theme, ui_helpers
from app.core.mood_model import extract_keywords, extract_tags
from app.voice_diary import VoiceDiary


def build(page: ft.Page, navigate) -> ft.Control:
    today_log = storage.today_mood()
    mood = today_log["mood"] if today_log else buddy.DEFAULT_MOOD

    story_field = ft.TextField(
        value="",
        hint_text="Tulis sebisanya. Nggak harus rapi dan panjang.",
        multiline=True,
        min_lines=6,
        max_lines=9,
        bgcolor=theme.SURFACE,
        border_color=theme.BORDER,
        focused_border_color=theme.PRIMARY,
        color=theme.ON_BACKGROUND,
        hint_style=ft.TextStyle(color=theme.MUTED, size=12),
    )
    saved_note = ft.Text("", size=12, color=theme.PRIMARY)
    entries_column = ft.Column(spacing=10)
    save_button = ui_helpers.primary_button(
        "Kirim ke KALEM", None, icon=ft.Icons.SEND, expand=True
    )

    def set_voice_busy(busy: bool) -> None:
        save_button.disabled = busy

    voice = VoiceDiary(page, story_field, set_voice_busy)
    voice_status = voice.embed_in_field()
    story_field.on_change = lambda e: voice.sync_with_text()
    setattr(page, "_focusbuddy_view_cleanup", voice.cleanup)

    def render_entries() -> None:
        entries = storage.diary_entries()
        if not entries:
            entries_column.controls = [
                ui_helpers.empty_state(
                    "Belum ada cerita tersimpan.", ft.Icons.MENU_BOOK
                )
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
                                        src=buddy.asset_for(
                                            entry.get("mood", buddy.DEFAULT_MOOD)
                                        ),
                                        width=26,
                                        height=26,
                                        fit=ft.BoxFit.CONTAIN,
                                    ),
                                    ft.Text(
                                        entry["date"],
                                        size=11,
                                        color=theme.MUTED,
                                        expand=True,
                                    ),
                                ],
                                spacing=8,
                            ),
                            ft.Text(
                                entry["diary"],
                                size=12.5,
                                color=theme.ON_BACKGROUND,
                            ),
                            (
                                ft.Row(tag_chips, spacing=6, wrap=True)
                                if tag_chips
                                else ft.Container()
                            ),
                        ],
                        spacing=8,
                    ),
                    padding=14,
                )
            )
        entries_column.controls = items

    def save_story(e) -> None:
        text = (story_field.value or "").strip()
        if not text:
            story_field.error = "Ceritanya masih kosong"
            page.update()
            return
        story_field.error = None

        current = storage.today_mood()
        current_mood = current["mood"] if current else mood
        keywords = extract_keywords(text)
        tags = keywords + [tag for tag in extract_tags(text) if tag not in keywords]
        storage.add_diary_entry(text, mood=current_mood, tags=tags[:6])
        story_field.value = ""
        saved_note.value = "Tersimpan. Makasih udah cerita 🤍"
        render_entries()
        page.update()

    save_button.on_click = save_story
    render_entries()

    return ft.Column(
        [
            ui_helpers.page_header("Cerita yuk", on_back=lambda e: navigate("mood")),
            ft.Column(
                [
                    story_field,
                    voice_status,
                    ft.Row(
                        [
                            buddy.face(mood, 52),
                            ft.Container(
                                content=save_button,
                                expand=True,
                            ),
                        ],
                        spacing=0,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    saved_note,
                ],
                spacing=6,
            ),
            ui_helpers.title("Cerita Sebelumnya", 15),
            entries_column,
            ui_helpers.disclaimer(
                "Teks cerita tersimpan di ruang akun kamu. Kalau pakai suara, rekaman "
                "diproses sementara untuk membuat transkrip dan tidak disimpan oleh "
                "FocusBuddy."
            ),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
