"""Tracker tugas, kalender, dan pecah tugas."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

import flet as ft

from app import clock, focus_session, storage, theme, ui_helpers
from app.core import kalem_engine
from models import fitur as kfitur
from models import model_durasi
from app.core.decomposer_logic import lay_out, plan_today
from app.core.energy_predictor import energy_to_mood_default

MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]
DAY_INITIALS = ["S", "S", "R", "K", "J", "S", "M"]

QUADRANT_META = {
    "lakukan": ("Lakukan sekarang", theme.DANGER),
    "jadwalkan": ("Jadwalkan", theme.PRIMARY),
    "delegasikan": ("Bisa didelegasikan", theme.SECONDARY),
    "nanti": ("Nanti aja", theme.MUTED),
}

DIFFICULTY_LABELS = {1: "Gampang", 2: "Sedang", 3: "Berat"}


def build(page: ft.Page, navigate) -> ft.Control:
    today = clock.today()
    latest_mood = storage.latest_mood()
    default_energy = energy_to_mood_default(latest_mood["score"]) if latest_mood else 3

    locked_energy = storage.today_energy()
    if locked_energy:
        default_energy = locked_energy

    state = {
        "month": today.month,
        "year": today.year,
        "selected": today.isoformat(),
        "energy": default_energy,
        "show_month": False,
        "time_filter": "weekly",
    }

    plan_state: dict = {"steps": [], "source": "", "reason": "", "quota_msg": "",
                        "n_lokal": 0, "n_ai": 0}

    calendar_grid = ft.Column(spacing=6)
    month_label = ft.Text(size=15, weight=ft.FontWeight.BOLD, color=theme.ON_BACKGROUND)
    calendar_nav = ft.Row(spacing=0)
    day_tasks_column = ft.Column(spacing=8)
    eisenhower_column = ft.Column(spacing=8)
    timeline_column = ft.Column(spacing=8)
    plan_column = ft.Column(spacing=8, visible=False)
    next_action_holder = ft.Container(visible=False)


    def day_has_task(day_iso: str) -> bool:
        return bool(storage.tasks_for(day_iso))

    def select_day(day_iso: str):
        state["selected"] = day_iso
        state["time_filter"] = "daily"
        render_calendar()
        render_time_filter()
        render_day_tasks()
        render_eisenhower()
        render_timeline()
        page.update()

    def day_cell(day, in_month: bool) -> ft.Control:
        iso = day.isoformat()
        selected = iso == state["selected"]
        is_today = day == today

        if selected:
            bg, fg = theme.PRIMARY, "#FFFFFF"
        elif is_today:
            bg, fg = theme.SURFACE, theme.PRIMARY
        else:
            bg, fg = "#00000000", (theme.ON_BACKGROUND if in_month else theme.BORDER)

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        str(day.day),
                        size=12.5,
                        color=fg,
                        weight=ft.FontWeight.BOLD if (selected or is_today) else ft.FontWeight.NORMAL,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(
                        width=4,
                        height=4,
                        bgcolor=(
                            ("#FFFFFF" if selected else theme.TERTIARY)
                            if (in_month and day_has_task(iso))
                            else "#00000000"
                        ),
                        border_radius=2,
                    ),
                ],
                spacing=1,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            height=42,
            expand=True,
            bgcolor=bg,
            border=ft.Border.all(1, theme.PRIMARY) if is_today and not selected else None,
            border_radius=10,
            alignment=ft.Alignment.CENTER,
            on_click=(lambda e, d=iso: select_day(d)) if in_month else None,
            ink=in_month,
        )

    def render_calendar():
        if state["show_month"]:
            year, month = state["year"], state["month"]
            month_label.value = f"{MONTH_NAMES[month - 1]} {year}"
            rows: list[ft.Control] = [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(d, size=11, color=theme.MUTED, text_align=ft.TextAlign.CENTER),
                            expand=True,
                            alignment=ft.Alignment.CENTER,
                        )
                        for d in DAY_INITIALS
                    ],
                    spacing=4,
                )
            ]
            for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
                rows.append(ft.Row([day_cell(d, d.month == month) for d in week], spacing=4))
            calendar_grid.controls = rows
            calendar_nav.controls = [
                ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, icon_color=theme.MUTED,
                              on_click=lambda e: shift_month(-1)),
                ft.Container(content=month_label, expand=True, alignment=ft.Alignment.CENTER),
                ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_color=theme.MUTED,
                              on_click=lambda e: shift_month(1)),
            ]
        else:
            start = today - timedelta(days=today.weekday())
            week = [start + timedelta(days=i) for i in range(7)]
            month_label.value = f"{MONTH_NAMES[today.month - 1]} {today.year}"
            calendar_grid.controls = [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(DAY_INITIALS[i], size=10, color=theme.MUTED,
                                            text_align=ft.TextAlign.CENTER),
                            expand=True,
                            alignment=ft.Alignment.CENTER,
                        )
                        for i in range(7)
                    ],
                    spacing=4,
                ),
                ft.Row([day_cell(d, True) for d in week], spacing=4),
            ]
            calendar_nav.controls = [
                ft.Container(content=month_label, expand=True),
                ft.TextButton(
                    content=ft.Text("Lihat bulan", size=12, color=theme.PRIMARY),
                    on_click=lambda e: toggle_month(True),
                ),
            ]

    def toggle_month(show: bool):
        state["show_month"] = show
        render_calendar()
        page.update()

    def shift_month(delta: int):
        month = state["month"] + delta
        year = state["year"]
        if month < 1:
            month, year = 12, year - 1
        elif month > 12:
            month, year = 1, year + 1
        state["month"], state["year"] = month, year
        render_calendar()
        if state["time_filter"] == "monthly":
            render_day_tasks()
        page.update()


    def quadrant_chip(key: str, count: int) -> ft.Container:
        label, color = QUADRANT_META[key]
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(str(count), size=20, weight=ft.FontWeight.BOLD, color=color),
                    ft.Text(label, size=10, color=theme.MUTED, text_align=ft.TextAlign.CENTER),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            expand=True,
            padding=ft.Padding.symmetric(vertical=12, horizontal=6),
            bgcolor=theme.SURFACE,
            border=ft.Border.all(1, theme.BORDER),
            border_radius=14,
        )

    def render_eisenhower():
        buckets = storage.eisenhower_summary(state["selected"])
        eisenhower_column.controls = [
            ui_helpers.section_header("Sebaran tugas"),
            ft.Row([quadrant_chip(k, len(buckets[k])) for k in ["lakukan", "jadwalkan"]], spacing=10),
            ft.Row([quadrant_chip(k, len(buckets[k])) for k in ["delegasikan", "nanti"]], spacing=10),
        ]


    def render_timeline():
        tasks = [t for t in storage.tasks_for(state["selected"]) if not storage.task_is_done(t)]
        if not tasks:
            timeline_column.controls = []
            return

        order = {"lakukan": 0, "delegasikan": 1, "jadwalkan": 2, "nanti": 3}
        tasks.sort(key=lambda t: (order.get(storage.quadrant_of(t), 9), t.get("difficulty_est", 2)))

        bars = [
            ft.Container(
                expand=max(t.get("difficulty_est", 2), 1),
                height=10,
                bgcolor=QUADRANT_META[storage.quadrant_of(t)][1],
                border_radius=5,
                tooltip=t["title"],
            )
            for t in tasks
        ]
        labels = [
            ft.Row(
                [
                    ft.Container(
                        width=8,
                        height=8,
                        bgcolor=QUADRANT_META[storage.quadrant_of(t)][1],
                        border_radius=4,
                    ),
                    ft.Text(t["title"], size=11.5, color=theme.ON_BACKGROUND, expand=True),
                    ft.Text(
                        DIFFICULTY_LABELS.get(t.get("difficulty_est", 2), ""),
                        size=10,
                        color=theme.MUTED,
                    ),
                ],
                spacing=8,
            )
            for t in tasks
        ]
        timeline_column.controls = [
            ui_helpers.section_header("Urutan yang disaranin"),
            ft.Row(bars, spacing=4),
            *labels,
        ]


    filter_holder = ft.Row(spacing=6)

    def set_time_filter(value: str):
        state["time_filter"] = value
        render_time_filter()
        render_day_tasks()
        page.update()

    def render_time_filter():
        labels = [("daily", "Harian"), ("weekly", "Mingguan"), ("monthly", "Bulanan")]
        filter_holder.controls = [
            ui_helpers.choice_chip(
                label, state["time_filter"] == key,
                lambda e, value=key: set_time_filter(value),
            )
            for key, label in labels
        ]

    def tasks_in_filter() -> list[dict]:
        mode = state["time_filter"]
        if mode == "daily":
            return storage.tasks_for(state["selected"])
        if mode == "weekly":
            selected = date.fromisoformat(state["selected"])
            start = selected - timedelta(days=selected.weekday())
            return [task for i in range(7) for task in storage.tasks_for((start + timedelta(days=i)).isoformat())]
        year, month = state["year"], state["month"]
        days = calendar.monthrange(year, month)[1]
        return [
            task
            for day in range(1, days + 1)
            for task in storage.tasks_for(date(year, month, day).isoformat())
        ]

    def toggle_step(task_id: str, index: int, value: bool, occurrence_date: str | None = None):
        before_task = next((t for t in tasks_in_filter() if t["id"] == task_id and
                            t.get("_occurrence_date") == occurrence_date), None)
        sebelum = storage.task_is_done(before_task) if before_task else False
        storage.set_step_done(task_id, index, value, occurrence_date)
        after_task = next((t for t in storage.tasks_for(occurrence_date) if t["id"] == task_id), None) \
            if occurrence_date else next((t for t in storage.get_tasks() if t["id"] == task_id), None)
        sesudah = storage.task_is_done(after_task) if after_task else False
        profile, day = kalem_engine.snapshot()
        next_decision = kalem_engine.decide(profile, day)
        next_action_holder.data = {
            "kind": next_decision.kind,
            "task_id": next_decision.task.get("id") if next_decision.task else None,
        }
        next_action_holder.content = ui_helpers.banner(
            "Progres tersimpan. KALEM sudah menilai ulang kondisimu — "
            "lihat satu langkah berikutnya di Beranda.",
            theme.SUCCESS,
            ft.Icons.AUTO_AWESOME,
        )
        next_action_holder.visible = True
        refresh_all()
        if sesudah and not sebelum:
            ui_helpers.reward_overlay(page)

    def reopen_task(task_id: str, occurrence_date: str | None = None):
        tasks = storage.tasks_for(occurrence_date) if occurrence_date else storage.get_tasks()
        for task in tasks:
            if task["id"] == task_id:
                for i in range(len(task.get("steps", []))):
                    storage.set_step_done(task_id, i, False, occurrence_date)
                break
        refresh_all()

    def confirm_remove(task: dict):
        def do_delete(ev):
            page.pop_dialog()
            storage.delete_task(task["id"])
            refresh_all()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Hapus tugas ini?", size=16),
                content=ft.Text(
                    f"“{task['title']}” bakal dihapus beserta langkah-langkahnya. "
                    "Nggak bisa dibalikin.",
                    size=13,
                ),
                actions=[
                    ft.TextButton(content=ft.Text("Batal"), on_click=lambda ev: page.pop_dialog()),
                    ft.ElevatedButton(
                        content=ft.Text("Hapus", weight=ft.FontWeight.BOLD),
                        bgcolor=theme.DANGER,
                        color="#FFFFFF",
                        elevation=0,
                        on_click=do_delete,
                    ),
                ],
            )
        )

    def done_card(task: dict) -> ft.Control:
        return ui_helpers.card(
            ft.Row(
                [
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=theme.SUCCESS, size=20),
                    ft.Text(
                        task["title"],
                        size=13.5,
                        weight=ft.FontWeight.BOLD,
                        color=theme.MUTED,
                        expand=True,
                    ),
                    ft.Container(
                        content=ft.Text("SELESAI", size=9, weight=ft.FontWeight.BOLD,
                                        color="#FFFFFF"),
                        bgcolor=theme.SUCCESS,
                        border_radius=8,
                        padding=ft.Padding.symmetric(vertical=3, horizontal=7),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.UNDO,
                        icon_color=theme.MUTED,
                        icon_size=17,
                        tooltip="Buka lagi",
                        on_click=lambda e, t=task: reopen_task(t["id"], t.get("_occurrence_date")),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=theme.MUTED,
                        icon_size=17,
                        tooltip="Hapus tugas",
                        on_click=lambda e, t=task: confirm_remove(t),
                    ),
                ],
                spacing=6,
            ),
            padding=12,
        )

    def open_card(task: dict) -> ft.Control:
        label, color = QUADRANT_META[storage.quadrant_of(task)]
        steps = task.get("steps", [])
        done_count = sum(1 for s in steps if s.get("done"))

        step_controls: list[ft.Control] = [
            ft.Checkbox(
                label=step["text"],
                value=step.get("done", False),
                on_change=lambda e, tid=task["id"], i=i, od=task.get("_occurrence_date"): toggle_step(tid, i, e.control.value, od),
            )
            for i, step in enumerate(steps)
        ]

        head: list[ft.Control] = [
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(task["title"], size=14, weight=ft.FontWeight.BOLD,
                                    color=theme.ON_BACKGROUND),
                            ft.Text(
                                f"{label} · {DIFFICULTY_LABELS.get(task.get('difficulty_est', 2), '')}"
                                + {"daily": " · tiap hari", "weekly": " · tiap minggu", "monthly": " · tiap bulan"}.get(task.get("repeat", "none"), "")
                                + (f" · {done_count}/{len(steps)} langkah" if len(steps) > 1 else ""),
                                size=10,
                                color=color,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=theme.MUTED,
                        icon_size=18,
                        tooltip="Hapus tugas",
                        on_click=lambda e, t=task: confirm_remove(t),
                    ),
                ],
            )
        ]
        if len(steps) > 1:
            head.append(
                ft.ProgressBar(
                    value=done_count / len(steps),
                    color=theme.PRIMARY,
                    bgcolor=theme.BORDER,
                    bar_height=4,
                )
            )

        if task.get("menit_est"):
            head.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SCHEDULE, size=14, color=theme.SECONDARY),
                        ft.Text(
                            f"~{task['menit_est']} menit",
                            size=11, color=theme.MUTED, expand=True,
                        ),
                        ft.TextButton(
                            content=ft.Text("Mulai", size=11.5, weight=ft.FontWeight.BOLD),
                            icon=ft.Icons.PLAY_ARROW,
                            on_click=lambda e, t=task: start_task_focus(t),
                        ),
                    ],
                    spacing=6,
                )
            )

        return ui_helpers.card(ft.Column([*head, *step_controls], spacing=6), padding=14)

    def start_task_focus(task: dict):
        pending_index, pending = next(
            (
                (index, step["text"])
                for index, step in enumerate(task.get("steps", []))
                if not step.get("done")
            ),
            (-1, task["title"]),
        )
        if pending_index < 0:
            pending = f"Buka bahan yang dibutuhkan untuk {task['title']}"
            pending_index = storage.ensure_focus_step(
                task.get("id", ""), pending, task.get("_occurrence_date") or None
            )
        focus_minutes, _ = kalem_engine.task_focus_minutes(
            task,
            pending_index,
            state["energy"],
            storage.get_focus_records(),
        )
        focus_session.start(
            focus_minutes,
            label=pending,
            task_title=task["title"],
            kategori=task.get("kategori", ""),
            jumlah_unit=task.get("jumlah_unit", 0),
            energi=state["energy"],
            task_id=task.get("id", ""),
            step_id=storage.task_step_id(
                task.get("id", ""),
                pending_index,
                task.get("_occurrence_date") or None,
            ),
            occurrence_date=task.get("_occurrence_date", ""),
            step_index=pending_index,
        )
        navigate("home")

    def render_day_tasks():
        tasks = tasks_in_filter()
        if not tasks:
            empty = {
                "daily": "Belum ada tugas di tanggal ini.",
                "weekly": "Belum ada tugas minggu ini.",
                "monthly": "Belum ada tugas bulan ini.",
            }[state["time_filter"]]
            day_tasks_column.controls = [ui_helpers.empty_state(empty, ft.Icons.EVENT_AVAILABLE)]
            return

        open_tasks = [t for t in tasks if not storage.task_is_done(t)]
        done_tasks = [t for t in tasks if storage.task_is_done(t)]

        items: list[ft.Control] = [open_card(t) for t in open_tasks]
        if done_tasks:
            items.append(
                ui_helpers.section_header(f"Udah kelar ({len(done_tasks)})")
            )
            items.extend(done_card(t) for t in done_tasks)
        day_tasks_column.controls = items

    def refresh_all():
        render_calendar()
        render_day_tasks()
        render_eisenhower()
        render_timeline()
        render_plan()
        page.update()


    def open_add_task(e):
        title_field = ft.TextField(label="Nama tugas", hint_text="mis. Bikin Skripsi Bab 1")
        description_field = ft.TextField(
            label="Deskripsi (opsional)",
            hint_text="mis. bikin proposal buat ikut hackathon kampus, "
                      "temanya bebas, deadline minggu depan",
            multiline=True,
            min_lines=2,
            max_lines=5,
            helper="Diisi -> Pecah Tugas mecah dari SINI, bukan cuma judul",
        )
        time_field = ft.TextField(
            label="Jam kerja / deadline (opsional)",
            hint_text="mis. 17:00",
            helper="Untuk tugas berulang, jam ini ikut berlaku di setiap occurrence",
            on_change=lambda ev: render_estimate(),
        )
        important_check = ft.Checkbox(label="Penting (berdampak besar)", value=True)
        difficulty = ft.RadioGroup(
            value="2",
            content=ft.Row(
                [
                    ft.Radio(value="1", label="Gampang"),
                    ft.Radio(value="2", label="Sedang"),
                    ft.Radio(value="3", label="Berat"),
                ],
                spacing=0,
            ),
        )
        repeat_group = ft.RadioGroup(
            value="none",
            content=ft.Row(
                [
                    ft.Radio(value="none", label="Sekali"),
                    ft.Radio(value="daily", label="Harian"),
                    ft.Radio(value="weekly", label="Mingguan"),
                    ft.Radio(value="monthly", label="Bulanan"),
                ],
                spacing=0,
                wrap=True,
            ),
        )

        picked = {"kategori": "", "jumlah": 0.0, "menit": 0}
        kategori_holder = ft.Container()
        buka_lanjutan = {"on": False}
        jumlah_field = ft.TextField(
            label="Berapa banyak?",
            keyboard_type=ft.KeyboardType.NUMBER,
            visible=False,
            on_change=lambda ev: render_estimate(),
        )
        estimate_holder = ft.Container()

        def pick_kategori(key: str):
            picked["kategori"] = "" if picked["kategori"] == key else key
            render_kategori()
            render_estimate()

        def render_kategori():
            if not buka_lanjutan["on"]:
                kategori_holder.content = ft.TextButton(
                    content=ft.Text("+ Kasih tau jenis & jumlahnya (opsional)",
                                    size=11.5, color=theme.PRIMARY),
                    on_click=lambda ev: (buka_lanjutan.update(on=True), render_kategori(),
                                         render_estimate()),
                )
                return
            chips = [
                ui_helpers.choice_chip(
                    meta["label"], picked["kategori"] == key,
                    lambda ev, k=key: pick_kategori(k),
                )
                for key, meta in model_durasi.KATEGORI.items()
            ]
            kategori_holder.content = ft.Column(
                [
                    ft.Text("Jenis tugasnya apa? Bikin Kalem inget kecepatan kamu "
                            "di jenis ini.", size=11, color=theme.MUTED),
                    ft.Row(chips, spacing=6, wrap=True, run_spacing=6),
                ],
                spacing=6,
            )

        def render_estimate():
            judul = (title_field.value or "").strip()
            kategori = picked["kategori"]

            jumlah_field.visible = bool(kategori) and buka_lanjutan["on"]
            if kategori:
                satuan = model_durasi.satuan_kategori(kategori)
                jumlah_field.label = f"Berapa {satuan}?"
            try:
                picked["jumlah"] = float((jumlah_field.value or "").strip())
            except ValueError:
                picked["jumlah"] = 0.0

            if len(judul) < 3:
                estimate_holder.content = None
                picked["menit"] = 0
                page.update()
                return

            try:
                tempo = max(0, (date.fromisoformat(state["selected"]) - today).days)
            except ValueError:
                tempo = 0
            penting = 8 if important_check.value else 4
            if tempo <= 1:
                penting = min(10, penting + 2)

            est = model_durasi.perkirakan(
                judul,
                tempo_hari=tempo,
                penting=penting,
                kategori=kategori,
                jumlah=picked["jumlah"],
                records=storage.get_focus_records(),
                energi=state["energy"],
            )
            picked["menit"] = est.menit
            estimate_holder.content = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.SCHEDULE, size=16, color=theme.PRIMARY),
                                ft.Text(
                                    f"Biasanya {est.rentang}"
                                    + (f" · {est.sesi} sesi" if est.sesi > 1 else ""),
                                    size=13, weight=ft.FontWeight.BOLD,
                                    color=theme.ON_BACKGROUND, expand=True,
                                ),
                            ],
                            spacing=6,
                        ),
                        ft.Text(est.catatan, size=10.5, color=theme.MUTED),
                    ],
                    spacing=4,
                ),
                bgcolor=theme.BACKGROUND,
                border_radius=10,
                padding=ft.Padding.symmetric(vertical=8, horizontal=10),
            )
            page.update()

        title_field.on_change = lambda ev: render_estimate()
        important_check.on_change = lambda ev: render_estimate()

        render_kategori()
        render_estimate()

        def submit(ev):
            name = (title_field.value or "").strip()
            if not name:
                title_field.error = "Isi nama tugasnya dulu"
                page.update()
                return
            repeat = repeat_group.value or "none"
            storage.add_task(
                name,
                state["selected"],
                important_check.value,
                deadline_time=(time_field.value or "").strip(),
                steps=[{"text": name, "done": False}],
                difficulty_est=int(difficulty.value or 2),
                kategori=picked["kategori"],
                jumlah_unit=picked["jumlah"],
                menit_est=picked["menit"],
                description=(description_field.value or "").strip(),
                repeat=repeat,
            )
            page.pop_dialog()
            refresh_all()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Tugas untuk {state['selected']}", size=16),
                content=ft.Column(
                    [
                        title_field,
                        description_field,
                        time_field,
                        ft.Text("Ulangi tugas", size=11, color=theme.MUTED),
                        repeat_group,
                        important_check,
                        ft.Text("Seberat apa buat dimulai?", size=11, color=theme.MUTED),
                        difficulty,
                        ft.Divider(color=theme.BORDER, height=1),
                        kategori_holder,
                        jumlah_field,
                        estimate_holder,
                    ],
                    spacing=8,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                actions=[
                    ft.TextButton(content=ft.Text("Batal"), on_click=lambda ev: page.pop_dialog()),
                    ui_helpers.primary_button("Tambah", submit),
                ],
            )
        )


    def open_split_picker(e):
        tasks = [t for t in storage.tasks_today() if not storage.task_is_done(t)]
        if not tasks:
            plan_state.update(steps=[], source="", reason="", quota_msg="", n_lokal=0, n_ai=0)
            plan_column.controls = [
                ui_helpers.banner("Belum ada tugas hari ini buat dipecah.",
                                  theme.WARN, ft.Icons.INFO_OUTLINE)
            ]
            plan_column.visible = True
            page.update()
            return

        boxes = {t["id"]: ft.Checkbox(label=t["title"], value=True) for t in tasks}
        extra_fields = {
            t["id"]: ft.TextField(
                label="Langkah tambahan dari kamu (opsional)",
                value="\n".join(t.get("custom_steps", [])),
                hint_text="mis. Ambil pensil",
                helper="Satu baris satu langkah · disisipkan setelah langkah pembuka",
                multiline=True,
                min_lines=1,
                max_lines=3,
            )
            for t in tasks
        }

        def picker_row(task: dict) -> ft.Control:
            box = boxes[task["id"]]
            steps = len(task.get("steps", []))
            rows: list[ft.Control] = [box]
            if steps > 1:
                rows.append(
                    ft.Container(
                        content=ft.Text(
                            f"udah punya {steps} langkah — bakal disusun ulang",
                            size=10.5,
                            color=theme.MUTED,
                        ),
                        padding=ft.Padding.only(left=42),
                    )
                )
            rows.append(
                ft.Container(content=extra_fields[task["id"]], padding=ft.Padding.only(left=42))
            )
            return ft.Column(rows, spacing=4)

        def set_all(value: bool):
            for box in boxes.values():
                box.value = value
            page.update()

        def submit(ev):
            chosen = []
            for task in tasks:
                if not boxes[task["id"]].value:
                    continue
                tambahan = [
                    line.strip(" \t-•*").strip()
                    for line in (extra_fields[task["id"]].value or "").splitlines()
                    if line.strip(" \t-•*").strip()
                ]
                storage.set_task_custom_steps(task["id"], tambahan)
                chosen.append({**task, "custom_steps": tambahan})
            page.pop_dialog()
            if chosen:
                run_split(chosen)

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Pecah tugas mana?", size=16),
                content=ft.Column(
                    [
                        ft.Text(
                            "Cuma yang dicentang yang dipecah. Kamu juga bisa nambah langkah "
                            "sendiri, misalnya ‘Ambil pensil’. Langkah itu tetap disimpan.",
                            size=11.5,
                            color=theme.MUTED,
                        ),
                        ft.Row(
                            [
                                ft.TextButton(content=ft.Text("Pilih semua", size=12),
                                              on_click=lambda ev: set_all(True)),
                                ft.TextButton(content=ft.Text("Kosongkan", size=12),
                                              on_click=lambda ev: set_all(False)),
                            ],
                            spacing=4,
                        ),
                        *[picker_row(t) for t in tasks],
                    ],
                    spacing=6,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                actions=[
                    ft.TextButton(content=ft.Text("Batal"), on_click=lambda ev: page.pop_dialog()),
                    ui_helpers.primary_button("Pecah", submit, icon=ft.Icons.AUTO_AWESOME),
                ],
            )
        )

    def run_split(tasks: list[dict]):
        allow_ai = storage.can_use("decompose")

        progres_holder = ft.Container()
        plan_column.controls = [progres_holder]
        plan_column.visible = True
        page.update()

        async def kerjakan():
            hasil = await ui_helpers.jalankan_dengan_progres(
                page, progres_holder,
                lambda: plan_today(tasks, state["energy"], allow_ai=allow_ai),
                "Kalem lagi mecahin tugasnya...",
            )
            selesaikan(hasil, tasks)

        page.run_task(kerjakan)

    def selesaikan(result, tasks: list[dict]):
        if result.n_ai:
            storage.record_usage("decompose")

        by_title: dict[str, list[dict]] = {}
        for title, step, _minutes in result.steps:
            by_title.setdefault(title, []).append({"text": step, "done": False})
        for task in tasks:
            steps = result.task_steps.get(task["id"]) if result.task_steps else by_title.get(task["title"])
            if steps:
                storage.set_task_steps(task["id"], steps, task.get("_occurrence_date"))

        left = storage.quota_left("decompose")
        plan_state.update(
            steps=list(result.steps),
            source=result.source,
            reason=result.reason,
            quota_msg=f" — sisa {left}x hari ini" if left is not None else "",
            n_lokal=result.n_lokal,
            n_ai=result.n_ai,
        )
        refresh_all()

    def render_plan():
        if not plan_state["steps"]:
            if not plan_column.controls:
                plan_column.visible = False
            return

        alive = {t["title"] for t in storage.tasks_today()}
        steps = [s for s in plan_state["steps"] if s[0] in alive]
        removed = len(plan_state["steps"]) - len(steps)
        plan_state["steps"] = steps

        if not steps:
            plan_column.controls = [
                ui_helpers.banner(
                    "Semua tugas di rencana ini udah dihapus.", theme.MUTED, ft.Icons.INFO_OUTLINE
                )
            ]
            plan_column.visible = True
            return

        blocks, total = lay_out(steps, state["energy"])

        n_lokal = plan_state.get("n_lokal", 0)
        n_ai = plan_state.get("n_ai", 0)

        if plan_state["source"] == "ai":
            label = "Disusun oleh Kalem" + plan_state["quota_msg"]
            rows: list[ft.Control] = [
                ui_helpers.banner(label, theme.PRIMARY, ft.Icons.AUTO_AWESOME)
            ]
        elif plan_state["source"] == "lokal":
            rows = [
                ui_helpers.banner(
                    "Disusun dari pola Kalem — hemat kuota", theme.SUCCESS, ft.Icons.BOLT
                )
            ]
        elif plan_state["source"] == "campuran":
            if n_ai:
                rows = [ui_helpers.banner(
                    "Disusun dari catatan kamu + Kalem" + plan_state["quota_msg"],
                    theme.PRIMARY, ft.Icons.AUTO_AWESOME,
                )]
            else:
                label = "Sebagian dari catatan kamu, sisanya template Kalem"
                rows = [ui_helpers.banner(label, theme.WARN, ft.Icons.OFFLINE_BOLT)]
        else:
            label = "Disusun dengan template Kalem"
            rows = [ui_helpers.banner(label, theme.WARN, ft.Icons.OFFLINE_BOLT)]

        if n_lokal and n_ai:
            rows.append(
                ft.Text(
                    f"{n_lokal} tugas dari catatan lama/outline kamu, "
                    f"{n_ai} tugas baru disusun Kalem.",
                    size=11, color=theme.MUTED,
                )
            )
        elif n_lokal and plan_state["source"] == "lokal":
            rows.append(
                ft.Text(
                    f"{n_lokal} tugas kelayanin dari catatan lama/outline kamu — "
                    "nggak perlu penyusunan generatif.",
                    size=11, color=theme.MUTED,
                )
            )

        if removed:
            rows.append(
                ft.Text(
                    f"{removed} langkah dibuang karena tugasnya udah dihapus — "
                    "jadwalnya udah disusun ulang.",
                    size=11,
                    color=theme.MUTED,
                )
            )

        for block in blocks:
            rows.append(
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(
                                block.start,
                                size=11,
                                color=theme.MUTED if block.is_break else theme.PRIMARY,
                                weight=ft.FontWeight.BOLD,
                            ),
                            width=44,
                        ),
                        ft.Container(
                            width=3,
                            height=26,
                            bgcolor=theme.BORDER if block.is_break else theme.PRIMARY,
                            border_radius=2,
                        ),
                        ft.Text(
                            block.step,
                            size=12.5,
                            color=theme.MUTED if block.is_break else theme.ON_BACKGROUND,
                            italic=block.is_break,
                            expand=True,
                        ),
                    ],
                    spacing=8,
                )
            )
        rows.append(
            ui_helpers.disclaimer(
                f"Total sekitar {total} menit. Ini rencana, bukan target wajib."
            )
        )
        plan_column.controls = rows
        plan_column.visible = True


    render_calendar()
    render_time_filter()
    render_day_tasks()
    render_eisenhower()
    render_timeline()

    calendar_card = ui_helpers.card(
        ft.Column([calendar_nav, calendar_grid], spacing=8), padding=14
    )

    return ft.Column(
        [
            ui_helpers.page_header("Tracker"),
            calendar_card,
            filter_holder,
            ft.Row(
                [
                    ui_helpers.primary_button("Tambah Tugas", open_add_task, icon=ft.Icons.ADD, expand=True),
                    ft.OutlinedButton(
                        content=ft.Text("Pecah Tugas"),
                        icon=ft.Icons.AUTO_AWESOME,
                        on_click=open_split_picker,
                        expand=True,
                    ),
                ],
                spacing=10,
            ),
            ui_helpers.subtitle("'Pecah Tugas' nyusun tugas HARI INI jadi slot waktu — kamu pilih yang mana."),
            plan_column,
            next_action_holder,
            eisenhower_column,
            timeline_column,
            day_tasks_column,
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
