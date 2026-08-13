"""Preferensi personal yang dipakai KALEM untuk rekomendasi dan recovery."""
from __future__ import annotations

import flet as ft

from app import buddy, storage, theme, ui_helpers

HINTS = {
    "musik": "mis. lo-fi, Tulus, instrumental",
    "suara_alam": "mis. suara hujan, ombak, white noise",
    "snack": "mis. es kopi susu, teh hangat, coklat",
    "kondisi_ruangan": "mis. lampu redup, meja kosong, ruangan dingin",
    "tempat_fokus": "mis. perpustakaan, meja dekat jendela",
    "fokus_lainnya": "mis. timer visual, pakai headphone",
    "hobi": "mis. gambar, main gitar, jalan sore",
    "tempat": "mis. balkon, kamar, kafe dekat kos",
    "penyemangat": "mis. pelan-pelan juga tetap jalan",
    "orang": "mis. Rani, Bang Dito — nama panggilan aja",
    "gerak": "mis. jalan keliling kos, stretching leher",
    "overwhelm_lainnya": "mis. mandi air hangat, matikan notifikasi",
    "preferensi_lainnya": "mis. harus pakai headphone",
    "kembali_fokus": "mis. minum air lalu tulis satu langkah kecil",
    "rasa_aman": "mis. selimut, kamar rapi, ngobrol dengan teman",
}

GROUPS = [
    (
        "A. Hal yang membantu fokus",
        (
            "musik", "suara_alam", "tempat_fokus", "snack",
            "kondisi_ruangan", "fokus_lainnya",
        ),
    ),
    (
        "B. Saat sedang overwhelmed",
        ("tempat", "hobi", "gerak", "penyemangat", "overwhelm_lainnya"),
    ),
    (
        "C. Preferensi mengerjakan tugas",
        ("preferensi_kerja", "preferensi_lainnya", "jam_capek", "warna"),
    ),
    (
        "D. Personal support",
        ("orang", "kembali_fokus", "rasa_aman"),
    ),
]


def build(page: ft.Page, navigate) -> ft.Control:
    back_route = getattr(page, "_focusbuddy_favorites_return", "mood")
    current = storage.get_favorites()
    fields: dict[str, ft.TextField] = {}
    progress_holder = ft.Container()

    picks: dict[str, str] = {
        "warna": str(current.get("warna", "")),
        "jam_capek": str(current.get("jam_capek", "")),
    }
    work_styles = {
        value
        for value in str(current.get("preferensi_kerja", "")).split(",")
        if value in storage.FAVORITE_WORK_STYLES
    }
    pick_holders = {
        "warna": ft.Container(),
        "jam_capek": ft.Container(),
        "preferensi_kerja": ft.Container(),
    }

    def render_progress() -> None:
        filled = storage.favorites_filled()
        total = len(storage.FAVORITE_FIELDS)
        progress_holder.content = ft.Column(
            [
                ft.Text(
                    f"KALEM makin kenal kamu — {filled}/{total} preferensi terisi.",
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
                    "Nggak ada yang wajib diisi. Boleh dilengkapi sedikit demi sedikit.",
                    size=11,
                    color=theme.MUTED,
                ),
            ],
            spacing=8,
        )

    def choose(key: str, value: str) -> None:
        picks[key] = "" if picks[key] == value else value
        render_picks()
        page.update()

    def toggle_work_style(value: str) -> None:
        if value in work_styles:
            work_styles.remove(value)
        else:
            work_styles.add(value)
        render_picks()
        page.update()

    def render_picks() -> None:
        swatches: list[ft.Control] = []
        for value, (label, hex_code) in storage.FAVORITE_COLORS.items():
            active = picks["warna"] == value
            swatches.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(width=14, height=14, bgcolor=hex_code, border_radius=7),
                            ft.Text(label, size=11.5, color="#FFFFFF" if active else theme.ON_BACKGROUND),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    bgcolor=hex_code if active else theme.SURFACE,
                    border=ft.Border.all(1, hex_code if active else theme.BORDER),
                    border_radius=12,
                    padding=ft.Padding.symmetric(vertical=7, horizontal=10),
                    on_click=lambda e, selected=value: choose("warna", selected),
                    ink=True,
                )
            )
        pick_holders["warna"].content = _preference_block(
            storage.FAVORITE_FIELDS["warna"],
            ft.Row(swatches, spacing=6, wrap=True, run_spacing=6),
        )

        hour_chips = [
            _favorite_choice_chip(
                label,
                picks["jam_capek"] == value,
                lambda e, selected=value: choose("jam_capek", selected),
            )
            for value, (label, _) in storage.FAVORITE_TIRED_HOURS.items()
        ]
        pick_holders["jam_capek"].content = _preference_block(
            storage.FAVORITE_FIELDS["jam_capek"],
            ft.Row(hour_chips, spacing=6, wrap=True, run_spacing=6),
        )

        style_chips = [
            _favorite_choice_chip(
                label,
                value in work_styles,
                lambda e, selected=value: toggle_work_style(selected),
            )
            for value, label in storage.FAVORITE_WORK_STYLES.items()
        ]
        pick_holders["preferensi_kerja"].content = _preference_block(
            storage.FAVORITE_FIELDS["preferensi_kerja"],
            ft.Row(style_chips, spacing=6, wrap=True, run_spacing=6),
        )

    def field_control(key: str) -> ft.Control:
        if key in pick_holders:
            return pick_holders[key]
        field = ft.TextField(
            label=storage.FAVORITE_FIELDS[key],
            value=str(current.get(key, "")),
            hint_text=HINTS.get(key, ""),
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            color=theme.ON_BACKGROUND,
            cursor_color=theme.ON_BACKGROUND,
            label_style=ft.TextStyle(color="#A5A3B2"),
            hint_style=ft.TextStyle(color="#8F8D9E"),
            bgcolor="#343446",
            filled=True,
            text_align=ft.TextAlign.JUSTIFY,
            expand=True,
            multiline=key in {"penyemangat", "kembali_fokus", "rasa_aman"},
            max_lines=2 if key in {"penyemangat", "kembali_fokus", "rasa_aman"} else 1,
        )
        fields[key] = field
        return ft.Container(
            content=ft.Row([field], spacing=0),
            padding=ft.Padding.symmetric(vertical=8, horizontal=14),
        )

    def save(e) -> None:
        for key, field in fields.items():
            storage.set_favorite(key, field.value or "")
        for key, value in picks.items():
            storage.set_favorite(key, value)
        storage.set_favorite("preferensi_kerja", ",".join(sorted(work_styles)))
        render_progress()
        ui_helpers.reward_overlay(page, "Favorit kamu tersimpan 🤍")
        page.update()

    render_picks()
    render_progress()

    groups = [
        ui_helpers.card(
            ft.ExpansionTile(
                title=ft.Text(
                    title,
                    size=13.5,
                    weight=ft.FontWeight.BOLD,
                    color=theme.ON_BACKGROUND,
                ),
                controls=[field_control(key) for key in keys],
                controls_padding=ft.Padding.only(bottom=8),
                tile_padding=ft.Padding.symmetric(vertical=4, horizontal=14),
                expanded=index == 0,
                maintain_state=True,
                text_color=theme.ON_BACKGROUND,
                collapsed_text_color=theme.ON_BACKGROUND,
                icon_color=theme.PRIMARY,
                collapsed_icon_color=theme.MUTED,
            ),
            padding=0,
        )
        for index, (title, keys) in enumerate(GROUPS)
    ]

    return ft.Column(
        [
            ui_helpers.page_header("Favorit Kamu", on_back=lambda e: navigate(back_route)),
            ft.Row(
                [
                    buddy.face("semangat", 64),
                    ft.Container(
                        content=buddy.speech_bubble(
                            "Isi sedikit demi sedikit. KALEM pakai ini untuk memilih "
                            "saran yang lebih dekat dengan kebiasaanmu."
                        ),
                        expand=True,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ui_helpers.card(progress_holder, padding=16),
            *groups,
            ui_helpers.wide_button("Simpan", save, icon=ft.Icons.SAVE),
            ui_helpers.disclaimer(
                "Semua isian tersimpan di ruang akun kamu dan boleh diubah kapan pun."
            ),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


def _preference_block(label: str, control: ft.Control) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(label, size=12.5, color=theme.ON_BACKGROUND),
                control,
            ],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        padding=ft.Padding.symmetric(vertical=8, horizontal=14),
    )


def _favorite_choice_chip(label: str, active: bool, on_click) -> ft.Control:
    return ft.Container(
        content=ft.Text(
            label,
            size=12.5,
            color=theme.ON_BACKGROUND,
            text_align=ft.TextAlign.CENTER,
        ),
        bgcolor=theme.PRIMARY if active else theme.SURFACE,
        border=ft.Border.all(1, theme.PRIMARY if active else theme.BORDER),
        border_radius=12,
        padding=ft.Padding.symmetric(vertical=10, horizontal=14),
        on_click=on_click,
        ink=True,
    )
