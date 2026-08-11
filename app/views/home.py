"""Beranda dan rekomendasi tindakan utama KALEM."""
from __future__ import annotations

import asyncio

import flet as ft

from app import (
    buddy,
    clock,
    config,
    focus_session,
    session_scope,
    storage,
    theme,
    ui_helpers,
)
from app.core import kalem_engine
from app.core.medication_model import check_status

_TICKER_SESSION_KEY = "focusbuddy.home_ticker.v1"
_FALLBACK_TICKER: dict = {"running": False, "refresh": None}


def _ticker_state() -> dict:
    return (
        session_scope.get_or_create(
            _TICKER_SESSION_KEY,
            lambda: {"running": False, "refresh": None},
        )
        or _FALLBACK_TICKER
    )


def _dev_buttons(page: ft.Page, navigate) -> list[ft.Control]:
    if not config.DEMO_MODE:
        return []

    def next_day(e):
        storage.advance_day(1)
        navigate("home")

    def lompat_malam(e):
        if storage.hour_offset():
            storage.clear_hour_offset()
        else:
            storage.jump_to_hour(storage.MEAL_ASK_HOUR)
        navigate("home")

    def buka_ulang_app(e):
        storage.clear_last_brief_date()
        storage.touch_last_open()
        navigate("home")

    def toggle_subs(e):
        storage.set_premium(not storage.is_premium())
        navigate("home")

    def open_auto_feel(e):
        try:
            import SettingDemo
        except ImportError:
            SettingDemo = None

        if SettingDemo is None:
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("SettingDemo.py nggak ketemu", size=16),
                    content=ft.Text(
                        "File SettingDemo.py harus ada di folder utama project "
                        "(sejajar sama README.md).",
                        size=13,
                    ),
                    actions=[
                        ft.TextButton(content=ft.Text("Oke"), on_click=lambda ev: page.pop_dialog())
                    ],
                )
            )
            return

        def pick(key: str):
            SettingDemo.apply_scenario_overlay(key)
            page.pop_dialog()
            navigate("home")

        def clear_demo(e):
            SettingDemo.clear_demo_overlay()
            page.pop_dialog()
            navigate("home")

        rows: list[ft.Control] = [
            ft.Text(
                "Pilih kondisi yang mau ditunjukin. Ini cuma menambahkan overlay "
                "demo; nama, profil, favorit, obat, diary, tugas, dan catatan "
                "aslimu tetap aman.",
                size=12,
                color=theme.MUTED,
            )
        ]
        for key, label, desc, judul_demo, wow in SettingDemo.list_scenarios():
            objective = SettingDemo.DEMO_OBJECTIVES.get(key, {})
            isi: list[ft.Control] = [
                ft.Text(judul_demo, size=13, weight=ft.FontWeight.BOLD, color=theme.ON_BACKGROUND),
            ]
            if objective.get("story"):
                isi.append(ft.Text(objective["story"], size=11.5, color=theme.ON_BACKGROUND))
            if objective.get("tests"):
                isi.append(ft.Text(
                    "Yang diuji: " + ", ".join(objective["tests"]),
                    size=10.5, color=theme.MUTED,
                ))
            if wow:
                isi.append(ft.Text(f"Demo point: {wow}", size=10.5,
                                    color=theme.PRIMARY, italic=True))
            isi.append(ft.Text(f"{label} — {desc}", size=9.5, color=theme.MUTED))
            rows.append(
                ft.Container(
                    content=ft.Column(isi, spacing=3),
                    bgcolor=theme.BACKGROUND,
                    border_radius=12,
                    padding=12,
                    on_click=lambda e, k=key: pick(k),
                    ink=True,
                )
            )

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Auto Feel — data demo", size=16),
                content=ft.Column(rows, spacing=8, tight=True, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton(
                        content=ft.Text("Hapus data demo"),
                        on_click=clear_demo,
                        disabled=not SettingDemo.demo_overlay_active(),
                    ),
                    ft.TextButton(content=ft.Text("Batal"), on_click=lambda ev: page.pop_dialog())
                ],
            )
        )

    return [
        ft.IconButton(
            icon=ft.Icons.SKIP_NEXT,
            icon_color=theme.TERTIARY if clock.is_simulated() else theme.MUTED,
            icon_size=20,
            tooltip=f"Maju 1 hari (testing) — sekarang {clock.today().strftime('%a, %d %b')}",
            on_click=next_day,
        ),
        ft.IconButton(
            icon=ft.Icons.WB_SUNNY if storage.hour_offset() else ft.Icons.BEDTIME,
            icon_color=theme.TERTIARY if storage.hour_offset() else theme.MUTED,
            icon_size=20,
            tooltip=(
                f"Balikin ke jam asli (demo) — sekarang {clock.now().strftime('%H:%M')}"
                if storage.hour_offset()
                else f"Lompat ke malam (demo) — sekarang {clock.now().strftime('%H:%M')}"
            ),
            on_click=lompat_malam,
        ),
        ft.IconButton(
            icon=ft.Icons.LOGOUT,
            icon_color=theme.MUTED,
            icon_size=20,
            tooltip="Tutup & buka lagi app (demo) — ngulang alur pembukaan",
            on_click=buka_ulang_app,
        ),
        ft.IconButton(
            icon=ft.Icons.WORKSPACE_PREMIUM,
            icon_color=theme.TERTIARY if storage.is_premium() else theme.MUTED,
            icon_size=20,
            tooltip="SUBS ON (demo)" if storage.is_premium() else "SUBS OFF (demo)",
            on_click=toggle_subs,
        ),
        ft.IconButton(
            icon=ft.Icons.AUTO_FIX_HIGH,
            icon_color=theme.MUTED,
            icon_size=20,
            tooltip="Auto Feel — overlay data demo (data asli tetap aman)",
            on_click=open_auto_feel,
        ),
    ]


def _popup_checkin(page: ft.Page, navigate) -> None:
    pilih = {"mood": buddy.DEFAULT_MOOD, "energi": 0}
    isi = ft.Column(spacing=14, tight=True)

    def gambar():
        chip_mood = buddy.mood_picker(pilih["mood"], pick_mood)
        chip_energi = ft.Row(
            [
                ft.Container(
                    content=ft.Text(
                        str(lv),
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color="#FFFFFF" if lv == pilih["energi"] else theme.ON_BACKGROUND,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    height=38,
                    expand=True,
                    bgcolor=theme.PRIMARY if lv == pilih["energi"] else theme.SURFACE,
                    border=ft.Border.all(
                        1, theme.PRIMARY if lv == pilih["energi"] else theme.BORDER
                    ),
                    border_radius=10,
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda e, v=lv: pick_energi(v),
                    ink=True,
                )
                for lv in range(1, 7)
            ],
            spacing=5,
        )
        isi.controls = [
            ft.Text("Hari ini kamu ngerasa gimana?", size=12.5, color=theme.ON_BACKGROUND),
            chip_mood,
            ft.Text("Tenaga kamu sekarang? (1-6)", size=12.5, color=theme.ON_BACKGROUND),
            chip_energi,
            ft.Text(
                "Dua tap aja. Ini yang nentuin seberat apa Kalem naruh target "
                "buat kamu hari ini.",
                size=10.5,
                color=theme.MUTED,
            ),
        ]
        page.update()

    def pick_mood(m: str):
        pilih["mood"] = m
        gambar()

    def pick_energi(v: int):
        pilih["energi"] = v
        gambar()

    def simpan(e):
        skor = buddy.score_for(pilih["mood"])
        energi = pilih["energi"] or _energi_dari_skor(skor)
        storage.add_mood_log(
            mood=pilih["mood"],
            score=skor,
            energy=energi,
            diary="",
            quick_tags=[],
        )
        storage.set_today_energy(energi)
        page.pop_dialog()
        navigate("home")

    def nanti(e):
        page.pop_dialog()

    gambar()
    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text("Sebentar aja ya 🌿", size=16),
            content=isi,
            actions=[
                ft.TextButton(content=ft.Text("Nanti aja", color=theme.MUTED), on_click=nanti),
                ui_helpers.primary_button("Simpan", simpan, icon=ft.Icons.CHECK),
            ],
        )
    )


def _energi_dari_skor(score: int) -> int:
    return {1: 1, 2: 2, 3: 3, 4: 5, 5: 6}.get(score, 3)


def _popup_makan(page: ft.Page, navigate) -> None:
    def jawab(makan: bool):
        log = storage.today_mood()
        if not log:
            page.pop_dialog()
            return
        storage.add_mood_log(
            mood=log.get("mood", buddy.DEFAULT_MOOD),
            score=log.get("score", 3),
            energy=log.get("energy", 3),
            diary=log.get("diary", ""),
            tags=log.get("tags", []),
            quick_tags=log.get("quick_tags", []),
            ate_today=makan,
            rested_enough=log.get("rested_enough"),
        )
        page.pop_dialog()
        navigate("home")

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text("Udah makan hari ini? 🍚", size=16),
            content=ft.Column(
                [
                    ft.Text(
                        "Jawab jujur aja — dua-duanya nggak apa-apa.",
                        size=12.5,
                        color=theme.ON_BACKGROUND,
                    ),
                    ft.Text(
                        "Kalem nanya ini cuma malem, buat tau kamu keurus apa "
                        "nggak — bukan buat nilai kamu.",
                        size=10.5,
                        color=theme.MUTED,
                    ),
                ],
                spacing=8,
                tight=True,
            ),
            actions=[
                ft.TextButton(
                    content=ft.Text("Belum", color=theme.WARN, weight=ft.FontWeight.BOLD),
                    on_click=lambda e: jawab(False),
                ),
                ui_helpers.primary_button("Udah", lambda e: jawab(True), icon=ft.Icons.CHECK),
            ],
        )
    )


def build(page: ft.Page, navigate) -> ft.Control:
    ticker_state = _ticker_state()
    profile, day = kalem_engine.snapshot()
    decision = kalem_engine.decide(profile, day)

    if not focus_session.is_active():
        from app.kalem_ml import fitur as kfitur

        storage.record_decision_shown(
            decision.kind,
            decision.action_kind,
            kfitur.bangun_fitur(day=day, profil=profile),
            decision.action_label,
        )


    sim_banner: list[ft.Control] = []
    if clock.is_simulated():
        sim_banner = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.SCIENCE, color="#FFFFFF", size=16),
                        ft.Text(
                            f"Mode testing — hari ini disimulasikan jadi "
                            f"{clock.today().strftime('%a, %d %b %Y')} (+{storage.day_offset()} hari)",
                            color="#FFFFFF",
                            size=11.5,
                            expand=True,
                        ),
                        ft.TextButton(
                            content=ft.Text("Balik", size=11, color="#FFFFFF"),
                            on_click=lambda e: (storage.clear_day_offset(), navigate("home")),
                        ),
                    ],
                    spacing=8,
                ),
                bgcolor=theme.TERTIARY,
                border_radius=12,
                padding=ft.Padding.symmetric(vertical=6, horizontal=12),
            )
        ]

    med_status = check_status(day.medication)
    med_banner: list[ft.Control] = []
    if med_status.needs_reminder:
        med_banner = [
            ft.Container(
                content=ft.Row(
                    [
                        ui_helpers.med_icon(18, "#FFFFFF"),
                        ft.Text(med_status.message, color="#FFFFFF", size=12.5, expand=True),
                        ft.TextButton(
                            content=ft.Text("Cari apotek", size=12, color="#FFFFFF"),
                            on_click=lambda e: navigate("med_setup"),
                        ),
                    ],
                    spacing=8,
                ),
                bgcolor=theme.DANGER,
                border_radius=14,
                padding=ft.Padding.symmetric(vertical=8, horizontal=14),
            )
        ]


    greeting = ft.Row(
        [
            ft.Column(
                [
                    ft.Text(
                        f"Halo, {storage.display_name()}",
                        size=22,
                        weight=ft.FontWeight.BOLD,
                        color=theme.ON_BACKGROUND,
                        font_family=theme.FONT_DISPLAY,
                    ),
                    ft.Row(
                        [
                            ft.Text(
                                clock.today().strftime("%A, %d %B %Y"), size=12, color=theme.MUTED
                            ),
                            *(
                                [
                                    ft.Container(
                                        content=ft.Row(
                                            [
                                                ft.Icon(
                                                    ft.Icons.WORKSPACE_PREMIUM,
                                                    size=11,
                                                    color="#FFFFFF",
                                                ),
                                                ft.Text(
                                                    "PREMIUM",
                                                    size=9,
                                                    weight=ft.FontWeight.BOLD,
                                                    color="#FFFFFF",
                                                ),
                                            ],
                                            spacing=3,
                                            tight=True,
                                        ),
                                        bgcolor=theme.TERTIARY,
                                        border_radius=8,
                                        padding=ft.Padding.symmetric(vertical=2, horizontal=6),
                                    )
                                ]
                                if storage.is_premium()
                                else []
                            ),
                        ],
                        spacing=6,
                    ),
                ],
                spacing=2,
                expand=True,
            ),
            *_dev_buttons(page, navigate),
            ft.IconButton(
                icon=ft.Icons.SETTINGS,
                icon_color=theme.MUTED,
                icon_size=20,
                tooltip="Pengaturan",
                on_click=lambda e: navigate("settings"),
            ),
        ],
        spacing=0,
    )


    accent = storage.favorite_color_hex()
    kalem_face_block: ft.Control = buddy.face(decision.mood, 170)
    if accent:
        kalem_face_block = ft.Container(
            content=kalem_face_block,
            bgcolor=ft.Colors.with_opacity(0.18, accent),
            border_radius=110,
            padding=10,
        )

    kalem_block = ft.Container(
        content=ft.Column(
            [
                kalem_face_block,
                buddy.speech_bubble(decision.message),
            ],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        alignment=ft.Alignment.CENTER,
    )


    def take_med(e):
        result = storage.take_medication()
        if result is None and (day.medication or {}).get("enabled", True):
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Stoknya udah abis", size=16),
                    content=ft.Text(
                        "Kalem nggak bisa nyatet absen obat kalau stoknya 0. "
                        "Update dulu stoknya di setelan obat.",
                        size=13,
                    ),
                    actions=[
                        ft.TextButton(content=ft.Text("Nanti"), on_click=lambda ev: page.pop_dialog()),
                        ui_helpers.primary_button(
                            "Ke setelan obat",
                            lambda ev: (page.pop_dialog(), navigate("med_setup")),
                        ),
                    ],
                )
            )
            return
        navigate("home")

    def start_focus(e):
        task = decision.task or {}
        focus_session.start(
            decision.focus_minutes,
            label=decision.step_text or decision.detail,
            task_title=decision.detail,
            kategori=task.get("kategori", ""),
            jumlah_unit=task.get("jumlah_unit", 0),
            energi=storage.today_energy() or 3,
        )
        navigate("home")

    ACTIONS = {
        "med_taken": take_med,
        "reset": lambda e: navigate("reset"),
        "focus": start_focus,
        "add_task": lambda e: navigate("tracker"),
    }

    ACTION_ICONS = {
        "med_taken": ft.Icons.CHECK_CIRCLE,
        "reset": ft.Icons.SPA,
        "focus": ft.Icons.PLAY_ARROW,
        "add_task": ft.Icons.ADD,
    }

    card_children: list[ft.Control] = []
    if decision.kind == "next_action":
        card_children = [
            ui_helpers.section_header("Sekarang ini aja"),
            ft.Text(
                decision.step_text,
                size=17,
                weight=ft.FontWeight.BOLD,
                color=theme.ON_BACKGROUND,
                font_family=theme.FONT_DISPLAY,
            ),
            ft.Row(
                [
                    ft.Icon(ft.Icons.SUBDIRECTORY_ARROW_RIGHT, size=14, color=theme.MUTED),
                    ft.Text(f"dari: {decision.detail}", size=11.5, color=theme.MUTED, expand=True),
                ],
                spacing=4,
            ),
        ]
    elif decision.detail:
        card_children = [ft.Text(decision.detail, size=13.5, color=theme.ON_BACKGROUND)]

    def _aksi_dicatat(e):
        storage.record_decision_acted(decision.kind, decision.action_kind)
        ACTIONS.get(decision.action_kind, lambda ev: None)(e)

    card_children.append(
        ui_helpers.wide_button(
            decision.action_label,
            _aksi_dicatat,
            icon=ACTION_ICONS.get(decision.action_kind),
        )
    )

    action_card = ui_helpers.card(ft.Column(card_children, spacing=10))


    ring = ft.ProgressRing(
        value=1.0, width=190, height=190, stroke_width=13,
        color=theme.PRIMARY, bgcolor=theme.BORDER,
    )
    clock_text = ft.Text("", size=40, weight=ft.FontWeight.BOLD,
                         color=theme.ON_BACKGROUND, font_family=theme.FONT_DISPLAY)
    sub_text = ft.Text("", size=11, color=theme.MUTED, text_align=ft.TextAlign.CENTER)
    bar = ft.ProgressBar(value=0.0, color=theme.PRIMARY, bgcolor=theme.BORDER, bar_height=8)
    elapsed_text = ft.Text("", size=10.5, color=theme.MUTED)
    total_text = ft.Text("", size=10.5, color=theme.MUTED)
    status_text = ft.Text("", size=12.5, color=theme.ON_BACKGROUND,
                          text_align=ft.TextAlign.CENTER)
    step_text = ft.Text("", size=15, weight=ft.FontWeight.BOLD, color=theme.ON_BACKGROUND,
                        text_align=ft.TextAlign.CENTER)
    controls_row = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=8)

    def toggle_pause(e):
        if focus_session.is_running():
            focus_session.pause()
        else:
            focus_session.resume()
        refresh_focus()

    def restart(e):
        focus_session.reset()
        refresh_focus()

    def finish_session(e):
        focus_session.stop()
        navigate("home")

    def refresh_focus():
        s = focus_session.snapshot()
        if not s["active"]:
            return

        ring.value = s["progress"]
        bar.value = 1 - s["progress"]
        clock_text.value = s["clock"]
        step_text.value = s["label"] or "Sesi fokus"
        total = s["total_seconds"] // 60
        done_min = (s["total_seconds"] - s["remaining"] + 59) // 60
        elapsed_text.value = f"{done_min} dari {total} menit"
        total_text.value = f"{round((1 - s['progress']) * 100)}%"

        if s["finished"]:
            rest = kalem_engine.break_minutes_for(day.energy_level or 3)
            ring.color = theme.SUCCESS
            clock_text.value = "Selesai"
            status_text.value = f"Kelar! 🎉 Istirahat {rest} menit dulu."
            sub_text.value = "Nggak usah langsung lanjut."
        elif s["running"]:
            ring.color = theme.PRIMARY
            status_text.value = "Fokus jalan... satu hal aja dulu."
            sub_text.value = (
                f"dari: {s['task_title']}" if s["task_title"] else "Kamu lagi ngerjain ini"
            )
        else:
            ring.color = theme.WARN
            status_text.value = "Dijeda. Lanjut kapan pun kamu siap."
            sub_text.value = "Nggak apa-apa berhenti sebentar."

        buttons: list[ft.Control] = []
        if not s["finished"]:
            buttons.append(
                ui_helpers.primary_button(
                    "Jeda" if s["running"] else "Lanjut",
                    toggle_pause,
                    icon=ft.Icons.PAUSE if s["running"] else ft.Icons.PLAY_ARROW,
                )
            )
            buttons.append(ft.OutlinedButton(content=ft.Text("Ulang"), on_click=restart))
        buttons.append(
            ft.TextButton(
                content=ft.Text("Sudahi", size=12, color=theme.MUTED), on_click=finish_session
            )
        )
        controls_row.controls = buttons
        page.update()

    async def ticker():
        if ticker_state["running"]:
            return
        ticker_state["running"] = True
        try:
            while focus_session.is_active():
                await asyncio.sleep(1)
                fn = ticker_state["refresh"]
                if fn:
                    fn()
        finally:
            ticker_state["running"] = False

    focus_card = ui_helpers.card(
        ft.Column(
            [
                ui_helpers.section_header("Sesi fokus"),
                step_text,
                ft.Container(
                    content=ft.Stack(
                        [
                            ring,
                            ft.Container(
                                content=ft.Column(
                                    [clock_text, sub_text],
                                    spacing=2,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                width=190,
                                height=190,
                                alignment=ft.Alignment.CENTER,
                                padding=ft.Padding.symmetric(vertical=0, horizontal=24),
                            ),
                        ],
                        width=190,
                        height=190,
                    ),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    [
                        bar,
                        ft.Row(
                            [elapsed_text, ft.Container(expand=True), total_text],
                            spacing=4,
                        ),
                    ],
                    spacing=4,
                ),
                status_text,
                controls_row,
            ],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=18,
    )

    session_active = focus_session.is_active()
    if session_active:
        ticker_state["refresh"] = refresh_focus
        refresh_focus()


    def open_capture(e):
        note_field = ft.TextField(
            hint_text="Apa aja yang keinget. Nggak usah rapi.",
            multiline=True,
            min_lines=3,
            max_lines=6,
            autofocus=True,
        )

        def save(ev):
            text = (note_field.value or "").strip()
            if not text:
                page.pop_dialog()
                return
            storage.add_inbox_note(text)
            page.pop_dialog()
            navigate("home")

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Buang dari kepala dulu", size=16),
                content=ft.Column(
                    [
                        ft.Text(
                            "Simpen mentah dulu di sini. Nanti bisa dirapikan jadi tugas.",
                            size=12,
                            color=theme.MUTED,
                        ),
                        note_field,
                    ],
                    spacing=10,
                    tight=True,
                ),
                actions=[
                    ft.TextButton(content=ft.Text("Batal"), on_click=lambda ev: page.pop_dialog()),
                    ui_helpers.primary_button("Simpan", save),
                ],
            )
        )

    inbox_count = len(storage.get_inbox())

    capture_children: list[ft.Control] = [
        ft.Icon(ft.Icons.EDIT_NOTE, color=theme.SECONDARY, size=20),
        ft.Container(
            content=ft.Text(
                "Ada yang keinget? Tulis cepat",
                size=12.5,
                color=theme.ON_BACKGROUND,
            ),
            expand=True,
            on_click=open_capture,
            ink=True,
            border_radius=10,
            padding=ft.Padding.symmetric(vertical=4, horizontal=2),
        ),
    ]
    if inbox_count:
        capture_children.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text(
                            f"{inbox_count} tersimpan",
                            size=11.5,
                            color=theme.PRIMARY,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, color=theme.PRIMARY, size=18),
                    ],
                    spacing=2,
                ),
                on_click=lambda e: navigate("inbox"),
                ink=True,
                border_radius=10,
                padding=ft.Padding.symmetric(vertical=4, horizontal=6),
            )
        )

    capture_row = ft.Container(
        content=ft.Row(capture_children, spacing=10),
        bgcolor=theme.SURFACE,
        border=ft.Border.all(1, theme.BORDER),
        border_radius=14,
        padding=ft.Padding.symmetric(vertical=12, horizontal=14),
    )


    sos_row = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.SPA, color=theme.PRIMARY, size=18),
                ft.Text(
                    "Lagi kewalahan? Ambil jeda dulu",
                    size=12.5,
                    color=theme.PRIMARY,
                    weight=ft.FontWeight.BOLD,
                    expand=True,
                ),
            ],
            spacing=10,
        ),
        border=ft.Border.all(1, theme.PRIMARY),
        border_radius=14,
        padding=ft.Padding.symmetric(vertical=12, horizontal=14),
        on_click=lambda e: navigate("reset"),
        ink=True,
    )

    layout = ft.Column(
        [
            *sim_banner,
            *med_banner,
            greeting,
            kalem_block,
            focus_card if session_active else action_card,
            capture_row,
            sos_row,
            ui_helpers.disclaimer(
                "FocusBuddy bukan alat diagnosis ADHD dan bukan pengganti tenaga medis."
            ),
        ],
        spacing=16,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    if session_active:
        page.run_task(ticker)

    if not session_active:
        if storage.today_mood() is None:
            _popup_checkin(page, navigate)
        elif storage.perlu_tanya_makan():
            _popup_makan(page, navigate)

    return layout
