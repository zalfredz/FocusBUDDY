"""Halaman Settings -- rumah buat fitur yang tadinya nyebar/nggak punya
tempat sendiri: edit ulang jawaban onboarding, link ke Obat & Favorit,
hapus semua data, dan info app.

Gear icon di Home nunjuk ke sini (bukan lagi langsung ke med_setup) --
"pengaturan app" beda sama "setup obat".

Tiga aturan yang beda dari onboarding:

- UMUR DIKUNCI begitu terisi. Umur nggak berubah gara-gara ganti pikiran,
  dan ngebiarin dia diedit bebas cuma ngundang data yang nggak konsisten.
  Yang masih kosong (user lama / hasil skip) tetap boleh diisi sekali.
- PEKERJAAN boleh lebih dari satu. "Mahasiswa sambil kerja" itu satu orang,
  dan maksa milih satu bikin datanya bohong.
- JAM PRODUKTIF diatur pakai slider, bukan preset. Di onboarding preset itu
  perlu (biar di bawah semenit); di sini user punya waktu buat presisi, dan
  boleh punya lebih dari satu rentang -- mis. pagi 06-11 DAN malam 20-01.
"""
from __future__ import annotations

import flet as ft

from app import storage, theme, ui_helpers
from app.kalem_ml import fitur as kfitur

AGE_OPTIONS = ["<18", "18-24", "25-34", "35+"]

APP_VERSION = "4.1.0"

# Rentang yang dipasang pas user mencet "Tambah rentang" -- sore-malam,
# jam paling umum buat orang ngerjain sesuatu di luar jam wajib.
DEFAULT_NEW_RANGE = [19, 22]


def build(page: ft.Page, navigate) -> ft.Control:
    profile = storage.get_profile()
    state = {
        "name": profile.get("name", ""),
        "age_range": profile.get("age_range", ""),
        "status": list(profile.get("status") or []),
        "sleep_condition": profile.get("sleep_condition", ""),
        "overwhelm_triggers": list(profile.get("overwhelm_triggers") or []),
        "custom_triggers": list(profile.get("custom_triggers") or []),
        "productive_hours": [list(r) for r in (profile.get("productive_hours") or [])],
        "trigger_input_open": False,
    }
    # Dikunci berdasarkan kondisi AWAL, bukan state yang lagi diedit -- kalau
    # nggak, umur bakal langsung ngunci diri sendiri sedetik setelah dipilih
    # dan user nggak sempat benerin kalau salah pencet.
    age_locked = bool(profile.get("age_range"))

    name_field = ft.TextField(label="Panggil kamu siapa?", value=state["name"])
    saved_note = ft.Text("", size=12, color=theme.PRIMARY)

    age_holder = ft.Container()
    status_holder = ft.Container()
    sleep_holder = ft.Container()
    hours_holder = ft.Container()
    triggers_holder = ft.Container()
    trigger_field = ft.TextField(
        hint_text="Tulis sendiri, mis. rapat mendadak",
        text_size=12,
        height=42,
        content_padding=ft.Padding.symmetric(vertical=4, horizontal=10),
        expand=True,
        autofocus=True,
        on_submit=lambda e: add_custom_trigger(e),
    )

    # ------------------------------------------------------------ umur

    def render_age():
        if age_locked:
            age_holder.content = ft.Column(
                [
                    ui_helpers.subtitle("Umur", 12),
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(state["age_range"], size=12.5,
                                                color=theme.ON_BACKGROUND),
                                bgcolor=theme.BACKGROUND,
                                border=ft.Border.all(1, theme.BORDER),
                                border_radius=12,
                                padding=ft.Padding.symmetric(vertical=10, horizontal=14),
                            ),
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.LOCK_OUTLINE, size=13, color=theme.MUTED),
                                    ft.Text("Nggak bisa diubah", size=11, color=theme.MUTED),
                                ],
                                spacing=4,
                            ),
                        ],
                        spacing=10,
                    ),
                ],
                spacing=6,
            )
            return

        age_holder.content = ft.Column(
            [
                ui_helpers.subtitle("Umur", 12),
                ft.Text(
                    "Sekali disimpan, umur nggak bisa diubah lagi.",
                    size=11,
                    color=theme.MUTED,
                ),
                ft.Row(
                    [
                        ui_helpers.choice_chip(
                            a, a == state["age_range"], lambda e, v=a: pick_age(v)
                        )
                        for a in AGE_OPTIONS
                    ],
                    spacing=6,
                    wrap=True,
                    run_spacing=6,
                ),
            ],
            spacing=6,
        )

    def pick_age(value: str):
        state["age_range"] = value
        render_age()
        page.update()

    # -------------------------------------------------------- pekerjaan

    def render_status():
        chips = [
            ui_helpers.choice_chip(
                label, value in state["status"], lambda e, v=value: toggle_status(v)
            )
            for value, label in storage.STATUS_OPTIONS.items()
        ]
        status_holder.content = ft.Column(
            [
                ui_helpers.subtitle(
                    f"Sehari-hari kamu lagi... (boleh lebih dari satu, maks {storage.MAX_STATUS})",
                    12,
                ),
                ft.Row(chips, spacing=6, wrap=True, run_spacing=6),
            ],
            spacing=6,
        )

    def toggle_status(value: str):
        current = state["status"]
        if value in current:
            current.remove(value)
        elif len(current) < storage.MAX_STATUS:
            current.append(value)
        render_status()
        page.update()

    # ------------------------------------------------------ kondisi tidur

    def render_sleep():
        chips = [
            ui_helpers.choice_chip(
                label, value == state["sleep_condition"], lambda e, v=value: pick_sleep(v)
            )
            for value, label in storage.SLEEP_OPTIONS.items()
        ]
        sleep_holder.content = ft.Column(
            [
                ui_helpers.subtitle("Kondisi tidur belakangan", 12),
                ft.Row(chips, spacing=6, wrap=True, run_spacing=6),
            ],
            spacing=6,
        )

    def pick_sleep(value: str):
        state["sleep_condition"] = value
        render_sleep()
        page.update()

    # ------------------------------------------------------ jam produktif

    def render_hours():
        rows: list[ft.Control] = [
            ui_helpers.subtitle("Jam Produktif", 12),
            ft.Text(
                "Geser buat nentuin jamnya sendiri. Boleh lebih dari satu rentang — "
                "mis. pagi 06:00–11:00 dan malam 20:00–01:00.",
                size=11,
                color=theme.MUTED,
            ),
        ]

        if not state["productive_hours"]:
            rows.append(
                ft.Text(
                    "Belum diatur. Kalem nggak bakal nebak-nebak jam produktif kamu.",
                    size=11.5,
                    color=theme.MUTED,
                    italic=True,
                )
            )

        for i, (start, end) in enumerate(state["productive_hours"]):
            label = ft.Text(
                storage.fmt_range(start, end),
                size=13.5,
                weight=ft.FontWeight.BOLD,
                color=theme.ON_BACKGROUND,
                expand=True,
            )
            slider = ft.RangeSlider(
                start_value=float(start),
                end_value=float(end),
                min=float(storage.HOUR_MIN),
                max=float(storage.HOUR_MAX),
                divisions=storage.HOUR_MAX - storage.HOUR_MIN,
                active_color=theme.PRIMARY,
                inactive_color=theme.BORDER,
                on_change=lambda e, idx=i, lbl=label: slide(idx, e, lbl),
            )
            rows.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    label,
                                    ft.IconButton(
                                        icon=ft.Icons.CLOSE,
                                        icon_size=16,
                                        icon_color=theme.MUTED,
                                        tooltip="Hapus rentang ini",
                                        on_click=lambda e, idx=i: drop_range(idx),
                                    ),
                                ],
                                spacing=4,
                            ),
                            slider,
                        ],
                        spacing=0,
                    ),
                    bgcolor=theme.BACKGROUND,
                    border_radius=12,
                    padding=ft.Padding.symmetric(vertical=8, horizontal=12),
                )
            )

        rows.append(
            ft.TextButton(
                content=ft.Text("+ Tambah rentang", size=12, color=theme.PRIMARY),
                on_click=lambda e: add_range(),
            )
        )
        hours_holder.content = ft.Column(rows, spacing=8)

    def slide(index: int, e, label: ft.Text):
        """Update label langsung tanpa render ulang seluruh daftar.

        Kalau render ulang penuh, slider-nya kebangun baru di tengah drag dan
        jarinya "lepas" dari gagang -- gerakannya jadi patah-patah.
        """
        start = int(round(e.control.start_value))
        end = int(round(e.control.end_value))
        if end <= start:
            end = min(start + 1, storage.HOUR_MAX)
        state["productive_hours"][index] = [start, end]
        label.value = storage.fmt_range(start, end)
        page.update()

    def add_range():
        state["productive_hours"].append(list(DEFAULT_NEW_RANGE))
        render_hours()
        page.update()

    def drop_range(index: int):
        state["productive_hours"].pop(index)
        render_hours()
        page.update()

    # ---------------------------------------------------- pemicu kewalahan

    def render_triggers():
        picked = state["overwhelm_triggers"] + state["custom_triggers"]
        full = len(picked) >= storage.MAX_TRIGGERS

        chips: list[ft.Control] = [
            ui_helpers.choice_chip(
                label, value in state["overwhelm_triggers"], lambda e, v=value: toggle_trigger(v)
            )
            for value, label in storage.TRIGGER_OPTIONS.items()
        ]
        # Pemicu ketikan sendiri tampil sebagai chip juga, biar bisa dimatiin
        # persis kayak preset -- bukan daftar terpisah yang cuma bisa dilihat.
        chips += [
            ui_helpers.choice_chip(t, True, lambda e, v=t: drop_custom_trigger(v))
            for t in state["custom_triggers"]
        ]

        if not full:
            chips.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.ADD, size=13, color=theme.MUTED),
                            ft.Text("Lainnya", size=12.5, color=theme.MUTED),
                        ],
                        spacing=3,
                        tight=True,
                    ),
                    border=ft.Border.all(1, theme.BORDER),
                    border_radius=12,
                    padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                    on_click=lambda e: open_trigger_input(),
                    ink=True,
                )
            )

        children: list[ft.Control] = [
            ui_helpers.subtitle(
                f"Yang paling sering bikin kewalahan (maks {storage.MAX_TRIGGERS})", 12
            ),
            ft.Text(
                "Ini yang nentuin opsi mana yang muncul duluan di halaman jeda "
                "pas kamu lagi kewalahan.",
                size=11,
                color=theme.MUTED,
            ),
            ft.Row(chips, spacing=6, wrap=True, run_spacing=6),
        ]

        if state["trigger_input_open"] and not full:
            children.append(
                ft.Row(
                    [
                        trigger_field,
                        ft.IconButton(
                            icon=ft.Icons.CHECK,
                            icon_color=theme.PRIMARY,
                            icon_size=20,
                            on_click=add_custom_trigger,
                        ),
                    ],
                    spacing=4,
                )
            )

        triggers_holder.content = ft.Column(children, spacing=6)

    def toggle_trigger(value: str):
        current = state["overwhelm_triggers"]
        total = len(current) + len(state["custom_triggers"])
        if value in current:
            current.remove(value)
        elif total < storage.MAX_TRIGGERS:
            current.append(value)
        render_triggers()
        page.update()

    def open_trigger_input():
        state["trigger_input_open"] = True
        render_triggers()
        page.update()

    def add_custom_trigger(e):
        raw = (trigger_field.value or "").strip()
        # Dipotong 32 karakter: ini label pemicu, bukan tempat cerita.
        text = raw[:32]
        total = len(state["overwhelm_triggers"]) + len(state["custom_triggers"])
        if text and text not in state["custom_triggers"] and total < storage.MAX_TRIGGERS:
            state["custom_triggers"].append(text)
        trigger_field.value = ""
        state["trigger_input_open"] = False
        render_triggers()
        page.update()

    def drop_custom_trigger(value: str):
        if value in state["custom_triggers"]:
            state["custom_triggers"].remove(value)
        render_triggers()
        page.update()

    # ------------------------------------------------------------- simpan

    def save_profile(e):
        state["name"] = (name_field.value or "").strip() or "Teman"
        storage.save_profile(
            {
                "name": state["name"],
                "age_range": state["age_range"],
                "status": state["status"],
                "sleep_condition": state["sleep_condition"],
                "overwhelm_triggers": state["overwhelm_triggers"],
                "custom_triggers": state["custom_triggers"],
                "productive_hours": state["productive_hours"],
            }
        )
        saved_note.value = "Tersimpan 🤍"
        page.update()

    render_age()
    render_status()
    render_sleep()
    render_hours()
    render_triggers()

    def confirm_reset(e):
        ui_helpers.show_reset_confirm(page, lambda: (storage.reset_all_data(), navigate("home")))

    return ft.Column(
        [
            ui_helpers.page_header("Pengaturan", on_back=lambda e: navigate("home")),
            ui_helpers.card(
                ft.Column(
                    [
                        ui_helpers.section_header("Profil"),
                        ui_helpers.subtitle(
                            "Situasi berubah, jawabannya boleh diubah juga.", 12
                        ),
                        name_field,
                        age_holder,
                        status_holder,
                        hours_holder,
                        sleep_holder,
                        triggers_holder,
                        ui_helpers.wide_button("Simpan Profil", save_profile, icon=ft.Icons.SAVE),
                        saved_note,
                    ],
                    spacing=14,
                )
            ),
            _med_link_card(navigate),
            ui_helpers.nav_link_card(
                ft.Icons.FAVORITE_BORDER,
                theme.TERTIARY,
                "Favorit Kamu",
                f"{storage.favorites_filled()}/{len(storage.FAVORITE_FIELDS)} terisi.",
                lambda e: navigate("favorites"),
            ),
            _kartu_model(),
            ui_helpers.card(
                ft.Column(
                    [
                        ui_helpers.section_header("Privasi & Data"),
                        ft.Text(
                            "Semua data (profil, tugas, mood, diary, favorit, obat) disimpan "
                            "lokal di HP ini aja. Nggak ada server luar di build ini.",
                            size=12,
                            color=theme.MUTED,
                        ),
                        ft.TextButton(
                            content=ft.Text("Hapus semua data", color=theme.DANGER),
                            icon=ft.Icons.DELETE_OUTLINE,
                            icon_color=theme.DANGER,
                            on_click=confirm_reset,
                        ),
                    ],
                    spacing=8,
                ),
                padding=16,
            ),
            ui_helpers.card(
                ft.Column(
                    [
                        ui_helpers.section_header("Tentang FocusBuddy"),
                        ft.Text(
                            "FocusBuddy bukan alat diagnosis ADHD dan bukan pengganti tenaga "
                            "medis. Ini alat bantu micro-planning harian, bukan penilaian "
                            "klinis.",
                            size=12,
                            color=theme.MUTED,
                        ),
                        ft.Text(f"Versi {APP_VERSION}", size=11, color=theme.MUTED),
                    ],
                    spacing=8,
                ),
                padding=16,
            ),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


def _kartu_model() -> ft.Control:
    """Seberapa jauh Kalem udah kenal kamu -- terbuka, bukan kotak hitam.

    Sengaja ditulis sebagai "udah belajar apa", bukan sebagai persentase atau
    skor. Angka mentah model (risiko, probabilitas) nggak pernah dipajang:
    itu bikin cemas dan kesannya pasti, padahal nggak.
    """
    import app.kalem_ml as ml

    ringkas = kfitur.ringkas_untuk_ui()
    st = ml.status_semua()

    baris: list[ft.Control] = []

    def item(judul: str, siap: bool, teks: str):
        baris.append(
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE if siap else ft.Icons.HOURGLASS_EMPTY,
                        size=15,
                        color=theme.SUCCESS if siap else theme.MUTED,
                    ),
                    ft.Column(
                        [
                            ft.Text(judul, size=12.5, weight=ft.FontWeight.BOLD,
                                    color=theme.ON_BACKGROUND),
                            ft.Text(teks, size=11, color=theme.MUTED),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )

    d = st["durasi"]
    item("Perkiraan waktu tugas", d["siap"],
         f"Dilatih dari {d['n_latih']} tugas contoh"
         + (f" · kecepatan kamu: {ringkas['sesi_7h']} sesi minggu ini" if ringkas["sesi_7h"] else ""))

    m = st["mood"]
    item("Pola mood", m["siap_pola"],
         f"{m['n_catatan']} catatan"
         + (" · udah bisa baca pola" if m["siap_model"] else " · butuh 5 buat mulai baca pola"))

    o = st["overwhelm"]
    item("Deteksi hari berat", o["siap"],
         f"Belajar dari {o['n_latih']} hari" if o["siap"]
         else f"Butuh {o['min_hari']} hari check-in dulu")

    pn = st["penenang"]
    item("Opsi jeda yang cocok", bool(pn["terukur"]),
         f"{pn['n_pakai']}x kamu pakai halaman jeda" if pn["n_pakai"]
         else "Belum ada data — urutannya ngikutin jawaban onboarding")

    if ringkas["kalibrasi"] != 1.0:
        arah = "lebih lama" if ringkas["kalibrasi"] > 1 else "lebih cepat"
        baris.append(
            ft.Text(
                f"Catatan: sesi kamu biasanya {arah} dari yang diperkirakan "
                f"(faktor {ringkas['kalibrasi']}). Kalem udah nyesuain.",
                size=10.5,
                color=theme.MUTED,
            )
        )

    return ui_helpers.card(
        ft.Column(
            [
                ui_helpers.section_header("Yang Kalem pelajari"),
                ft.Text(
                    "Semua ini dipelajari dari pemakaian kamu sendiri, di HP ini aja. "
                    "Makin sering dipakai, makin nyesuain.",
                    size=11.5,
                    color=theme.MUTED,
                ),
                *baris,
            ],
            spacing=10,
        ),
        padding=16,
    )


def _med_link_card(navigate) -> ft.Container:
    """Kartu link ke Obat -- ikonnya ilustrasi custom, bukan Material icon,
    jadi dibikin manual (nav_link_card cuma nerima ft.Icons.*)."""
    return ft.Container(
        content=ft.Row(
            [
                ui_helpers.med_icon(24, theme.TERTIARY),
                ft.Column(
                    [
                        ft.Text("Pengingat Obat", weight=ft.FontWeight.BOLD, color=theme.ON_BACKGROUND),
                        ft.Text("Setup obat, stok, & jadwal absen.", size=11.5, color=theme.MUTED),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=theme.MUTED, size=20),
            ],
            spacing=12,
        ),
        bgcolor=theme.SURFACE,
        border=ft.Border.all(1, theme.BORDER),
        border_radius=theme.CARD_RADIUS,
        padding=16,
        on_click=lambda e: navigate("med_setup"),
        ink=True,
    )
