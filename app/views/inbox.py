"""Halaman inbox untuk menangkap tugas dengan cepat."""
from __future__ import annotations

from datetime import datetime

import flet as ft

from app import clock, storage, theme, ui_helpers
from app.core.decomposer_logic import plan_today


def _relative_time(iso: str) -> str:
    try:
        when = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    mins = int((clock.now() - when).total_seconds() // 60)
    if mins < 0:
        return "barusan"
    if mins < 1:
        return "barusan"
    if mins < 60:
        return f"{mins} menit lalu"
    hours = mins // 60
    if hours < 24:
        return f"{hours} jam lalu"
    return f"{hours // 24} hari lalu"


def build(page: ft.Page, navigate) -> ft.Control:
    body = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
    notes_column = ft.Column(spacing=10)

    def to_task(note: dict):
        title_field = ft.TextField(label="Jadiin tugas apa?", value=note["text"], multiline=True, max_lines=3)
        description_field = ft.TextField(
            label="Deskripsi (opsional)",
            hint_text="konteks lebih detail, kalau ada",
            multiline=True,
            min_lines=2,
            max_lines=5,
            helper="Diisi -> Pecah Tugas mecah dari SINI, bukan cuma judul",
        )
        time_field = ft.TextField(
            label="Jam deadline (opsional)",
            hint_text="mis. 17:00",
            helper="Dikosongin = sampai akhir hari",
        )
        important_check = ft.Checkbox(label="Penting (berdampak besar)", value=True)
        can_use_ai = storage.can_use("decompose")
        split_check = ft.Checkbox(
            label="Pecah otomatis jadi langkah kecil",
            value=True,
        )
        note_text = ft.Text(
            "" if can_use_ai else "Kuota penyusunan Kalem habis: tetap coba pola lokal; "
            "kalau nggak cocok, dipakai template sederhana.",
            size=11,
            color=theme.MUTED,
        )

        def submit(ev):
            name = (title_field.value or "").strip()
            if not name:
                title_field.error = "Isi dulu ya"
                page.update()
                return

            task = storage.add_task(
                name,
                clock.today().isoformat(),
                important_check.value,
                steps=[{"text": name, "done": False}],
                difficulty_est=2,
                deadline_time=(time_field.value or "").strip(),
                description=(description_field.value or "").strip(),
            )

            if split_check.value:
                energy = storage.today_energy() or 3
                result = plan_today([task], energy, allow_ai=can_use_ai)
                if result.n_ai:
                    storage.record_usage("decompose")
                steps = [
                    {"text": step, "done": False}
                    for title, step, _m in result.steps
                    if title == name
                ]
                if steps:
                    storage.set_task_steps(task["id"], steps)

            storage.delete_inbox_note(note["id"])
            page.pop_dialog()
            render_notes()
            page.update()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Rapikan jadi tugas", size=16),
                content=ft.Column(
                    [title_field, description_field, time_field, important_check, split_check, note_text],
                    spacing=8,
                    tight=True,
                ),
                actions=[
                    ft.TextButton(content=ft.Text("Batal"), on_click=lambda ev: page.pop_dialog()),
                    ui_helpers.primary_button("Jadiin tugas", submit),
                ],
            )
        )

    def drop(note_id: str):
        storage.delete_inbox_note(note_id)
        render_notes()
        page.update()

    def render_notes():
        notes = storage.get_inbox()
        if not notes:
            notes_column.controls = [
                ui_helpers.empty_state(
                    "Belum ada catatan. Tulis apa pun yang keinget dari Beranda.",
                    ft.Icons.EDIT_NOTE,
                )
            ]
            return

        notes_column.controls = [
            ui_helpers.card(
                ft.Column(
                    [
                        ft.Text(note["text"], size=13.5, color=theme.ON_BACKGROUND),
                        ft.Text(_relative_time(note.get("created_at", "")), size=10.5, color=theme.MUTED),
                        ft.Row(
                            [
                                ft.TextButton(
                                    content=ft.Text("Jadiin tugas", size=12, weight=ft.FontWeight.BOLD),
                                    icon=ft.Icons.ARROW_FORWARD,
                                    on_click=lambda e, n=note: to_task(n),
                                ),
                                ft.Container(expand=True),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE_OUTLINE,
                                    icon_color=theme.MUTED,
                                    icon_size=18,
                                    tooltip="Hapus catatan",
                                    on_click=lambda e, i=note["id"]: drop(i),
                                ),
                            ],
                            spacing=4,
                        ),
                    ],
                    spacing=6,
                ),
                padding=14,
            )
            for note in notes
        ]

    render_notes()

    body.controls = [
        ui_helpers.page_header("Yang Keinget", on_back=lambda e: navigate("home")),
        ui_helpers.subtitle(
            "Catatan mentah yang belum jadi tugas. Nggak usah rapi -- "
            "nanti KALEM yang bantu mecahin jadi langkah kecil."
        ),
        notes_column,
        ui_helpers.disclaimer(
            "Nggak ada kewajiban ngosongin daftar ini. Kalau ada yang udah "
            "nggak relevan, hapus aja."
        ),
    ]
    return body
