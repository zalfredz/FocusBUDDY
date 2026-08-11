"""Halaman jeda dan bantuan saat pengguna overwhelm."""
from __future__ import annotations

import asyncio
import random
from typing import Optional

import flet as ft

from app import buddy, storage, theme, ui_helpers
from app.core.reset_preferences import (
    CRISIS_HOTLINES,
    OPTIONS,
    TELEHEALTH_PARTNERS,
    detect_distress,
    music_links,
)
from models import model_penenang

MOVE_ACTIONS = [
    "Berdiri, regangin badan 60 detik.",
    "Jalan bolak-balik di kamar, 60 detik aja.",
    "Puter bahu ke belakang 10 kali, pelan.",
    "Buka jendela, hirup udara luar sebentar.",
    "Cuci muka pakai air dingin.",
    "Minum segelas air putih sampai habis.",
]

BREATHING_STEPS = [
    ("Tarik napas...", 4, 1.0),
    ("Tahan...", 7, 1.0),
    ("Buang pelan-pelan...", 8, 0.55),
]

GROUNDING_STEPS = [
    (5, "hal yang bisa kamu LIHAT", ft.Icons.VISIBILITY),
    (4, "hal yang bisa kamu SENTUH", ft.Icons.BACK_HAND),
    (3, "suara yang bisa kamu DENGER", ft.Icons.HEARING),
    (2, "bau yang bisa kamu CIUM", ft.Icons.AIR),
    (1, "hal yang kamu SYUKURIN hari ini", ft.Icons.FAVORITE),
]


def build(page: ft.Page, navigate) -> ft.Control:
    body = ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    profile = storage.get_profile()
    favorites = storage.get_favorites()
    distress = detect_distress(storage.get_reset_events(), storage.get_mood_logs())
    prefs = model_penenang.peringkat(
        storage.get_reset_events(), storage.get_mood_logs(), storage.all_triggers(profile)
    )

    reset_event_id = ""

    def log_once(choice: str):
        nonlocal reset_event_id
        if not reset_event_id:
            reset_event_id = storage.add_reset_event(choice)["id"]

    def show_outcome() -> None:
        if not reset_event_id:
            show_menu()
            return

        def answer(improved: bool) -> None:
            nonlocal reset_event_id
            storage.complete_reset_event(reset_event_id, improved=improved)
            if improved:
                navigate("home")
                return

            def retry(e) -> None:
                nonlocal reset_event_id
                reset_event_id = ""
                show_menu()

            body.controls = [
                ui_helpers.page_header("", on_back=lambda e: show_menu()),
                buddy.face("cemas", 110),
                ui_helpers.title("Belum membaik juga nggak apa-apa.", 19),
                ft.Text(
                    "Nggak ada tugas yang harus dipaksa sekarang. Kamu boleh tetap "
                    "istirahat, mencoba aktivitas lain, atau mencari dukungan.",
                    size=12.5,
                    color=theme.MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
                ui_helpers.wide_button(
                    "Coba aktivitas lain",
                    retry,
                    icon=ft.Icons.SPA,
                ),
                professional_card(prominent=distress.escalate),
                ft.TextButton(
                    content=ft.Text("Kembali ke Beranda"),
                    on_click=lambda e: navigate("home"),
                ),
            ]
            page.update()

        body.controls = [
            ui_helpers.page_header("", on_back=lambda e: show_menu()),
            buddy.face("tenang", 110),
            ui_helpers.title("Sekarang rasanya gimana?", 19),
            ft.Text(
                "Jawaban kamu yang menentukan apakah Reset ini membantu—bukan "
                "sekadar karena aktivitasnya dibuka.",
                size=12.5,
                color=theme.MUTED,
                text_align=ft.TextAlign.CENTER,
            ),
            ui_helpers.wide_button(
                "Sedikit lebih enak",
                lambda e: answer(True),
                icon=ft.Icons.FAVORITE,
            ),
            ft.OutlinedButton(
                content=ft.Text("Belum membaik"),
                on_click=lambda e: answer(False),
            ),
        ]
        page.update()


    def hotline_rows() -> list[ft.Control]:
        rows: list[ft.Control] = []
        for h in CRISIS_HOTLINES:
            rows.append(ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.CALL, color="#FFFFFF", size=22),
                        ft.Column(
                            [
                                ft.Text(h["number"], size=19, weight=ft.FontWeight.BOLD,
                                        color="#FFFFFF"),
                                ft.Text(f"{h['name']} · {h['desc']}", size=11, color="#FFFFFF"),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.ARROW_OUTWARD, color="#FFFFFF", size=16),
                    ],
                    spacing=12,
                ),
                padding=ft.Padding.symmetric(vertical=12, horizontal=14),
                bgcolor=theme.PRIMARY,
                border_radius=12,
                url=h["tel"],
                ink=True,
            ))
            if h.get("web"):
                rows.append(
                    ft.TextButton(
                        content=ft.Text("Buka Healing119.id", size=12, color=theme.PRIMARY),
                        icon=ft.Icons.OPEN_IN_NEW,
                        url=h["web"],
                    )
                )
        return rows

    def professional_card(prominent: bool) -> ft.Control:
        partner_rows = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.SUPPORT_AGENT, color=theme.PRIMARY, size=20),
                        ft.Column(
                            [
                                ft.Text(p["name"], weight=ft.FontWeight.BOLD, size=13, color=theme.ON_BACKGROUND),
                                ft.Text(p["desc"], size=11, color=theme.MUTED),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.OPEN_IN_NEW, color=theme.MUTED, size=16),
                    ],
                    spacing=12,
                ),
                padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                bgcolor=theme.BACKGROUND,
                border_radius=12,
                url=p["url"],
                ink=True,
            )
            for p in TELEHEALTH_PARTNERS
        ]

        header = (
            ft.Column(
                [
                    ui_helpers.banner(
                        "Kalem lihat ini bukan cuma capek biasa", theme.DANGER, ft.Icons.FAVORITE
                    ),
                    ft.Text(distress.reason, size=12, color=theme.MUTED),
                    ft.Text(
                        "Nggak apa-apa minta bantuan. Ngobrol sama orang yang terlatih "
                        "bakal lebih ngebantu daripada nahan sendiri.",
                        size=13,
                        color=theme.ON_BACKGROUND,
                    ),
                ],
                spacing=8,
            )
            if prominent
            else ft.Column(
                [
                    ui_helpers.section_header("Butuh ngobrol sama profesional?"),
                    ft.Text(
                        "Kalau rasanya kebanyakan buat dihadapin sendiri, ini beberapa layanan yang bisa dihubungi.",
                        size=12,
                        color=theme.MUTED,
                    ),
                ],
                spacing=6,
            )
        )

        rows = [*hotline_rows(), *partner_rows] if prominent else [*partner_rows, *hotline_rows()]

        return ui_helpers.card(ft.Column([header, *rows], spacing=10), bgcolor=theme.SURFACE)

    def person_card() -> Optional[ft.Control]:
        person = favorites.get("orang", "").strip()
        if not person or not distress.escalate:
            return None
        return ui_helpers.card(
            ft.Row(
                [
                    ft.Icon(ft.Icons.PEOPLE_OUTLINE, color=theme.SECONDARY, size=22),
                    ft.Column(
                        [
                            ft.Text(f"Mau cerita ke {person}?", size=14,
                                    weight=ft.FontWeight.BOLD, color=theme.ON_BACKGROUND),
                            ft.Text(
                                "Kamu pernah bilang dia tempat cerita kamu. Nggak harus "
                                "cerita berat — kabar-kabaran aja juga boleh.",
                                size=11.5,
                                color=theme.MUTED,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=14,
        )

    def snack_card() -> Optional[ft.Control]:
        snack = (favorites.get("snack") or "").strip()
        if not snack:
            return None
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.LOCAL_CAFE, color=theme.TERTIARY, size=20),
                    ft.Column(
                        [
                            ft.Text(f"Ambil {snack} dulu?", size=13.5,
                                    weight=ft.FontWeight.BOLD, color=theme.ON_BACKGROUND),
                            ft.Text("Nggak usah mikir dulu. Ini aja udah cukup.",
                                    size=11, color=theme.MUTED),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                ],
                spacing=12,
            ),
            bgcolor=theme.SURFACE,
            border=ft.Border.all(1, theme.TERTIARY),
            border_radius=theme.CARD_RADIUS,
            padding=14,
        )

    def encouragement_card() -> Optional[ft.Control]:
        line = favorites.get("penyemangat", "").strip()
        if not line:
            return None
        return ui_helpers.card(
            ft.Column(
                [
                    ui_helpers.section_header("Kata kamu sendiri"),
                    ft.Text(f"“{line}”", size=14, italic=True,
                            color=theme.ON_BACKGROUND, text_align=ft.TextAlign.CENTER),
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=14,
        )

    def activity_frame(title: str, inner: ft.Control, on_back) -> None:
        body.controls = [
            ui_helpers.page_header(title, on_back=on_back),
            ui_helpers.card(inner),
            ui_helpers.soft_button("Kembali", on_back),
        ]
        page.update()


    def show_breathing():
        log_once("napas")
        running = {"active": True}

        circle = ft.Container(
            width=170,
            height=170,
            border_radius=85,
            bgcolor=ft.Colors.with_opacity(0.30, theme.PRIMARY),
            border=ft.Border.all(2, theme.PRIMARY),
            scale=0.55,
            animate_scale=ft.Animation(1000, ft.AnimationCurve.EASE_IN_OUT),
            alignment=ft.Alignment.CENTER,
        )
        counter_text = ft.Text("", size=44, weight=ft.FontWeight.BOLD, color=theme.PRIMARY)
        circle.content = counter_text

        phase_text = ft.Text("Siap-siap...", size=19, weight=ft.FontWeight.BOLD,
                             color=theme.ON_BACKGROUND)
        cycle_text = ft.Text("Ikutin lingkarannya aja.", size=12, color=theme.MUTED)

        async def run_cycles():
            await asyncio.sleep(0.6)
            for cycle in range(1, 4):
                cycle_text.value = f"Putaran {cycle} dari 3"
                for label, seconds, target_scale in BREATHING_STEPS:
                    if not running["active"]:
                        return
                    phase_text.value = label
                    circle.animate_scale = ft.Animation(
                        seconds * 1000, ft.AnimationCurve.EASE_IN_OUT
                    )
                    circle.scale = target_scale
                    for remaining in range(seconds, 0, -1):
                        if not running["active"]:
                            return
                        counter_text.value = str(remaining)
                        page.update()
                        await asyncio.sleep(1)
            if running["active"]:
                phase_text.value = "Selesai 🤍"
                counter_text.value = ""
                cycle_text.value = "Semoga agak lebih enak sekarang."
                circle.animate_scale = ft.Animation(900, ft.AnimationCurve.EASE_OUT)
                circle.scale = 0.8
                page.update()
                await asyncio.sleep(0.8)
                if running["active"]:
                    show_outcome()

        def back(e):
            running["active"] = False
            show_menu()

        activity_frame(
            "Napas 4-7-8",
            ft.Column(
                [
                    phase_text,
                    ft.Container(content=circle, height=200, alignment=ft.Alignment.CENTER),
                    cycle_text,
                ],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            back,
        )
        page.run_task(run_cycles)


    def show_grounding():
        log_once("grounding")
        pos = {"i": 0}

        def render():
            i = pos["i"]
            if i >= len(GROUNDING_STEPS):
                inner = ft.Column(
                    [
                        buddy.face("tenang", 100),
                        ft.Text("Udah balik ke sini 🤍", size=17, weight=ft.FontWeight.BOLD,
                                color=theme.ON_BACKGROUND),
                        ft.Text(
                            "Kepala kamu barusan sibuk sama hal yang beneran ada di sekitar, "
                            "bukan sama yang lagi diputer-puter.",
                            size=12.5,
                            color=theme.MUTED,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.TextButton(
                            content=ft.Text("Ulangi dari awal"),
                            on_click=lambda e: (pos.update(i=0), render()),
                        ),
                        ui_helpers.wide_button(
                            "Lanjut", lambda e: show_outcome(), icon=ft.Icons.CHECK
                        ),
                    ],
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
            else:
                count, what, icon = GROUNDING_STEPS[i]
                inner = ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(
                                    height=4,
                                    expand=True,
                                    bgcolor=theme.PRIMARY if n <= i else theme.BORDER,
                                    border_radius=2,
                                )
                                for n in range(len(GROUNDING_STEPS))
                            ],
                            spacing=4,
                        ),
                        ft.Icon(icon, size=40, color=theme.SECONDARY),
                        ft.Text(str(count), size=52, weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
                        ft.Text(what, size=15, color=theme.ON_BACKGROUND,
                                text_align=ft.TextAlign.CENTER),
                        ft.Text(
                            "Nggak usah diketik, sebut aja dalam hati. Pelan-pelan.",
                            size=11.5,
                            color=theme.MUTED,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ui_helpers.wide_button(
                            "Udah", lambda e: (pos.update(i=pos["i"] + 1), render()),
                            icon=ft.Icons.CHECK,
                        ),
                    ],
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )

            activity_frame("Balik ke sini", inner, lambda e: show_menu())

        render()


    def show_music():
        log_once("musik")
        fav = (favorites.get("musik") or "").strip()
        query = fav or "lofi calm"

        links = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, color=theme.PRIMARY, size=22),
                        ft.Column(
                            [
                                ft.Text(m["name"], size=13, weight=ft.FontWeight.BOLD,
                                        color=theme.ON_BACKGROUND),
                                ft.Text(m["desc"], size=11, color=theme.MUTED),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.OPEN_IN_NEW, color=theme.MUTED, size=16),
                    ],
                    spacing=10,
                ),
                padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                bgcolor=theme.BACKGROUND,
                border_radius=12,
                url=m["url"],
                ink=True,
            )
            for m in music_links(query)
        ]

        note = (
            f"Kamu bilang '{fav}' yang bikin kamu tenang. Aku bukain langsung."
            if fav
            else "Kamu belum cerita musik apa yang bikin tenang, jadi aku bukain "
                 "lo-fi dulu. Isi Favorit biar next-nya lebih pas."
        )

        children: list[ft.Control] = [
            buddy.face("tenang", 100),
            ft.Text("Pejamkan mata sebentar.", size=16, weight=ft.FontWeight.BOLD,
                    color=theme.ON_BACKGROUND),
            ft.Text(note, size=12.5, color=theme.MUTED, text_align=ft.TextAlign.CENTER),
            *links,
            ui_helpers.wide_button(
                "Selesai mendengarkan",
                lambda e: show_outcome(),
                icon=ft.Icons.CHECK,
            ),
        ]
        if not fav:
            children.append(
                ft.TextButton(
                    content=ft.Text("Isi Favorit", size=12),
                    icon=ft.Icons.FAVORITE_BORDER,
                    on_click=lambda e: navigate("favorites"),
                )
            )

        activity_frame(
            "Musik",
            ft.Column(children, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            lambda e: show_menu(),
        )


    def show_move():
        log_once("gerak")
        options = list(MOVE_ACTIONS)
        if favorites.get("gerak"):
            options.insert(0, f"Coba {favorites['gerak']} — 60 detik aja, nggak usah niat.")
        if favorites.get("tempat"):
            options.insert(0, f"Pindah ke {favorites['tempat']} sebentar.")

        picked = {"text": random.choice(options)}
        timer = {"left": 60, "running": False, "loop": False}
        countdown_text = ft.Text("60", size=44, weight=ft.FontWeight.BOLD, color=theme.PRIMARY)
        status_text = ft.Text("", size=12, color=theme.MUTED)
        alive = {"on": True}

        async def tick():
            if timer["loop"]:
                return
            timer["loop"] = True
            try:
                while timer["left"] > 0 and alive["on"]:
                    await asyncio.sleep(1)
                    if not timer["running"] or not alive["on"]:
                        continue
                    timer["left"] -= 1
                    countdown_text.value = str(timer["left"])
                    page.update()
                if alive["on"] and timer["left"] <= 0:
                    countdown_text.value = "🤍"
                    status_text.value = "Udah. Itu aja udah cukup buat sekarang."
                    page.update()
                    await asyncio.sleep(0.8)
                    if alive["on"]:
                        show_outcome()
            finally:
                timer["loop"] = False

        def start(e):
            timer["running"] = True
            status_text.value = "Jalan... nggak usah buru-buru."
            page.update()
            page.run_task(tick)

        def another(e):
            picked["text"] = random.choice(options)
            timer.update(left=60, running=False)
            countdown_text.value = "60"
            status_text.value = ""
            render()

        def back(e):
            alive["on"] = False
            show_menu()

        def render():
            activity_frame(
                "Gerak 60 detik",
                ft.Column(
                    [
                        buddy.face("semangat", 90),
                        ft.Text(picked["text"], size=17, weight=ft.FontWeight.BOLD,
                                color=theme.ON_BACKGROUND, text_align=ft.TextAlign.CENTER),
                        countdown_text,
                        status_text,
                        ui_helpers.wide_button("Mulai", start, icon=ft.Icons.PLAY_ARROW),
                        ft.TextButton(content=ft.Text("Kasih ide lain"), on_click=another),
                    ],
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                back,
            )

        render()

    HANDLERS = {
        "napas": show_breathing,
        "grounding": show_grounding,
        "musik": show_music,
        "gerak": show_move,
    }
    ICONS = {
        "napas": ft.Icons.AIR,
        "grounding": ft.Icons.VISIBILITY,
        "musik": ft.Icons.MUSIC_NOTE,
        "gerak": ft.Icons.DIRECTIONS_WALK,
    }


    def option_row(key: str, highlight: bool) -> ft.Control:
        meta = OPTIONS[key]
        used = prefs.jumlah.get(key, 0)
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ICONS[key], color=theme.PRIMARY if highlight else theme.MUTED, size=24),
                    ft.Column(
                        [
                            ft.Text(meta["label"], weight=ft.FontWeight.BOLD, size=14, color=theme.ON_BACKGROUND),
                            ft.Text(
                                meta["desc"] + (f" · dipakai {used}x" if used else ""),
                                size=11,
                                color=theme.MUTED,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=theme.MUTED, size=20),
                ],
                spacing=14,
            ),
            bgcolor=theme.SURFACE,
            border=ft.Border.all(2 if highlight else 1, theme.PRIMARY if highlight else theme.BORDER),
            border_radius=theme.CARD_RADIUS,
            padding=16,
            on_click=lambda e, k=key: HANDLERS[k](),
            ink=True,
        )

    def show_menu():
        header = ft.Column(
            [
                buddy.face("cemas" if distress.escalate else "tenang", 120),
                ui_helpers.title("Tarik napas dulu.", 20),
                ft.Text(
                    "Semua daftar tugas lagi disembunyiin. Sekarang nggak ada yang harus dikejar.",
                    size=13,
                    color=theme.MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        controls: list[ft.Control] = [
            ui_helpers.page_header("", on_back=lambda e: navigate("home")),
            header,
        ]

        if distress.escalate:
            controls.append(professional_card(prominent=True))
            person = person_card()
            if person:
                controls.append(person)
            controls.append(ui_helpers.section_header("Atau kalau mau nenangin diri dulu"))
            controls.extend(option_row(k, highlight=False) for k in prefs.urutan)
        else:
            if prefs.catatan:
                controls.append(ui_helpers.banner(prefs.catatan, theme.PRIMARY, ft.Icons.FAVORITE))
            snack = snack_card()
            if snack:
                controls.append(snack)
            controls.extend(
                option_row(k, highlight=(i == 0 and prefs.sumber != "pemicu"))
                for i, k in enumerate(prefs.urutan)
            )
            controls.append(professional_card(prominent=False))

        encouragement = encouragement_card()
        if encouragement:
            controls.append(encouragement)

        controls.append(
            ui_helpers.disclaimer(
                "FocusBuddy bukan layanan krisis. Kalau kamu dalam bahaya langsung, "
                "hubungi layanan darurat atau nomor di atas."
            )
        )

        body.controls = controls
        page.update()

    show_menu()
    return body
