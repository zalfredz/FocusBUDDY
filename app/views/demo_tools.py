"""Kontrol simulasi yang dikelompokkan untuk presentasi FocusBuddy."""
from __future__ import annotations

import flet as ft

from app import clock, demo_scenarios, storage, theme, ui_helpers


def _tool_card(
    icon: str,
    title: str,
    description: str,
    on_click,
    *,
    active: bool = False,
) -> ft.Container:
    color = theme.TERTIARY if active else theme.PRIMARY
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, color=color, size=21),
                    width=42,
                    height=42,
                    alignment=ft.Alignment.CENTER,
                    bgcolor=ft.Colors.with_opacity(0.14, color),
                    border_radius=13,
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
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=theme.MUTED, size=19),
            ],
            spacing=11,
        ),
        bgcolor=theme.SURFACE,
        border=ft.Border.all(1, color if active else theme.BORDER),
        border_radius=theme.CARD_RADIUS,
        padding=14,
        on_click=on_click,
        ink=True,
    )


def build(page: ft.Page, navigate) -> ft.Control:
    simulated_time = clock.is_simulated() or bool(storage.hour_offset())
    overlay_active = demo_scenarios.demo_overlay_active()

    def refresh() -> None:
        navigate("demo_tools")

    def next_day(e) -> None:
        storage.advance_day(1)
        refresh()

    def toggle_night(e) -> None:
        if storage.hour_offset():
            storage.clear_hour_offset()
        else:
            storage.jump_to_hour(storage.MEAL_ASK_HOUR)
        refresh()

    def restore_time(e) -> None:
        storage.clear_day_offset()
        storage.clear_hour_offset()
        refresh()

    def replay_opening(e) -> None:
        storage.clear_last_brief_date()
        storage.touch_last_open()
        navigate("home")

    def clear_overlay(e) -> None:
        demo_scenarios.clear_demo_overlay()
        refresh()

    def open_scenarios(e) -> None:
        def pick(key: str) -> None:
            demo_scenarios.apply_scenario_overlay(key)
            page.pop_dialog()
            navigate("home")

        rows: list[ft.Control] = [
            ft.Text(
                "Pilih kondisi yang mau ditunjukkan. Overlay ini tidak mengubah "
                "nama, profil, favorit, obat, diary, tugas, atau catatan asli.",
                size=12,
                color=theme.MUTED,
            )
        ]
        for key, _label, description, demo_title, _wow in demo_scenarios.list_scenarios():
            content: list[ft.Control] = [
                ft.Text(
                    demo_title,
                    size=13,
                    weight=ft.FontWeight.BOLD,
                    color=theme.ON_BACKGROUND,
                ),
                ft.Text(
                    description,
                    size=11,
                    color=theme.MUTED,
                ),
            ]
            rows.append(
                ft.Container(
                    content=ft.Column(content, spacing=3),
                    bgcolor=theme.BACKGROUND,
                    border_radius=12,
                    padding=12,
                    on_click=lambda event, scenario_key=key: pick(scenario_key),
                    ink=True,
                )
            )

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Pilih kondisi demo", size=16),
                content=ft.Column(
                    rows,
                    spacing=8,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                actions=[
                    ft.TextButton(
                        content=ft.Text("Batal"),
                        on_click=lambda event: page.pop_dialog(),
                    )
                ],
            )
        )

    status_items: list[ft.Control] = [
        ft.Text(
            clock.now().strftime("%A, %d %B %Y · %H:%M"),
            size=13,
            weight=ft.FontWeight.BOLD,
            color=theme.ON_BACKGROUND,
        ),
        ft.Text(
            "Waktu simulasi aktif" if simulated_time else "Mengikuti waktu asli perangkat",
            size=11,
            color=theme.TERTIARY if simulated_time else theme.MUTED,
        ),
        ft.Text(
            "Overlay Auto Feel aktif" if overlay_active else "Tidak ada overlay Auto Feel",
            size=11,
            color=theme.TERTIARY if overlay_active else theme.MUTED,
        ),
    ]

    tools: list[ft.Control] = [
        _tool_card(
            ft.Icons.SKIP_NEXT,
            "Maju 1 hari",
            "Uji tugas berulang, deadline, dan perubahan keputusan besok.",
            next_day,
            active=bool(storage.day_offset()),
        ),
        _tool_card(
            ft.Icons.WB_SUNNY if storage.hour_offset() else ft.Icons.BEDTIME,
            "Kembali ke jam asli" if storage.hour_offset() else "Lompat ke malam",
            "Uji pertanyaan makan dan respons KALEM pada malam hari.",
            toggle_night,
            active=bool(storage.hour_offset()),
        ),
        _tool_card(
            ft.Icons.REPLAY,
            "Ulang alur pembukaan",
            "Tampilkan lagi Morning Brief seperti saat aplikasi baru dibuka.",
            replay_opening,
        ),
        _tool_card(
            ft.Icons.AUTO_FIX_HIGH,
            "Auto Feel — pilih skenario",
            "Tampilkan kondisi demo terarah tanpa menimpa data asli.",
            open_scenarios,
            active=overlay_active,
        ),
    ]

    cleanup: list[ft.Control] = []
    if simulated_time:
        cleanup.append(
            ft.OutlinedButton(
                content=ft.Text("Kembali ke waktu asli"),
                icon=ft.Icons.RESTORE,
                on_click=restore_time,
                style=ft.ButtonStyle(color=theme.ON_BACKGROUND),
            )
        )
    if overlay_active:
        cleanup.append(
            ft.OutlinedButton(
                content=ft.Text("Hapus overlay data demo"),
                icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                on_click=clear_overlay,
                style=ft.ButtonStyle(color=theme.DANGER),
            )
        )

    return ft.Column(
        [
            ui_helpers.page_header("Alat Demo", lambda e: navigate("home")),
            ui_helpers.card(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.SCIENCE_OUTLINED, color=theme.TERTIARY),
                                ft.Column(status_items, spacing=2, expand=True),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        ft.Text(
                            "Semua kontrol di halaman ini hanya memengaruhi akun yang "
                            "sedang login dan disediakan khusus untuk presentasi.",
                            size=10.5,
                            color=theme.MUTED,
                        ),
                    ],
                    spacing=10,
                ),
                padding=16,
            ),
            *tools,
            *(
                [
                    ui_helpers.card(
                        ft.Column(
                            [ui_helpers.section_header("Bersihkan simulasi"), *cleanup],
                            spacing=8,
                        ),
                        padding=14,
                    )
                ]
                if cleanup
                else []
            ),
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
