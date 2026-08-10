"""Page 4 -- Reset. Tujuan halaman ini ruang personal, bukan layar tenang generik.

Tiga lapis:
1. Opsi penenang -- urutannya menyesuaikan apa yang paling sering ngebantu
   user (hitung frekuensi, bukan ML).
2. Rujukan: hotline TELEPON duluan, baru deep link telehealth.
3. Deteksi pola distress: kalau SOS berulang + mood rendah, app berhenti
   nawarin musik dan lebih tegas ngarahin ke bantuan profesional.

ATURAN HALAMAN INI: nggak ada satu pun opsi yang nyentuh daftar tugas.
Halaman ini bilang "semua daftar tugas lagi disembunyiin" -- nyodorin tugas
di sini, sekecil apa pun, ngebatalin janji itu.

SOAL PENCATATAN SOS: event cuma dicatat SEKALI per pembukaan aktivitas.
Versi lama nyatet tiap kali layarnya digambar ulang, jadi mencet "Kasih ide
lain" 4x = 4 event SOS -- cukup buat micu eskalasi rujukan profesional
padahal user cuma lagi milih-milih.
"""
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
from app.kalem_ml import model_penenang

# Saran gerak 60 detik. SENGAJA nggak ada yang narik dari daftar tugas.
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

# Grounding 5-4-3-2-1 -- teknik standar buat narik perhatian keluar dari
# spiral pikiran, balik ke indra. Nggak butuh alat, nggak butuh tugas.
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
    # Urutan opsi sekarang dari `model_penenang`: bukan cuma seberapa SERING
    # dipakai, tapi seberapa sering mood user jadi lebih enak SESUDAHNYA.
    # Opsi yang diulang terus belum tentu yang nolong -- bisa jadi justru
    # yang nggak mempan, makanya diulang.
    prefs = model_penenang.peringkat(
        storage.get_reset_events(), storage.get_mood_logs(), storage.all_triggers(profile)
    )

    # Satu KUNJUNGAN Reset = satu event. Mencoba beberapa aktivitas saat
    # kunjungan yang sama bukan empat kejadian SOS terpisah.
    logged = False

    def log_once(choice: str):
        nonlocal logged
        if not logged:
            storage.add_reset_event(choice)
            logged = True

    # ------------------------------------------------------ rujukan pro

    def hotline_rows() -> list[ft.Control]:
        """Nomor telepon ditaruh gede & bisa dipencet.

        Tautan web bisa mati (dan pernah mati di app ini), butuh sinyal data,
        dan minta orang navigasiin situs dulu. Nomor telepon nggak.
        """
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
                # Telepon 119 lalu pilih ekstensi 8. Sistem dialer tidak
                # punya format lintas-perangkat yang andal untuk extension.
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

        # Pas pola distress kebaca, telepon naik ke paling atas -- di atas
        # semua tautan web. Kalau nggak, hotline tetap ada tapi di bawah,
        # biar halaman ini nggak kerasa kayak layar darurat tiap dibuka.
        rows = [*hotline_rows(), *partner_rows] if prominent else [*partner_rows, *hotline_rows()]

        return ui_helpers.card(ft.Column([header, *rows], spacing=10), bgcolor=theme.SURFACE)

    def person_card() -> Optional[ft.Control]:
        """"Mau cerita ke [nama]?" -- cuma muncul pas pola SOS berulang.

        Sifatnya PENGINGAT, bukan auto-contact: Kalem nggak nyimpen nomor,
        nggak ngirim apa-apa. Ditaruh berdampingan sama rujukan profesional,
        bukan gantiin -- orang terdekat dan tenaga terlatih beda peran.
        """
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
        """Comfort food favorit user, ditawarin pas lagi kewalahan.

        Kolom `snack` dulu satu-satunya isian Favorit yang nggak punya
        konsumen -- kesimpen tapi nggak pernah kepakai di mana pun. Di sinilah
        tempatnya paling masuk akal: aksi paling murah yang ada di halaman
        ini, nol usaha kognitif, dan pakai kata-kata user sendiri.
        """
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
        """Kalimat penyemangat user sendiri, dikutip balik sama Kalem."""
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

    # ------------------------------------------------------------- napas

    def show_breathing():
        log_once("napas")
        running = {"active": True}

        # Lingkaran yang beneran ikut napas: mengembang 4 detik pas narik,
        # nahan ukuran 7 detik, nyusut 8 detik pas buang. Ini yang bikin user
        # punya sesuatu buat DIIKUTIN, bukan cuma angka yang turun sendiri.
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
                    # Durasi animasi = durasi fase, jadi lingkarannya nyampe
                    # ukuran akhir pas hitungannya juga habis.
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

    # --------------------------------------------------------- grounding

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

    # ------------------------------------------------------------ musik

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

    # ------------------------------------------------------------- gerak

    def show_move():
        log_once("gerak")
        # Favorit user naik ke atas, tapi daftarnya tetap murni self-care --
        # nggak ada satu pun yang ngambil dari tugas.
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

    # ------------------------------------------------------------- menu

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
            # Pola distress kebaca: rujukan profesional naik ke atas,
            # opsi penenang tetap ada tapi jadi pilihan sekunder.
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
