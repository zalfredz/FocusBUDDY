"""Setup Medication Companion -- dibuka sekali di awal, bukan halaman harian.

SOAL PAYWALL: pengingat stok & cari apotek SENGAJA tetap gratis. Nggak
kehabisan obat resep itu fungsi dasar, bukan kenyamanan -- dan prinsip
paywall app ini cuma ngunci kedalaman. Yang premium di sini cuma lapisan
analisisnya (riwayat kepatuhan & ekspor buat dokter), bukan pengingatnya.


Setelah user isi di sini, sisanya jalan di belakang layar: stok turun tiap
user mencet "Udah minum" di Home, dan Home juga yang nampilin pengingat
kalau stoknya mau habis.

Yang SENGAJA nggak ada di sini: rekomendasi dosis. Angka dosis yang diisi
user itu yang sudah ditentukan dokternya. FocusBuddy nggak pernah nyaranin
atau ngitungin "dosis wajar" -- di luar kapasitas app, dan berisiko buat
obat psikotropika terkontrol seperti metilfenidat.
"""
from __future__ import annotations

import flet as ft

from app import buddy, clock, storage, theme, ui_helpers
from app.core import bpom
from app.core.medication_model import (
    ONLINE_PHARMACY_PARTNERS,
    REMINDER_THRESHOLD_DAYS,
    check_status,
    maps_search_url,
    missed_streak,
)


def build(page: ft.Page, navigate) -> ft.Control:
    existing = storage.get_medication()
    status = check_status(existing)

    bpom_holder = ft.Container()

    def check_name(e=None):
        """Cek nama obat ke registri BPOM sambil user ngetik.

        Offline & instan (~10 ms buat 8.960 nama), jadi nggak perlu nunggu
        disimpan dulu. Hasilnya SELALU informasi, nggak pernah ngeblokir --
        lihat catatan di bawah soal nama yang nggak ketemu.
        """
        typed = (name_field.value or "").strip()
        if not typed or not bpom.available():
            bpom_holder.content = None
            page.update()
            return

        match = bpom.lookup(typed)

        if not match.found:
            # TETAP BOLEH DISIMPAN. Racikan apotek dan obat yang belum masuk
            # unduhan registri itu nyata ada -- nolak nyimpen bakal ngunci
            # pengingat dari orang yang justru paling butuh.
            # Alasan paling sering kenapa produk yang JELAS ADA nggak ketemu:
            # jamu, herbal, dan suplemen didaftarin BPOM di daftar TERPISAH
            # (nomor TR/SD/POM), bukan di Master Produk Komoditi Obat ini.
            # Diomongin terus terang biar user nggak ngira dia salah ketik.
            bpom_holder.content = _note_row(
                ft.Icons.HELP_OUTLINE,
                theme.MUTED,
                "Nggak ketemu di daftar obat BPOM. Tetap bisa disimpan kok — "
                "jamu, suplemen, dan racikan apotek emang terdaftar di daftar "
                "yang beda, jadi wajar nggak muncul di sini.",
            )
            page.update()
            return

        rows: list[ft.Control] = []
        saran = bpom.suggestion_for(typed, match)
        catatan_zat = bpom.ingredient_note(match)

        if saran:
            rows.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SPELLCHECK, size=15, color=theme.WARN),
                        ft.Text(f"Maksudnya {saran}?", size=12,
                                color=theme.ON_BACKGROUND, expand=True),
                        ft.TextButton(
                            content=ft.Text("Pakai", size=11.5),
                            on_click=lambda ev, n=saran: use_name(n),
                        ),
                    ],
                    spacing=6,
                )
            )
        elif catatan_zat:
            rows.append(_note_row(ft.Icons.SCIENCE, theme.SECONDARY, catatan_zat))
        else:
            rows.append(
                _note_row(
                    ft.Icons.VERIFIED,
                    theme.SUCCESS,
                    f"Terdaftar di BPOM — {match.name}",
                )
            )

        rows.append(
            ft.Text(bpom.summary(match), size=10.5, color=theme.MUTED)
        )

        if match.butuh_resep:
            rows.append(
                _note_row(
                    ft.Icons.LOCK_OUTLINE,
                    theme.TERTIARY,
                    f"Golongan {match.golongan.lower()} — cuma boleh dengan resep dokter.",
                )
            )
        if match.registrasi_kedaluwarsa:
            rows.append(
                _note_row(
                    ft.Icons.SCHEDULE,
                    theme.MUTED,
                    f"Izin edarnya tercatat berlaku sampai {match.berlaku_sampai}. "
                    "Ini soal registrasi, bukan tanggal kedaluwarsa obatnya.",
                )
            )

        bpom_holder.content = ft.Container(
            content=ft.Column(rows, spacing=5),
            bgcolor=theme.BACKGROUND,
            border_radius=10,
            padding=ft.Padding.symmetric(vertical=8, horizontal=10),
        )
        page.update()

    def use_name(name: str):
        name_field.value = name
        check_name()

    name_field = ft.TextField(
        label="Nama obat",
        value=existing["name"] if existing else "",
        hint_text="mis. Concerta 18mg",
        on_change=check_name,
    )
    stock_field = ft.TextField(
        label="Sisa stok sekarang (jumlah pil)",
        value=str(int(existing["pills_left"])) if existing else "",
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    dose_field = ft.TextField(
        label="Sesuai resep dokter, berapa pil per hari",
        value=str(existing["pills_per_day"]) if existing else "1",
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    status_holder = ft.Container(visible=False)
    pharmacy_holder = ft.Column(spacing=10, visible=False)

    def render_status():
        current = check_status(storage.get_medication())
        if not current.active:
            status_holder.visible = False
            return

        color = theme.DANGER if current.needs_reminder else theme.SUCCESS
        message = current.message or (
            f"Stok {current.name} cukup buat sekitar {current.days_left} hari lagi."
        )

        children: list[ft.Control] = [
            ui_helpers.banner(message, color, "med"),
            ft.Text(
                f"Sisa {current.pills_remaining:g} pil. Kalem bakal ingetin otomatis "
                f"{REMINDER_THRESHOLD_DAYS} hari sebelum habis — kamu nggak perlu buka "
                "halaman ini tiap hari.",
                size=12,
                color=theme.MUTED,
            ),
        ]

        if current.taken_today:
            children.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE, color=theme.SUCCESS, size=16),
                        ft.Text("Udah diabsen hari ini.", size=12, color=theme.SUCCESS),
                    ],
                    spacing=6,
                )
            )

        # Hari yang nggak keabsen dianggap nggak diminum. Ditulis sebagai
        # KETERANGAN, bukan teguran -- dan sekalian ngasih tau kalau angka
        # stoknya mungkin ketinggalan dari kenyataan.
        missed = missed_streak(storage.get_medication())
        if missed:
            children.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.INFO_OUTLINE, color=theme.WARN, size=16),
                        ft.Text(
                            f"{missed} hari terakhir belum keabsen — Kalem nganggapnya "
                            "belum diminum, jadi ekspektasi hari ini diturunin dikit. "
                            "Kalau ternyata udah diminum, stok di atas boleh dibenerin.",
                            size=11.5,
                            color=theme.MUTED,
                            expand=True,
                        ),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                )
            )

        children.append(
            ui_helpers.wide_button(
                "Cari apotek terdekat", show_pharmacies, icon=ft.Icons.LOCATION_ON
            )
        )
        status_holder.content = ft.Column(children, spacing=10)
        status_holder.visible = True

    def show_pharmacies(e):
        """Serahin pencarian ke Google Maps -- datanya beneran hidup.

        Sengaja nggak bikin daftar apotek + "stok tersedia" sendiri: itu
        bakal keliatan meyakinkan padahal isinya karangan.
        """
        rows: list[ft.Control] = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.MAP, color=theme.PRIMARY, size=20),
                        ft.Column(
                            [
                                ft.Text("Buka apotek terdekat di Maps",
                                        size=13, weight=ft.FontWeight.BOLD,
                                        color=theme.ON_BACKGROUND),
                                ft.Text("Pakai lokasi kamu sekarang", size=11, color=theme.MUTED),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.OPEN_IN_NEW, color=theme.MUTED, size=16),
                    ],
                    spacing=10,
                ),
                padding=ft.Padding.symmetric(vertical=12, horizontal=12),
                bgcolor=theme.BACKGROUND,
                border_radius=12,
                url=maps_search_url("apotek terdekat"),
                ink=True,
            ),
            ft.Divider(color=theme.BORDER, height=1),
            ui_helpers.section_header("Atau tebus daring"),
        ]
        rows += [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.SHOPPING_BAG, color=theme.SECONDARY, size=18),
                        ft.Column(
                            [
                                ft.Text(p["name"], size=13, weight=ft.FontWeight.BOLD,
                                        color=theme.ON_BACKGROUND),
                                ft.Text(p["desc"], size=11, color=theme.MUTED),
                            ],
                            spacing=0,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.OPEN_IN_NEW, color=theme.MUTED, size=16),
                    ],
                    spacing=10,
                ),
                padding=ft.Padding.symmetric(vertical=8, horizontal=10),
                bgcolor=theme.BACKGROUND,
                border_radius=12,
                url=p["url"],
                ink=True,
            )
            for p in ONLINE_PHARMACY_PARTNERS
        ]
        pharmacy_holder.controls = rows
        pharmacy_holder.visible = True
        page.update()

    def save(e):
        name = (name_field.value or "").strip()
        try:
            pills_left = int(float(stock_field.value or 0))
            per_day = float(dose_field.value or 1)
        except ValueError:
            stock_field.error = "Masukin angka ya"
            page.update()
            return
        stock_field.error = None

        if not name:
            name_field.error = "Isi nama obatnya dulu"
            page.update()
            return
        name_field.error = None

        if pills_left <= 0 or per_day <= 0:
            stock_field.error = "Stok dan dosis harus lebih dari 0"
            page.update()
            return

        storage.set_medication(name, pills_left, per_day)
        # Hasil registri ikut disimpan: golongan & NIE dipakai di tempat lain
        # tanpa perlu cari ulang, dan jadi jejak "ini divalidasi kapan".
        found = bpom.lookup(name)
        if found.found:
            storage.set_medication_registry(
                {"nama_resmi": found.name, "nie": found.nie,
                 "golongan": found.golongan, "cocok": found.matched_by}
            )
        # Semua kartu turunan ikut digambar ulang. Sebelumnya cuma
        # `render_status()` yang jalan, jadi kartu riwayat kepatuhan pakai
        # `status` hasil hitungan waktu halaman dibangun -- nggak muncul
        # sampai halamannya dibuka ulang.
        refresh_cards()
        page.update()

    def turn_off(e):
        storage.disable_medication()
        status_holder.visible = False
        pharmacy_holder.visible = False
        refresh_cards()
        page.update()

    def refresh_cards():
        render_status()
        adherence_holder.content = _adherence_card(check_status(storage.get_medication()))

    adherence_holder = ft.Container()
    refresh_cards()
    check_name()

    actions: list[ft.Control] = [
        ui_helpers.primary_button("Simpan", save, icon=ft.Icons.SAVE, expand=True)
    ]
    if status.active:
        actions.append(ft.TextButton(content=ft.Text("Matikan"), on_click=turn_off))

    kalem_note = ft.Row(
        [
            buddy.face("tenang", 54),
            ft.Container(
                content=buddy.speech_bubble(
                    "Biar aku bisa bantuin ingetin, tanpa kamu harus ngitung-ngitung sendiri."
                ),
                expand=True,
            ),
        ],
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    return ft.Column(
        [
            ui_helpers.page_header(
                "Pengingat Obat",
                on_back=lambda e: navigate("home"),
                leading=ui_helpers.med_icon(26, theme.TERTIARY),
            ),
            ui_helpers.subtitle(
                "Opsional — buat kamu yang lagi pakai obat resep rutin. "
                "Cukup diisi sekali, sisanya Kalem yang hitung."
            ),
            kalem_note,
            ui_helpers.card(
                ft.Column([name_field, bpom_holder, stock_field, dose_field,
                          ft.Row(actions, spacing=8)], spacing=12)
            ),
            status_holder,
            pharmacy_holder,
            adherence_holder,
            ui_helpers.card(
                ft.Column(
                    [
                        ui_helpers.section_header("Privasi"),
                        ft.Text(
                            "Data obat disimpan lokal di perangkat ini aja, nggak ikut ke-sync "
                            "ke mana pun. Notifikasi pengingat sengaja ditulis netral "
                            "(\"Waktunya check-in ya\") — nama obatnya nggak muncul di banner.",
                            size=12,
                            color=theme.MUTED,
                        ),
                    ],
                    spacing=6,
                ),
                padding=14,
            ),
            ui_helpers.disclaimer(
                "Fitur ini bukan alat diagnosis atau pengganti dokter. FocusBuddy nggak "
                "nyaranin dosis — angka di atas yang kamu isi sesuai resep dokter kamu."
            ),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


def _note_row(icon: str, color: str, text: str) -> ft.Control:
    """Satu baris catatan kecil: ikon + teks. Dipakai kartu validasi BPOM."""
    return ft.Row(
        [
            ft.Icon(icon, size=15, color=color),
            ft.Text(text, size=11.5, color=theme.MUTED, expand=True),
        ],
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def _adherence_card(status) -> ft.Control:
    """Riwayat kepatuhan -- lapisan PREMIUM di atas pengingat yang gratis.

    Yang dikunci cuma analisisnya (persentase, streak, ekspor buat dokter).
    Pengingat stok, tombol absen, dan cari apotek tetap kebuka buat semua
    orang: itu keselamatan, bukan fitur mewah.
    """
    if not status.active:
        return ft.Container()

    if not storage.is_premium():
        return ui_helpers.card(
            ft.Column(
                [
                    ui_helpers.section_header("Riwayat kepatuhan"),
                    ui_helpers.upgrade_hint(
                        "Premium: lihat persentase hari kamu absen tepat waktu, "
                        "pola bolongnya di mana, dan ringkasan yang bisa "
                        "ditunjukin ke dokter pas kontrol."
                    ),
                    ft.Text(
                        "Pengingat stok & cari apotek tetap gratis selamanya.",
                        size=10.5,
                        color=theme.MUTED,
                    ),
                ],
                spacing=8,
            ),
            padding=14,
        )

    med = storage.get_medication() or {}
    log = med.get("take_log", [])
    from datetime import date, timedelta

    today = clock.today()
    # Jendelanya dipotong ke UMUR pemakaian, bukan selalu 30 hari. Kalau
    # nggak, orang yang baru setup kemarin dan patuh 100% ditampilin "3%" --
    # angka yang salah total, di kartu yang teksnya sendiri nyaranin
    # ditunjukin ke dokter.
    try:
        start = date.fromisoformat(med.get("start_date", ""))
        age = (today - start).days + 1
    except (TypeError, ValueError):
        age = 30
    window = max(1, min(30, age))
    days = [today - timedelta(days=i) for i in range(window)]
    taken = set(log)
    hits = sum(1 for d in days if d.isoformat() in taken)
    pct = round(hits / window * 100)

    # Streak berjalan: berapa hari berturut-turut dari hari ini ke belakang.
    streak = 0
    for d in days:
        if d.isoformat() in taken:
            streak += 1
        else:
            break

    dots = ft.Row(
        [
            ft.Container(
                width=8,
                height=8,
                border_radius=4,
                bgcolor=theme.PRIMARY if d.isoformat() in taken else theme.BORDER,
            )
            for d in reversed(days)
        ],
        spacing=2,
        wrap=True,
        run_spacing=3,
    )

    return ui_helpers.card(
        ft.Column(
            [
                ft.Row(
                    [
                        ui_helpers.section_header("Riwayat kepatuhan"),
                        ft.Container(expand=True),
                        ft.Icon(ft.Icons.WORKSPACE_PREMIUM, size=14, color=theme.TERTIARY),
                    ],
                ),
                ft.Text(
                    f"{pct}% kamu absen ({hits} dari {window} hari"
                    + (" sejak dicatat)." if window < 30 else " terakhir)."),
                    size=13,
                    weight=ft.FontWeight.BOLD,
                    color=theme.ON_BACKGROUND,
                ),
                ft.Text(
                    f"Lagi {streak} hari berturut-turut." if streak
                    else "Belum absen hari ini.",
                    size=11.5,
                    color=theme.MUTED,
                ),
                dots,
                ft.Text(
                    "Angka ini cuma seakurat absen kamu — bukan rekam medis. "
                    "Kalau mau ditunjukin ke dokter, sampaikan juga hari-hari "
                    "yang lupa diabsen.",
                    size=10.5,
                    color=theme.MUTED,
                ),
            ],
            spacing=8,
        ),
        padding=14,
    )
