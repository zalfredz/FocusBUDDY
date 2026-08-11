"""Halaman preferensi penenang personal."""
from __future__ import annotations

import flet as ft

from app import buddy, storage, theme, ui_helpers

HINTS = {
    "musik": "mis. lo-fi, Tulus, hujan-hujanan",
    "snack": "mis. es kopi susu, indomie, coklat",
    "hobi": "mis. gambar, main gitar, jalan sore",
    "tempat": "mis. balkon, kamar, kafe deket kos",
    "penyemangat": "mis. pelan-pelan juga tetep jalan",
    "orang": "mis. Rani, Bang Dito — nama panggilan aja",
    "gerak": "mis. jalan keliling kos, stretching leher",
}

USED_FOR = {
    "musik": "Dipakai buat opsi 'dengerin musik' di halaman jeda.",
    "snack": "Ditawarin di halaman jeda pas kamu lagi kewalahan — aksi paling gampang.",
    "hobi": "Jadi saran kegiatan 60 detik pas kamu lagi kewalahan.",
    "tempat": "Jadi saran tempat pas kamu butuh pindah suasana.",
    "penyemangat": "Kalem bakal ngutip balik kalimat ini pas kamu lagi berat.",
    "warna": "Jadi aksen di kartu Kalem punya kamu.",
    "orang": "Kalau kamu lagi sering kewalahan, Kalem bakal ngingetin buat cerita ke dia.",
    "gerak": "Jadi saran gerak 60 detik, bukan 'stretching' generik.",
    "jam_capek": "Kalem nurunin ekspektasi otomatis di jam ini.",
}

PRIVACY_NOTE = {
    "orang": "Cukup nama panggilan. Kalem nggak nyimpen kontak dan nggak akan "
             "ngehubungin siapa pun otomatis — ini cuma pengingat buat kamu.",
    "penyemangat": "Tulis pakai kalimat kamu sendiri ya, bukan kutipan orang lain.",
}


def build(page: ft.Page, navigate) -> ft.Control:
    back_route = getattr(page, "_focusbuddy_favorites_return", "mood")
    current = storage.get_favorites()
    fields: dict[str, ft.TextField] = {}
    saved_note = ft.Text("", size=12, color=theme.PRIMARY)
    progress_holder = ft.Container()

    def render_progress():
        filled = storage.favorites_filled()
        total = len(storage.FAVORITE_FIELDS)
        progress_holder.content = ft.Column(
            [
                ft.Text(
                    f"Kalem makin kenal kamu — {filled}/{total} favorit terisi.",
                    size=13,
                    weight=ft.FontWeight.BOLD,
                    color=theme.ON_BACKGROUND,
                ),
                ft.ProgressBar(
                    value=filled / total if total else 0,
                    color=theme.PRIMARY,
                    bgcolor=theme.BORDER,
                    bar_height=6,
                ),
                ft.Text(
                    "Nggak ada yang wajib diisi. Boleh dilengkapi kapan aja.",
                    size=11,
                    color=theme.MUTED,
                ),
            ],
            spacing=8,
        )

    def save(e):
        for key, field in fields.items():
            storage.set_favorite(key, field.value or "")
        for key, value in picks.items():
            storage.set_favorite(key, value)
        saved_note.value = "Tersimpan 🤍"
        render_progress()
        page.update()

    picks: dict[str, str] = {
        "warna": current.get("warna", ""),
        "jam_capek": current.get("jam_capek", ""),
    }
    pick_holders = {key: ft.Container() for key in picks}

    def choose(key: str, value: str):
        picks[key] = "" if picks[key] == value else value
        render_picks()
        page.update()

    def render_picks():
        swatches = []
        for value, (label, hex_code) in storage.FAVORITE_COLORS.items():
            on = picks["warna"] == value
            swatches.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(width=14, height=14, bgcolor=hex_code, border_radius=7),
                            ft.Text(label, size=11.5,
                                    color=theme.ON_BACKGROUND if not on else "#FFFFFF"),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    bgcolor=hex_code if on else theme.SURFACE,
                    border=ft.Border.all(1, hex_code if on else theme.BORDER),
                    border_radius=12,
                    padding=ft.Padding.symmetric(vertical=7, horizontal=10),
                    on_click=lambda e, v=value: choose("warna", v),
                    ink=True,
                )
            )
        pick_holders["warna"].content = ft.Column(
            [
                ft.Text(storage.FAVORITE_FIELDS["warna"], size=12.5, color=theme.ON_BACKGROUND),
                ft.Row(swatches, spacing=6, wrap=True, run_spacing=6),
                ft.Text(USED_FOR["warna"], size=11, color=theme.MUTED),
            ],
            spacing=8,
        )

        hour_chips = [
            ui_helpers.choice_chip(
                label, picks["jam_capek"] == value, lambda e, v=value: choose("jam_capek", v)
            )
            for value, (label, _) in storage.FAVORITE_TIRED_HOURS.items()
        ]
        pick_holders["jam_capek"].content = ft.Column(
            [
                ft.Text(storage.FAVORITE_FIELDS["jam_capek"], size=12.5, color=theme.ON_BACKGROUND),
                ft.Text("Ini titik TERENDAH kamu — beda dari jam produktif di onboarding.",
                        size=11, color=theme.MUTED),
                ft.Row(hour_chips, spacing=6, wrap=True, run_spacing=6),
                ft.Text(USED_FOR["jam_capek"], size=11, color=theme.MUTED),
            ],
            spacing=8,
        )

    cards: list[ft.Control] = []
    for key, label in storage.FAVORITE_FIELDS.items():
        if key in picks:
            cards.append(ui_helpers.card(pick_holders[key], padding=14))
            continue

        field = ft.TextField(
            label=label,
            value=current.get(key, ""),
            hint_text=HINTS.get(key, ""),
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            multiline=key == "penyemangat",
            max_lines=2 if key == "penyemangat" else 1,
        )
        fields[key] = field

        card_items: list[ft.Control] = [
            field,
            ft.Text(USED_FOR.get(key, ""), size=11, color=theme.MUTED),
        ]
        if key in PRIVACY_NOTE:
            card_items.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.LOCK_OUTLINE, size=12, color=theme.SECONDARY),
                        ft.Text(PRIVACY_NOTE[key], size=10.5, color=theme.SECONDARY, expand=True),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                )
            )
        cards.append(ui_helpers.card(ft.Column(card_items, spacing=6), padding=14))

    render_picks()
    render_progress()

    return ft.Column(
        [
            ui_helpers.page_header("Favorit Kamu", on_back=lambda e: navigate(back_route)),
            ft.Row(
                [
                    buddy.face("semangat", 64),
                    ft.Container(
                        content=buddy.speech_bubble(
                            "Cerita dikit dong soal hal-hal yang kamu suka. "
                            "Nanti aku pakai pas kamu lagi butuh."
                        ),
                        expand=True,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ui_helpers.card(progress_holder, padding=16),
            *cards,
            ui_helpers.wide_button("Simpan", save, icon=ft.Icons.SAVE),
            saved_note,
            ui_helpers.disclaimer(
                "Semua isian di sini disimpan lokal di perangkat kamu aja."
            ),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
