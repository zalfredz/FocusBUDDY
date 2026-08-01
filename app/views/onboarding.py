"""Onboarding -- 6 pertanyaan singkat, di bawah semenit.

Aturan yang dipegang halaman ini:

- Tiap jawaban HARUS nyetir minimal satu fitur. Nggak ada pertanyaan yang
  datanya cuma nganggur di database.
- Nggak nanya diagnosis ADHD formal (biar user yang belum/nggak sempat
  diagnosis tetap kepakai) dan nggak pakai skala klinis panjang (ASRS dsb).
- Nama & umur WAJIB dijawab (nggak ada opsi lewat di dua pertanyaan itu).
  Pertanyaan sesudahnya (status dst) boleh di-skip -- begitu skip dipencet,
  onboarding LANGSUNG selesai ke Beranda, bukan lompat ke pertanyaan
  berikutnya. Sisanya pakai default netral.
- KECEPATAN menang atas presisi di sini. Jam produktif ditanya lewat preset
  kasar (pagi/siang/malam), bukan slider -- slidernya ada di Settings buat
  yang mau ngatur persis. Preset di sini langsung diterjemahin jadi rentang
  jam beneran, jadi datanya tetap satu bentuk.

Peta jawaban -> fitur:
    status           -> default rigiditas jadwal (boleh lebih dari satu)
    productive_time  -> rentang Jam Produktif -> nada pesan Kalem
    sleep_condition  -> input Energy/Burnout Classifier
    on_medication    -> trigger setup Medication Companion
    triggers         -> urutan default opsi di halaman Reset
"""
from __future__ import annotations

import flet as ft

from app import buddy, storage, theme, ui_helpers

AGE_OPTIONS = ["<18", "18-24", "25-34", "35+"]


def build(page: ft.Page, navigate) -> ft.Control:
    answers: dict = {
        "name": "",
        "age_range": "",
        "status": [],
        "productive_time": "",
        "sleep_condition": "",
        "on_medication": "",
        "overwhelm_triggers": [],
        "custom_triggers": [],
    }
    step = {"index": 0, "custom_open": False}

    name_field = ft.TextField(label="Panggil kamu siapa?", hint_text="mis. Alfredo")
    custom_field = ft.TextField(
        hint_text="Tulis sendiri, mis. rapat mendadak",
        text_size=12,
        height=42,
        content_padding=ft.Padding.symmetric(vertical=4, horizontal=10),
        expand=True,
        autofocus=True,
        on_submit=lambda e: add_custom_trigger(),
    )
    body = ft.Column(spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    def finish(skipped: bool = False):
        answers["name"] = (name_field.value or "").strip() or "Teman"
        answers["skipped_detail"] = skipped
        # Preset jam produktif diterjemahin jadi rentang jam beneran di sini,
        # biar Settings tinggal ngedit angka yang sama -- bukan dua sumber
        # kebenaran yang harus disamain terus.
        preset = storage.PRODUCTIVE_PRESETS.get(answers.get("productive_time", ""))
        answers["productive_hours"] = [[preset[0], preset[1]]] if preset else []
        storage.save_profile(answers)
        # Morning Brief ditandai udah "tampil" hari ini biar nggak langsung
        # nongol sedetik setelah onboarding -- user baru belum punya catatan
        # apa pun, jadi isinya cuma bakal "belum cukup data". Brief-nya mulai
        # nyapa besok, pas udah ada yang bisa dibaca.
        storage.set_last_brief_date()
        # Kalau user bilang lagi minum obat rutin, langsung tawarin setup-nya.
        navigate("med_setup" if answers.get("on_medication") == "ya" else "home")

    # ---------------------------------------------------------- pertanyaan
    # (key, judul, opsi, multi?, maks pilihan)
    QUESTIONS = [
        ("age_range", "Umur kamu di rentang mana?", {a: a for a in AGE_OPTIONS}, False, 1),
        ("status", "Sehari-hari kamu lagi...", storage.STATUS_OPTIONS, True, storage.MAX_STATUS),
        ("productive_time", "Jam Produktif kamu kapan?", storage.PRODUCTIVE_TIME_OPTIONS, False, 1),
        ("sleep_condition", "Tidur kamu belakangan gimana?", storage.SLEEP_OPTIONS, False, 1),
        ("on_medication", "Lagi minum obat rutin dari dokter?", storage.MEDICATION_OPTIONS, False, 1),
        ("overwhelm_triggers", "Apa yang paling sering bikin kamu kewalahan?",
         storage.TRIGGER_OPTIONS, True, storage.MAX_TRIGGERS),
    ]

    # Alasan tiap pertanyaan -- ditulis apa adanya biar nggak kerasa diinterogasi.
    WHY = {
        "age_range": "Cuma buat nyesuain bahasa Kalem. Nggak bisa diubah nanti.",
        "status": f"Biar Kalem tau seberapa kaku jadwal kamu. Boleh pilih sampai {storage.MAX_STATUS} — "
                  "mahasiswa sambil kerja itu wajar.",
        "productive_time": "Kalem bakal lebih pelan kalau kamu buka di luar jam ini. "
                           "Jamnya bisa diatur persis nanti di Pengaturan.",
        "sleep_condition": "Dipakai buat nebak beban kerja yang masuk akal hari ini.",
        "on_medication": "Kalau iya, Kalem bisa bantu ingetin stok obat. Kalau nggak, dilewat aja.",
        "overwhelm_triggers": f"Nentuin opsi mana yang muncul duluan pas kamu lagi kewalahan. "
                              f"Boleh pilih sampai {storage.MAX_TRIGGERS}, atau tulis sendiri.",
    }

    def picked_count(key: str) -> int:
        """Buat pertanyaan pemicu, yang diketik sendiri ikut kehitung kuotanya."""
        if key == "overwhelm_triggers":
            return len(answers["overwhelm_triggers"]) + len(answers["custom_triggers"])
        return len(answers[key])

    def pick(key: str, value: str, multi: bool, limit: int):
        if multi:
            current = answers[key]
            if value in current:
                current.remove(value)
            elif picked_count(key) < limit:
                current.append(value)
        else:
            answers[key] = value
            step["index"] += 1
        render()

    def add_custom_trigger():
        raw = (custom_field.value or "").strip()
        text = raw[:32]
        if (
            text
            and text not in answers["custom_triggers"]
            and picked_count("overwhelm_triggers") < storage.MAX_TRIGGERS
        ):
            answers["custom_triggers"].append(text)
        custom_field.value = ""
        step["custom_open"] = False
        render()

    def drop_custom_trigger(value: str):
        if value in answers["custom_triggers"]:
            answers["custom_triggers"].remove(value)
        render()

    def render():
        i = step["index"]

        # --- Layar 0: nama (selalu ditanya) ---
        if i == 0:
            body.controls = [
                ui_helpers.card(
                    ft.Column(
                        [
                            buddy.face("tenang", 110),
                            ui_helpers.title("Halo! Aku Kalem."),
                            ft.Text(
                                "Aku bakal nemenin kamu ngerjain hal-hal kecil tiap hari. "
                                "Boleh kenalan dulu?",
                                size=13,
                                color=theme.MUTED,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            name_field,
                            ui_helpers.wide_button("Lanjut", lambda e: next_from_name()),
                        ],
                        spacing=14,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                ),
                ui_helpers.disclaimer(
                    "Semua jawaban disimpan lokal di HP kamu aja, dan boleh diubah kapan pun."
                ),
            ]
            page.update()
            return

        # --- Selesai ---
        if i > len(QUESTIONS):
            finish()
            return

        key, question, options, multi, limit = QUESTIONS[i - 1]
        selected = answers[key]
        is_triggers = key == "overwhelm_triggers"

        chips: list[ft.Control] = [
            ui_helpers.choice_chip(
                label,
                (value in selected) if multi else (value == selected),
                lambda e, v=value: pick(key, v, multi, limit),
            )
            for value, label in options.items()
        ]

        # Pemicu ketikan sendiri: tampil sebagai chip aktif, pencet buat batal.
        if is_triggers:
            chips += [
                ui_helpers.choice_chip(t, True, lambda e, v=t: drop_custom_trigger(v))
                for t in answers["custom_triggers"]
            ]
            if picked_count(key) < limit:
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
                        on_click=lambda e: open_custom(),
                        ink=True,
                    )
                )

        card_items: list[ft.Control] = [
            ui_helpers.title(question, 18),
            ft.Text(WHY[key], size=12, color=theme.MUTED),
            ft.Row(chips, spacing=8, wrap=True, run_spacing=8),
        ]

        if is_triggers and step["custom_open"] and picked_count(key) < limit:
            card_items.append(
                ft.Row(
                    [
                        custom_field,
                        ft.IconButton(
                            icon=ft.Icons.CHECK,
                            icon_color=theme.PRIMARY,
                            icon_size=20,
                            on_click=lambda e: add_custom_trigger(),
                        ),
                    ],
                    spacing=4,
                )
            )

        controls: list[ft.Control] = [
            ft.Row(
                [
                    ft.Container(
                        height=4,
                        expand=True,
                        bgcolor=theme.PRIMARY if n < i else theme.BORDER,
                        border_radius=2,
                    )
                    for n in range(len(QUESTIONS))
                ],
                spacing=4,
            ),
            ft.Text(f"{i} dari {len(QUESTIONS)}", size=11, color=theme.MUTED),
            ui_helpers.card(ft.Column(card_items, spacing=12)),
        ]

        # Pertanyaan multi-pilih butuh tombol lanjut sendiri (nggak auto-maju
        # kayak pilihan tunggal, karena user belum tentu selesai milih).
        nav: list[ft.Control] = []
        if i > 1:
            nav.append(ft.TextButton(content=ft.Text("Kembali"), on_click=lambda e: go_back()))
        if multi:
            last = i == len(QUESTIONS)
            nav.append(
                ui_helpers.primary_button(
                    "Selesai" if last else "Lanjut",
                    (lambda e: finish()) if last else (lambda e: go_next()),
                    expand=True,
                )
            )
        if nav:
            controls.append(ft.Row(nav, spacing=8))

        # Umur (i == 1) wajib dijawab, jadi nggak ada tombol skip di situ.
        # Mulai pertanyaan berikutnya skip SELALU tersedia -- termasuk di
        # pertanyaan multi-pilih, biar aturannya konsisten: begitu skip
        # dipencet, onboarding langsung selesai ke Beranda.
        if i > 1:
            controls.append(
                ft.Row(
                    [
                        ft.TextButton(
                            content=ft.Text("Lewati, langsung ke Beranda", color=theme.MUTED),
                            on_click=lambda e: skip_to_home(),
                        )
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                )
            )

        body.controls = controls
        page.update()

    def open_custom():
        step["custom_open"] = True
        render()

    def next_from_name():
        if not (name_field.value or "").strip():
            name_field.error = "Isi dulu ya"
            page.update()
            return
        name_field.error = None
        step["index"] = 1
        render()

    def go_next():
        step["index"] += 1
        step["custom_open"] = False
        render()

    def go_back():
        step["index"] = max(step["index"] - 1, 0)
        step["custom_open"] = False
        render()

    def skip_to_home():
        """Dipencet dari pertanyaan status dst (i > 1). Nama & umur udah
        kejawab duluan sebelum tombol ini bisa muncul, jadi aman langsung
        disimpan -- sisanya default netral. Ini LANGSUNG selesai, bukan
        lompat ke pertanyaan berikutnya."""
        finish(skipped=True)

    render()
    return body
