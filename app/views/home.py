"""Beranda dan rekomendasi tindakan utama KALEM."""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta

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
_DAILY_FLOW_SESSION_KEY = "focusbuddy.daily_flow.v1"
_FALLBACK_TICKER: dict = {"running": False, "refresh": None}
_FALLBACK_DAILY_FLOW: dict = {"checkin_snoozed_date": ""}

HOME_BACKGROUND = "#141416"
HOME_TEXT = "#FFFFFF"
HOME_BUTTON = "#DDE0FF"
HOME_BUTTON_TEXT = "#181A35"
HOME_FONT = "Plus Jakarta Sans"
HOME_CONTENT_WIDTH = 320


def deadline_cue(task: dict, now: datetime | None = None) -> tuple[str, str]:
    """Buat penanda deadline pasif tanpa mengubah keputusan atau membuka modal."""
    deadline = storage.deadline_at(task)
    if deadline is None:
        return "", theme.MUTED
    now = now or clock.now()
    seconds = (deadline - now).total_seconds()
    time_label = deadline.strftime("%H:%M")
    if seconds < 0:
        overdue_minutes = max(1, math.ceil(abs(seconds) / 60))
        if overdue_minutes < 60:
            return f"Deadline lewat {overdue_minutes} menit", theme.DANGER
        overdue_hours = math.ceil(overdue_minutes / 60)
        if overdue_hours < 24:
            return f"Deadline lewat {overdue_hours} jam", theme.DANGER
        return f"Deadline lewat {math.ceil(overdue_hours / 24)} hari", theme.DANGER
    if deadline.date() == now.date():
        return f"Deadline hari ini · {time_label}", theme.WARN
    if deadline.date() == (now + timedelta(days=1)).date():
        return f"Deadline besok · {time_label}", theme.WARN
    return f"Deadline {deadline.strftime('%d %b')} · {time_label}", theme.MUTED


def _ticker_state() -> dict:
    return (
        session_scope.get_or_create(
            _TICKER_SESSION_KEY,
            lambda: {"running": False, "refresh": None},
        )
        or _FALLBACK_TICKER
    )


def _daily_flow_state() -> dict:
    return (
        session_scope.get_or_create(
            _DAILY_FLOW_SESSION_KEY,
            lambda: {"checkin_snoozed_date": ""},
        )
        or _FALLBACK_DAILY_FLOW
    )


def _checkin_required() -> bool:
    state = _daily_flow_state()
    return (
        storage.today_mood() is None
        and state.get("checkin_snoozed_date") != clock.today().isoformat()
    )


def _home_companion(level: int) -> tuple[str, str]:
    if level <= 3:
        return (
            "lelah",
            "Kamu kelihatan capek. Istirahat juga termasuk progress loh...",
        )
    return "semangat", "Semangat untuk Hari Ini!"


def build(page: ft.Page, navigate) -> ft.Control:
    def open_med_setup(e=None) -> None:
        setattr(page, "_focusbuddy_med_setup_return", "home")
        navigate("med_setup")

    ticker_state = _ticker_state()
    profile, day = kalem_engine.snapshot()
    session_active = focus_session.is_active()
    rendered_session_started_at = (
        focus_session.snapshot().get("session_started_at", "")
        if session_active
        else ""
    )
    needs_checkin = not session_active and _checkin_required()
    interruption_active = needs_checkin
    decision = (
        kalem_engine.KalemDecision(
            kind="pending",
            message="Aku tunggu kondisi kamu hari ini dulu.",
            mood=buddy.DEFAULT_MOOD,
            detail="Biar langkah berikutnya nggak asal pilih.",
            action_label="Isi check-in",
            action_kind="pending",
        )
        if interruption_active
        else kalem_engine.decide(profile, day)
    )
    has_tasks = any(not storage.task_is_done(task) for task in day.tasks_today)
    hide_empty_add_action = not has_tasks and decision.action_kind == "add_task"

    decision_record_id = None
    if not session_active and not interruption_active and not hide_empty_add_action:
        from models import fitur as kfitur

        decision_record_id = storage.record_decision_shown(
            decision.kind,
            decision.action_kind,
            kfitur.bangun_fitur(day=day, profil=profile),
            decision.action_label,
            task_id=(decision.task or {}).get("id", ""),
            occurrence_date=(decision.task or {}).get("_occurrence_date", ""),
            step_index=decision.step_index if decision.task else None,
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
                            on_click=open_med_setup,
                        ),
                    ],
                    spacing=8,
                ),
                bgcolor=theme.DANGER,
                border_radius=14,
                padding=ft.Padding.symmetric(vertical=8, horizontal=14),
            )
        ]


    display_name = storage.display_name()
    today_log = storage.today_mood() or {}
    energy_level = int(today_log.get("energy") or storage.today_energy() or 3)
    companion_mood, companion_message = _home_companion(energy_level)

    greeting = ft.Container(
        width=HOME_CONTENT_WIDTH,
        height=74,
        content=ft.Stack(
            [
                ft.Text(
                    f"Hai! {display_name}",
                    color=HOME_TEXT,
                    size=32,
                    weight=ft.FontWeight.W_900,
                    font_family=HOME_FONT,
                    style=ft.TextStyle(letter_spacing=1.1),
                    left=0,
                    top=30,
                ),
                ft.Row(
                    [
                        *(
                            [
                                ft.IconButton(
                                    icon=ft.Icons.SCIENCE_OUTLINED,
                                    icon_color="#DDE0FF",
                                    icon_size=18,
                                    tooltip="Alat Demo",
                                    on_click=lambda e: navigate("demo_tools"),
                                )
                            ]
                            if config.DEMO_MODE
                            else []
                        ),
                        ft.IconButton(
                            icon=ft.Icons.SETTINGS,
                            icon_color="#DDE0FF",
                            icon_size=20,
                            tooltip="Pengaturan",
                            on_click=lambda e: navigate("settings"),
                        ),
                    ],
                    spacing=0,
                    tight=True,
                    right=0,
                    top=0,
                ),
            ],
        ),
    )

    kalem_block = ft.Container(
        width=HOME_CONTENT_WIDTH,
        height=153,
        alignment=ft.Alignment.CENTER,
        content=ft.Row(
            [
                ft.Image(
                    src=buddy.asset_for(companion_mood),
                    width=124,
                    height=135,
                    fit=ft.BoxFit.CONTAIN,
                ),
                ft.Container(
                    width=157,
                    height=79,
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding.symmetric(vertical=10, horizontal=10),
                    bgcolor="#1D2B24",
                    border=ft.Border.all(1, "#95D899"),
                    border_radius=12,
                    shadow=ft.BoxShadow(
                        blur_radius=16,
                        spread_radius=1,
                        color="#4095D899",
                    ),
                    content=ft.Text(
                        companion_message,
                        size=10.5,
                        color=HOME_TEXT,
                        font_family=HOME_FONT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ),
            ],
            spacing=4,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    task_heading = ft.Container(
        width=HOME_CONTENT_WIDTH,
        content=ft.Text(
            (
                "Ayo, Sekarang kerjain ini dulu"
                if has_tasks
                else f"Nggak ada tugas hari ini {display_name},\nEnjoy the Day!"
            ),
            size=19,
            color=HOME_TEXT,
            weight=ft.FontWeight.W_800,
            font_family=HOME_FONT,
        ),
    )


    def take_med(e):
        result = storage.take_medication()
        if result is None and (day.medication or {}).get("enabled", True):
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Stoknya udah abis", size=16),
                    content=ft.Text(
                        "KALEM nggak bisa nyatet absen obat kalau stoknya 0. "
                        "Update dulu stoknya di setelan obat.",
                        size=13,
                    ),
                    actions=[
                        ft.TextButton(content=ft.Text("Nanti"), on_click=lambda ev: page.pop_dialog()),
                        ui_helpers.primary_button(
                            "Ke setelan obat",
                            lambda ev: (page.pop_dialog(), open_med_setup()),
                        ),
                    ],
                )
            )
            return
        navigate("home")

    def start_focus(e):
        task = decision.task or {}
        step_index = decision.step_index
        if task and step_index < 0:
            step_index = storage.ensure_focus_step(
                task.get("id", ""),
                decision.step_text or decision.detail,
                task.get("_occurrence_date") or None,
            )
        if decision.context_event_id:
            storage.mark_reset_followup_used(decision.context_event_id)
        occurrence = task.get("_occurrence_date", "")
        focus_session.start(
            decision.focus_minutes,
            label=decision.step_text or decision.detail,
            task_title=decision.detail,
            kategori=task.get("kategori", ""),
            jumlah_unit=task.get("jumlah_unit", 0),
            energi=storage.today_energy() or 3,
            task_id=task.get("id", ""),
            step_id=storage.task_step_id(
                task.get("id", ""), step_index, occurrence or None
            ),
            occurrence_date=occurrence,
            step_index=step_index,
            decision_id=decision_record_id or "",
            task_estimate_minutes=(
                decision.remaining_minutes
                or int(task.get("menit_est", 0) or 0)
            ),
        )
        navigate("home")

    def choose_rest(e):
        if decision.context_event_id:
            storage.mark_reset_followup_used(decision.context_event_id)
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Istirahat dulu ya", size=16),
                content=ft.Text(
                    "Tugas kamu tetap aman. Tutup ini kalau nanti sudah siap kembali.",
                    size=12.5,
                ),
                actions=[
                    ui_helpers.primary_button(
                        "Oke", lambda ev: page.pop_dialog(), icon=ft.Icons.CHECK
                    )
                ],
            )
        )

    ACTIONS = {
        "med_taken": take_med,
        "reset": lambda e: navigate("reset"),
        "focus": start_focus,
        "add_task": lambda e: navigate("task_add"),
        "rest": choose_rest,
        "pending": lambda e: navigate("daily_checkin"),
    }

    ACTION_ICONS = {
        "med_taken": ft.Icons.CHECK_CIRCLE,
        "reset": ft.Icons.SPA,
        "focus": ft.Icons.PLAY_ARROW,
        "add_task": ft.Icons.ADD,
        "rest": ft.Icons.BEDTIME,
        "pending": ft.Icons.FAVORITE,
    }

    def centered_home_block(content: ft.Control) -> ft.Control:
        return ft.Row(
            [
                ft.Container(
                    width=HOME_CONTENT_WIDTH,
                    content=content,
                )
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )

    def home_action_button(label: str, on_click, icon=None, *, dark: bool = False) -> ft.Control:
        background = "#343446" if dark else HOME_BUTTON
        foreground = "#DDE0FF" if dark else HOME_BUTTON_TEXT
        is_add_task = "tambah tugas" in label.lower()
        return ft.Button(
            height=42,
            content=ft.Text(
                label,
                size=15 if is_add_task else 13,
                color=foreground,
                font_family=HOME_FONT,
                weight=ft.FontWeight.W_700,
            ),
            icon=icon,
            icon_color=foreground,
            style=ft.ButtonStyle(
                bgcolor=background,
                color=foreground,
                padding=0,
                shape=ft.RoundedRectangleBorder(radius=18),
            ),
            on_click=on_click,
        )

    card_children: list[ft.Control] = []
    if decision.kind == "next_action":
        estimate = decision.remaining_minutes or int(
            (decision.task or {}).get("menit_est", 0) or 0
        )
        card_children = [
            ft.Text(
                decision.detail,
                size=14,
                weight=ft.FontWeight.BOLD,
                color="#DDE0FF",
                font_family=HOME_FONT,
            ),
            ft.Row(
                [
                    ft.Icon(ft.Icons.SUBDIRECTORY_ARROW_RIGHT, size=13, color="#DDE0FF"),
                    ft.Text(decision.step_text, size=11.5, color="#DDE0FF", expand=True),
                ],
                spacing=4,
            ),
            ft.Text(
                (
                    f"Sisa estimasi ~{estimate} menit · sesi ini {decision.focus_minutes} menit"
                    if estimate
                    else f"Sesi ini {decision.focus_minutes} menit"
                ),
                size=10.5,
                color="#DDE0FF",
            ),
        ]
        cue, cue_color = deadline_cue(decision.task or {})
        if cue:
            card_children.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.EVENT_OUTLINED, size=13, color="#DDE0FF"),
                        ft.Text(cue, size=10.5, color="#DDE0FF", expand=True),
                    ],
                    spacing=6,
                )
            )
    elif decision.detail and decision.action_kind != "add_task":
        card_children = [
            ft.Text(
                decision.detail,
                size=12.5,
                color="#DDE0FF",
                font_family=HOME_FONT,
                text_align=ft.TextAlign.CENTER,
            )
        ]

    def _aksi_dicatat(e):
        if not storage.record_decision_acted_by_id(decision_record_id):
            storage.record_decision_acted(decision.kind, decision.action_kind)
        ACTIONS.get(decision.action_kind, lambda ev: None)(e)

    card_children.append(
        home_action_button(
            decision.action_label,
            _aksi_dicatat,
            icon=ACTION_ICONS.get(decision.action_kind),
            dark=decision.action_kind == "add_task",
        )
    )
    if decision.action_kind != "add_task" and has_tasks:
        card_children.append(
            home_action_button(
                "+ Tambah Tugas",
                lambda e: navigate("task_add"),
                dark=True,
            )
        )

    action_card = centered_home_block(
        ft.Container(
            bgcolor="#1C1C26",
            border=ft.Border.all(1, "#484863"),
            border_radius=16,
            padding=(
                ft.Padding.symmetric(vertical=5, horizontal=6)
                if decision.action_kind == "add_task"
                else ft.Padding.symmetric(vertical=12, horizontal=14)
            ),
            content=ft.Column(
                card_children,
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        )
    )


    ring = ft.ProgressRing(
        value=1.0, width=210, height=210, stroke_width=12,
        color="#FFBD91", bgcolor="#171719",
    )
    clock_text = ft.Text("", size=42, weight=ft.FontWeight.BOLD,
                         color=HOME_TEXT, font_family=HOME_FONT)
    sub_text = ft.Text("", size=11, color=HOME_TEXT, text_align=ft.TextAlign.CENTER)
    step_text = ft.Text("", size=16, weight=ft.FontWeight.BOLD, color=HOME_TEXT,
                        text_align=ft.TextAlign.LEFT, expand=True)
    task_title_text = ft.Text(
        "", size=10.5, color=HOME_TEXT, text_align=ft.TextAlign.RIGHT, width=92
    )
    focus_progress = ft.ProgressBar(
        value=0,
        color="#91A8FF",
        bgcolor="#171719",
        bar_height=10,
        border_radius=8,
        expand=True,
    )
    focus_progress_text = ft.Text(
        "0%", size=14, weight=ft.FontWeight.BOLD, color="#91A8FF"
    )
    controls_row = ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=8,
    )

    def toggle_pause(e):
        if focus_session.is_running():
            focus_session.pause()
        else:
            focus_session.resume()
        refresh_focus()

    def restart_focus(e):
        focus_session.reset()
        focus_session.resume()
        refresh_focus()

    def save_outcome(outcome: str, reflection: str = "") -> None:
        continued = False
        if outcome == "completed":
            record, continued = focus_session.complete_and_continue(
                rendered_session_started_at
            )
            if record is not None:
                ui_helpers.reward_overlay(
                    page,
                    "Step beres. Lanjut yang berikutnya!" if continued else "",
                )
        else:
            focus_session.finish(outcome, reflection)
        navigate("home")

    def ask_blocker(e) -> None:
        note = ft.TextField(
            label="Apa yang menghambat? (opsional)",
            multiline=True,
            min_lines=2,
            max_lines=4,
        )

        def submit(ev) -> None:
            page.pop_dialog()
            save_outcome("blocked", note.value or "")

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Tadi terhambat di mana?", size=16),
                content=note,
                actions=[
                    ft.TextButton(
                        content=ft.Text("Lewati"),
                        on_click=lambda ev: (page.pop_dialog(), save_outcome("blocked")),
                    ),
                    ui_helpers.primary_button("Simpan", submit, icon=ft.Icons.CHECK),
                ],
            )
        )

    def ask_duration(e) -> None:
        current = focus_session.snapshot()
        current_minutes = min(30, max(1, current["total_seconds"] // 60))
        duration = ft.TextField(
            label="Durasi sesi (menit)",
            value=str(current_minutes),
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
            helper="Isi 1 - 30 Menit yaa",
            helper_style=ft.TextStyle(color=theme.MUTED),
            filled=True,
            bgcolor="#343446",
            color=theme.ON_BACKGROUND,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            label_style=ft.TextStyle(color=theme.ON_BACKGROUND),
        )

        def submit(ev) -> None:
            try:
                minutes = int((duration.value or "").strip())
            except ValueError:
                duration.error = "Masukkan angka menit yang valid"
                page.update()
                return
            if not focus_session.update_duration(minutes):
                duration.error = (
                    "Pilih 1 - 30 menit dan jangan lebih pendek dari waktu yang sudah berjalan"
                )
                page.update()
                return
            page.pop_dialog()
            refresh_focus()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor="#1C1C26",
                title=ft.Text(
                    "Edit waktu fokus",
                    size=17,
                    color=theme.ON_BACKGROUND,
                    weight=ft.FontWeight.BOLD,
                ),
                content=duration,
                actions=[
                    ft.TextButton(
                        content=ft.Text("Batal", color=theme.ON_BACKGROUND),
                        on_click=lambda ev: page.pop_dialog(),
                    ),
                    ui_helpers.primary_button("Simpan durasi", submit),
                ],
            )
        )

    def outcome_buttons(*, close_dialog: bool = False) -> list[ft.Control]:
        def resolve(outcome: str):
            def handler(e) -> None:
                if close_dialog:
                    page.pop_dialog()
                save_outcome(outcome)

            return handler

        def blocked(e) -> None:
            if close_dialog:
                page.pop_dialog()
            ask_blocker(e)

        return [
            ui_helpers.primary_button(
                "Sudah selesai", resolve("completed"), icon=ft.Icons.CHECK
            ),
            ft.OutlinedButton(
                content=ft.Text("Masih butuh waktu"),
                on_click=resolve("incomplete"),
            ),
            ft.OutlinedButton(content=ft.Text("Terhambat"), on_click=blocked),
            ft.OutlinedButton(
                content=ft.Text("Butuh istirahat"),
                icon=ft.Icons.BEDTIME_OUTLINED,
                on_click=resolve("rest"),
            ),
            ft.TextButton(
                content=ft.Text("Lanjut nanti"),
                on_click=resolve("later"),
            ),
        ]

    def finish_session(e):
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Gimana hasil fokusnya?", size=16),
                content=ft.Column(outcome_buttons(close_dialog=True), spacing=8, tight=True),
                actions=[
                    ft.TextButton(
                        content=ft.Text("Kembali"), on_click=lambda ev: page.pop_dialog()
                    )
                ],
            )
        )

    def refresh_focus():
        s = focus_session.snapshot()
        if not s["active"]:
            return

        ring.value = s["progress"]
        clock_text.value = s["clock"]
        step_text.value = s["label"] or "Sesi fokus"
        task_title_text.value = f"Dari\n{s['task_title']}" if s["task_title"] else ""
        completed_progress = max(0.0, min(1.0, 1.0 - float(s["progress"])))
        focus_progress.value = completed_progress
        focus_progress_text.value = f"{round(completed_progress * 100)}%"
        if s["finished"]:
            ring.color = theme.SUCCESS
            clock_text.value = "Selesai"
            sub_text.value = "Nggak usah langsung lanjut."
        elif s["running"]:
            ring.color = "#FFBD91"
            sub_text.value = "Satu sesi aja dulu."
        else:
            ring.color = theme.WARN
            sub_text.value = "Nggak apa-apa berhenti sebentar."

        buttons: list[ft.Control] = []
        if not s["finished"]:
            buttons.extend(
                [
                    ft.OutlinedButton(
                        content=ft.Icon(
                            ft.Icons.PAUSE if s["running"] else ft.Icons.PLAY_ARROW,
                            color="#FFBD91",
                        ),
                        tooltip="Jeda" if s["running"] else "Lanjut",
                        style=ft.ButtonStyle(side=ft.BorderSide(1, "#6D5545")),
                        on_click=toggle_pause,
                        expand=True,
                    ),
                    ft.OutlinedButton(
                        content=ft.Icon(ft.Icons.REPLAY, color="#FFBD91"),
                        tooltip="Ulangi sesi",
                        style=ft.ButtonStyle(side=ft.BorderSide(1, "#6D5545")),
                        on_click=restart_focus,
                        expand=True,
                    ),
                    ft.Button(
                        content=ft.Text(
                            "Sudahi", color="#2B211B", weight=ft.FontWeight.BOLD
                        ),
                        bgcolor="#FFBD91",
                        on_click=finish_session,
                        expand=True,
                    ),
                ]
            )
        else:
            buttons.append(
                ui_helpers.primary_button("Lihat hasil sesi", finish_session, expand=True)
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

    focus_card = centered_home_block(
        ft.Container(
            bgcolor="#302A27",
            border=ft.Border.all(1, "#6D5545"),
            border_radius=20,
            padding=16,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            step_text,
                            task_title_text,
                            ft.TextButton(
                                content=ft.Text(
                                    "Edit",
                                    size=11,
                                    color="#FFBD91",
                                    weight=ft.FontWeight.BOLD,
                                ),
                                icon=ft.Icons.EDIT_CALENDAR_OUTLINED,
                                tooltip="Edit waktu",
                                on_click=ask_duration,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
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
                                    width=210,
                                    height=210,
                                    alignment=ft.Alignment.CENTER,
                                    padding=ft.Padding.symmetric(vertical=0, horizontal=24),
                                ),
                            ],
                            width=210,
                            height=210,
                        ),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Row([focus_progress, focus_progress_text], spacing=10),
                    controls_row,
                ],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
    )
    focus_heading = centered_home_block(
        ft.Text(
            "Sesi fokus:",
            size=24,
            color=HOME_TEXT,
            font_family=HOME_FONT,
            weight=ft.FontWeight.W_800,
        )
    )

    if session_active:
        ticker_state["refresh"] = refresh_focus
        refresh_focus()


    def open_capture(e):
        note_field = ft.TextField(
            hint_text="Tulis apa pun di sini...",
            multiline=True,
            min_lines=3,
            max_lines=6,
            autofocus=True,
            text_size=14,
            color="#DDE0FF",
            bgcolor="#343446",
            border_color="#484863",
            focused_border_color="#DDE0FF",
            border_radius=14,
            cursor_color="#DDE0FF",
            hint_style=ft.TextStyle(
                color="#9292A9",
                size=13,
                font_family=HOME_FONT,
            ),
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
                bgcolor="#1C1C26",
                shape=ft.RoundedRectangleBorder(radius=22),
                title_padding=ft.Padding(left=24, top=26, right=24, bottom=10),
                content_padding=ft.Padding(left=24, top=4, right=24, bottom=10),
                actions_padding=ft.Padding(left=24, top=8, right=24, bottom=22),
                title=ft.Text(
                    "Apapun yang kamu mau ingat",
                    size=28,
                    color="#DDE0FF",
                    font_family=HOME_FONT,
                    weight=ft.FontWeight.W_900,
                    style=ft.TextStyle(letter_spacing=0.5),
                ),
                content=ft.Column(
                    [
                        ft.Text(
                            "Kamu boleh tulis apapun, tugas, cerita, atau apapun itu",
                            size=13,
                            color="#DDE0FF",
                            font_family=HOME_FONT,
                        ),
                        note_field,
                    ],
                    width=280,
                    spacing=12,
                    tight=True,
                ),
                actions=[
                    ft.OutlinedButton(
                        width=100,
                        height=42,
                        content=ft.Text(
                            "Batal",
                            color="#DDE0FF",
                            weight=ft.FontWeight.W_700,
                            font_family=HOME_FONT,
                        ),
                        style=ft.ButtonStyle(
                            side=ft.BorderSide(1, "#DDE0FF"),
                            shape=ft.RoundedRectangleBorder(radius=18),
                        ),
                        on_click=lambda ev: page.pop_dialog(),
                    ),
                    ft.Button(
                        width=176,
                        height=42,
                        content=ft.Text(
                            "Simpan",
                            color="#181A35",
                            weight=ft.FontWeight.W_800,
                            font_family=HOME_FONT,
                        ),
                        style=ft.ButtonStyle(
                            bgcolor="#DDE0FF",
                            shape=ft.RoundedRectangleBorder(radius=18),
                        ),
                        on_click=save,
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
        )

    inbox_count = len(storage.get_inbox())

    capture_children: list[ft.Control] = [
        ft.Icon(ft.Icons.EDIT_OUTLINED, color="#181A35", size=17),
        ft.Container(
            content=ft.Text(
                "Ada yang Keingat?",
                size=12,
                color="#181A35",
                font_family=HOME_FONT,
                weight=ft.FontWeight.W_600,
            ),
            expand=True,
            on_click=open_capture,
        ),
    ]
    if inbox_count:
        capture_children.append(
            ft.Container(
                content=ft.Text(
                    f"{inbox_count} tersimpan",
                    size=9,
                    color="#DDE0FF",
                    weight=ft.FontWeight.BOLD,
                ),
                bgcolor="#343446",
                border_radius=100,
                padding=ft.Padding.symmetric(vertical=4, horizontal=8),
                on_click=lambda e: navigate("inbox"),
            )
        )

    capture_row = centered_home_block(
        ft.Container(
            height=38,
            bgcolor="#DDE0FF",
            border_radius=18,
            padding=ft.Padding.symmetric(vertical=5, horizontal=11),
            content=ft.Row(capture_children, spacing=7),
            on_click=open_capture,
            ink=True,
        )
    )


    sos_row = centered_home_block(
        ft.Stack(
            [
                ft.Container(
                    left=0,
                    top=0,
                    width=HOME_CONTENT_WIDTH,
                    height=38,
                    content=ft.Text(
                        "Kewalahan? YUK AMBIL JEDA",
                        size=11.5,
                        color="#17153A",
                        font_family=HOME_FONT,
                        weight=ft.FontWeight.W_700,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    alignment=ft.Alignment.CENTER,
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment.CENTER_LEFT,
                        end=ft.Alignment.CENTER_RIGHT,
                        colors=["#95D899", "#95D899", "#AEEEF8"],
                        stops=[0.0, 0.8, 1.0],
                    ),
                    border_radius=18,
                    padding=ft.Padding(left=46, top=4, right=8, bottom=4),
                    on_click=lambda e: navigate("reset"),
                    ink=True,
                ),
                ft.Image(
                    src="kalem_cemas.svg",
                    left=-12,
                    top=-14,
                    width=65,
                    height=65,
                    fit=ft.BoxFit.CONTAIN,
                ),
            ],
            width=HOME_CONTENT_WIDTH,
            height=38,
            clip_behavior=ft.ClipBehavior.NONE,
        )
    )

    home_controls = [*sim_banner, *med_banner]
    if session_active:
        home_controls.extend([focus_heading, focus_card, capture_row])
    else:
        home_controls.extend(
            [
                greeting,
                kalem_block,
                task_heading,
                *([] if hide_empty_add_action else [action_card]),
                capture_row,
                sos_row,
            ]
        )
    layout = ft.Container(
        bgcolor=HOME_BACKGROUND,
        content=ft.Column(
            [
                ft.Column(
                    home_controls,
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(
                    width=HOME_CONTENT_WIDTH,
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding(left=4, top=2, right=4, bottom=0),
                    content=ft.Text(
                        "FocusBuddy bukan alat diagnosis dan bukan pengganti tenaga medis",
                        size=10.5,
                        color="#DDE0FF",
                        font_family=HOME_FONT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ),
            ],
            spacing=6,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=True,
    )

    if session_active:
        page.run_task(ticker)

    return layout
