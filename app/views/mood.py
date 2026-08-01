"""Page 3 -- Mood. Check-in mood harian + insight pola yang dipelajari
model dari data user sendiri. Cerita panjangnya ada di halaman Diary.
"""
from __future__ import annotations

import flet as ft

from app import buddy, storage, theme, ui_helpers
from app.core import recommendations
from app.core.energy_predictor import predict_workload, sleep_hours_for
from app.core.medication_model import missed_streak
from app.core.mood_model import (
    DAY_NAMES,
    QUICK_TAGS,
    analyse,
    checkin_streak,
    neglect_streak,
)
from app.views import mood_chart

SCORE_COLORS = {5: theme.PRIMARY, 4: theme.PRIMARY, 3: theme.WARN, 2: theme.WARN, 1: theme.DANGER}

# (key, pertanyaan, ikon) -- tri-state: None (belum dijawab) -> True (udah) ->
# False (belum) -> balik None. Sengaja BUKAN streak yang dipajang/bisa putus,
# cuma sinyal tambahan buat burnout classifier. Lihat mood_model.neglect_streak.
CARE_QUESTIONS = [
    ("ate_today", "Udah makan hari ini?", ft.Icons.RESTAURANT),
    ("rested_enough", "Istirahat cukup semalam?", ft.Icons.BEDTIME),
]


def build(page: ft.Page, navigate) -> ft.Control:
    latest = storage.latest_mood()
    today_log = storage.today_mood()
    state = {
        "mood": latest["mood"] if latest else buddy.DEFAULT_MOOD,
        "quick_tags": list(today_log.get("quick_tags", [])) if today_log else [],
        "custom_open": False,
        "care": {
            "ate_today": today_log.get("ate_today") if today_log else None,
            "rested_enough": today_log.get("rested_enough") if today_log else None,
        },
    }

    kalem_face = buddy.face(state["mood"], 130)
    kalem_words = ft.Text(
        buddy.greeting_for(state["mood"]), size=13, color=theme.ON_BACKGROUND, text_align=ft.TextAlign.CENTER
    )
    picker_holder = ft.Container()
    tags_holder = ft.Container()
    custom_field = ft.TextField(
        hint_text="Tulis tag sendiri, mis. sidang proposal",
        text_size=12,
        height=42,
        content_padding=ft.Padding.symmetric(vertical=4, horizontal=10),
        expand=True,
        autofocus=True,
        on_submit=lambda e: add_custom_tag(e),
    )
    care_holder = ft.Container()
    result_holder = ft.Container(visible=False)

    def pick_mood(mood: str):
        state["mood"] = mood
        kalem_face.src = buddy.asset_for(mood)
        kalem_words.value = buddy.greeting_for(mood)
        render_picker()
        page.update()

    def render_picker():
        picker_holder.content = buddy.mood_picker(state["mood"], pick_mood)

    # --- Tag cepat: dipencet dalam hitungan detik, tanpa harus nulis ---

    def toggle_tag(key: str):
        if key in state["quick_tags"]:
            state["quick_tags"].remove(key)
        elif len(state["quick_tags"]) < 3:
            state["quick_tags"].append(key)
        render_tags()
        page.update()

    def _tag_chip(key: str, label: str) -> ft.Container:
        on = key in state["quick_tags"]
        return ft.Container(
            content=ft.Text(label, size=11.5, color="#FFFFFF" if on else theme.ON_BACKGROUND),
            bgcolor=theme.SECONDARY if on else theme.SURFACE,
            border=ft.Border.all(1, theme.SECONDARY if on else theme.BORDER),
            border_radius=12,
            padding=ft.Padding.symmetric(vertical=7, horizontal=12),
            on_click=lambda e, k=key: toggle_tag(k),
            ink=True,
        )

    def add_custom_tag(e):
        raw = (custom_field.value or "").strip().lower()
        # Dipotong 24 karakter: ini tag, bukan tempat nulis cerita.
        tag = raw[:24]
        if not tag:
            state["custom_open"] = False
            render_tags()
            page.update()
            return
        if tag not in state["quick_tags"] and len(state["quick_tags"]) < 3:
            state["quick_tags"].append(tag)
        custom_field.value = ""
        state["custom_open"] = False
        render_tags()
        page.update()

    def open_custom(e):
        state["custom_open"] = True
        render_tags()
        page.update()

    def render_tags():
        chips = [_tag_chip(key, label) for key, label in QUICK_TAGS.items()]

        # Tag custom yang udah kepilih ikut ditampilin sebagai chip, biar
        # bisa dimatiin lagi persis kayak preset.
        chips += [
            _tag_chip(tag, tag) for tag in state["quick_tags"] if tag not in QUICK_TAGS
        ]

        full = len(state["quick_tags"]) >= 3
        if not full:
            chips.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.ADD, size=13, color=theme.MUTED),
                            ft.Text("Lainnya", size=11.5, color=theme.MUTED),
                        ],
                        spacing=3,
                        tight=True,
                    ),
                    border=ft.Border.all(1, theme.BORDER),
                    border_radius=12,
                    padding=ft.Padding.symmetric(vertical=7, horizontal=10),
                    on_click=open_custom,
                    ink=True,
                )
            )

        children: list[ft.Control] = [
            ui_helpers.subtitle("Hari ini isinya apa? (boleh dilewat, maks 3)", 12),
            ft.Row(chips, spacing=6, wrap=True, run_spacing=6),
        ]

        # Input tag custom muncul INLINE -- nggak pindah halaman, biar tetap
        # secepat mencet chip.
        if state["custom_open"] and not full:
            children.append(
                ft.Row(
                    [
                        custom_field,
                        ft.IconButton(
                            icon=ft.Icons.CHECK,
                            icon_color=theme.PRIMARY,
                            icon_size=20,
                            on_click=add_custom_tag,
                        ),
                    ],
                    spacing=4,
                )
            )

        tags_holder.content = ft.Column(children, spacing=8)

    # --- Eat & Rest Well: 2 toggle opsional, BUKAN streak yang dipajang ---

    def cycle_care(key: str):
        current = state["care"][key]
        state["care"][key] = {None: True, True: False, False: None}[current]
        render_care()
        page.update()

    def render_care():
        rows: list[ft.Control] = []
        for key, question, icon in CARE_QUESTIONS:
            value = state["care"][key]
            if value is True:
                label, bg, border, fg = "Udah", theme.PRIMARY, theme.PRIMARY, "#FFFFFF"
            elif value is False:
                label, bg, border, fg = "Belum", theme.WARN, theme.WARN, "#FFFFFF"
            else:
                label, bg, border, fg = "Tap buat jawab", theme.SURFACE, theme.BORDER, theme.MUTED
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(icon, size=16, color=theme.MUTED),
                            ft.Text(question, size=12, color=theme.ON_BACKGROUND, expand=True),
                            ft.Container(
                                content=ft.Text(label, size=10.5, color=fg, weight=ft.FontWeight.BOLD),
                                bgcolor=bg,
                                border=ft.Border.all(1, border),
                                border_radius=10,
                                padding=ft.Padding.symmetric(vertical=4, horizontal=10),
                            ),
                        ],
                        spacing=8,
                    ),
                    on_click=lambda e, k=key: cycle_care(k),
                    ink=True,
                    border_radius=10,
                    padding=ft.Padding.symmetric(vertical=4, horizontal=2),
                )
            )
        care_holder.content = ft.Column(
            [
                ui_helpers.subtitle("Udah makan & istirahat cukup? (opsional, boleh dilewat)", 12),
                *rows,
            ],
            spacing=4,
        )

    def save_checkin(e):
        mood = state["mood"]
        score = buddy.score_for(mood)
        energy = _energy_from_score(score)
        existing = storage.today_mood()
        storage.add_mood_log(
            mood=mood,
            score=score,
            energy=energy,
            # Jangan sampai check-in mood ngehapus cerita yang udah ditulis hari ini.
            diary=existing.get("diary", "") if existing else "",
            tags=existing.get("tags", []) if existing else None,
            quick_tags=state["quick_tags"],
            ate_today=state["care"]["ate_today"],
            rested_enough=state["care"]["rested_enough"],
        )

        sleep_condition = storage.get_profile().get("sleep_condition", "")
        # Dihitung SETELAH nyimpen, biar jawaban hari ini ikut kehitung.
        logs_now = storage.get_mood_logs()
        neglect_days = neglect_streak(logs_now)
        # `streak` di model artinya MOMENTUM (0-10), bukan total tugas selesai.
        # Dulu di sini dikirim jumlah tugas yang pernah kelar -- angka yang
        # naik terus, dan bikin model nyaranin beban lebih BERAT justru pas
        # mood & tidur user lagi paling parah.
        prediction = predict_workload(
            sleep_hours=sleep_hours_for(sleep_condition),
            mood_score=score,
            energy_level=energy,
            streak=checkin_streak(logs_now),
            neglect_days=neglect_days,
            # Obat yang nggak keabsen dianggap nggak diminum -- konteks yang
            # bikin hari berat punya penjelasan, bukan misteri.
            missed_med_days=missed_streak(storage.get_medication()),
        )
        color = {
            "rendah": theme.WARN,
            "sedang": theme.PRIMARY,
            "tinggi": theme.SUCCESS,
        }[prediction.workload_label]
        if prediction.burnout_risk:
            color = theme.DANGER

        result_holder.content = ft.Column(
            [
                ui_helpers.banner(
                    f"Beban kerja yang disaranin hari ini: {prediction.workload_label.upper()}",
                    color,
                    ft.Icons.INSIGHTS,
                ),
                ft.Text(prediction.advice, size=12.5, color=theme.ON_BACKGROUND),
            ],
            spacing=10,
        )
        result_holder.visible = True
        # Catatan baru = pola baru. Kartu insight & grafik digambar ulang di
        # sini; kalau nggak, dua-duanya masih nunjukkin data sebelum check-in
        # dan user ngira simpanannya nggak masuk.
        render_insight()
        render_history()
        page.update()
        offer_diary(mood)

    def offer_diary(mood: str):
        """Habis check-in, langsung tawarin nulis cerita.

        Mood picker cuma ngasih angka; cerita yang ngasih KONTEKS -- dan
        konteks itu yang bikin insight Kalem berhenti terdengar generik.
        Ditawarin di sini karena ini satu-satunya momen user udah kepikiran
        soal harinya. Nanya belakangan artinya nanya pas udah lupa.
        """
        # Udah nulis hari ini? Jangan nagih lagi.
        today_entry = storage.today_mood()
        if today_entry and (today_entry.get("diary") or "").strip():
            return

        def go(ev):
            page.pop_dialog()
            navigate("diary")

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Mau cerita dikit?", size=16),
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                buddy.face(mood, 56),
                                ft.Text(
                                    "Kamu udah nandain gimana rasanya. Kalau mau, "
                                    "cerita bentar soal APA yang bikin gitu — "
                                    "itu yang bantu aku ngerti pola kamu.",
                                    size=12.5,
                                    color=theme.ON_BACKGROUND,
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text(
                            "Dua kalimat juga cukup. Boleh dilewat kok.",
                            size=11,
                            color=theme.MUTED,
                        ),
                    ],
                    spacing=10,
                    tight=True,
                ),
                actions=[
                    ft.TextButton(
                        content=ft.Text("Nanti aja", color=theme.MUTED),
                        on_click=lambda ev: page.pop_dialog(),
                    ),
                    ui_helpers.primary_button("Cerita", go, icon=ft.Icons.MENU_BOOK),
                ],
            )
        )

    render_picker()
    render_tags()
    render_care()

    # ------------------------------------- kartu rekomendasi (Weekly Insight)
    # Lazy: baru manggil Gemini pas user beneran mau liat, bukan tiap buka
    # halaman Mood -- hemat kuota & nggak bikin halaman ini lemot dibuka.
    rec_state = {"cards": None, "index": 0}
    rec_holder = ft.Container()

    def render_rec():
        if rec_state["cards"] is None:
            rec_holder.content = ui_helpers.card(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.AUTO_AWESOME, color=theme.TERTIARY, size=20),
                        ft.Text(
                            "Kalem punya rekomendasi personal buat kamu",
                            size=12.5,
                            color=theme.ON_BACKGROUND,
                            expand=True,
                        ),
                        ft.TextButton(
                            content=ft.Text("Lihat", size=12, weight=ft.FontWeight.BOLD),
                            on_click=fetch_rec,
                        ),
                    ],
                    spacing=10,
                ),
                padding=14,
            )
            return

        cards = rec_state["cards"]
        current = cards[rec_state["index"]]
        icon = {"music": ft.Icons.MUSIC_NOTE, "recipe": ft.Icons.RESTAURANT_MENU}.get(
            current.kind, ft.Icons.AUTO_AWESOME
        )
        children: list[ft.Control] = [
            ft.Row(
                [
                    ft.Icon(icon, color=theme.TERTIARY, size=20),
                    ft.Text(current.title, size=14, weight=ft.FontWeight.BOLD, color=theme.ON_BACKGROUND, expand=True),
                ],
                spacing=8,
            ),
            ft.Text(current.body, size=12.5, color=theme.ON_BACKGROUND),
        ]
        if current.kind == "empty":
            children.append(
                ui_helpers.wide_button("Isi Favorit", lambda e: navigate("favorites"), icon=ft.Icons.FAVORITE_BORDER)
            )
        elif len(cards) > 1:
            children.append(
                ft.Row(
                    [
                        ft.TextButton(
                            content=ft.Text(
                                f"Lihat lainnya ({rec_state['index'] + 1}/{len(cards)})", size=12
                            ),
                            on_click=next_rec,
                        )
                    ],
                    alignment=ft.MainAxisAlignment.END,
                )
            )
        rec_holder.content = ui_helpers.card(ft.Column(children, spacing=8), padding=16)

    def fetch_rec(e):
        # Free tier: 1 kartu per minggu (tiap kartu = panggilan Gemini).
        if not storage.can_see_reco_card():
            rec_holder.content = ui_helpers.card(
                ui_helpers.upgrade_hint(
                    "Jatah kartu rekomendasi minggu ini udah kepakai. "
                    "Premium bisa terus-terusan, dan makin personal seiring data."
                ),
                padding=14,
            )
            page.update()
            return

        favorites = storage.get_favorites()
        # Energi diambil dari yang dikunci hari ini, bukan dari mood log lama.
        energy_level = storage.today_energy() or (latest.get("energy", 3) if latest else 3)

        async def kerjakan():
            cards = await ui_helpers.jalankan_dengan_progres(
                page, rec_holder,
                lambda: recommendations.build_cards(favorites, energy_level),
                "Kalem lagi mikir rekomendasi buat kamu...",
            )
            # Kartu "isi Favorit dulu" nggak motong kuota -- itu bukan
            # rekomendasi, itu ajakan ngelengkapin data.
            if not (len(cards) == 1 and cards[0].kind == "empty"):
                storage.record_reco_card()
            rec_state["cards"] = cards
            rec_state["index"] = 0
            render_rec()
            page.update()

        page.run_task(kerjakan)

    def next_rec(e):
        cards = rec_state["cards"] or []
        if cards:
            rec_state["index"] = (rec_state["index"] + 1) % len(cards)
        render_rec()
        page.update()

    render_rec()

    # ------------------------------------------------------------ insight
    # Dibungkus holder + fungsi render sendiri supaya bisa DIGAMBAR ULANG
    # setelah check-in. Sebelumnya insight dihitung sekali pas halaman
    # dibangun, jadi habis nyimpen check-in kartunya masih nunjukkin data
    # lama sampai user pindah halaman -- keliatan kayak simpanannya gagal.
    insight_holder = ft.Container()

    def render_insight():
        insight = analyse(storage.get_mood_logs())
        children: list[ft.Control] = [
            ui_helpers.section_header("Yang Kalem pelajari tentang kamu"),
            ft.Text(insight.headline, size=13, weight=ft.FontWeight.BOLD,
                    color=theme.ON_BACKGROUND),
        ]

        # Free tier: 1 highlight aja. Premium: semua temuan.
        # Yang dikunci KEDALAMAN (berapa banyak pola yang dibuka), bukan
        # aksesnya -- user gratis tetap dapat insight yang beneran kepakai.
        premium = storage.is_premium()
        shown = insight.details if premium else insight.details[:1]
        hidden = 0 if premium else max(0, len(insight.details) - 1)

        for detail in shown:
            children.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CIRCLE, size=6, color=theme.PRIMARY),
                        ft.Text(detail, size=12.5, color=theme.MUTED, expand=True),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                )
            )

        if hidden:
            children.append(
                ui_helpers.upgrade_hint(
                    f"Ada {hidden} temuan lagi yang kebaca dari catatan kamu. "
                    "Kebuka semua di Premium."
                )
            )

        if not insight.ready:
            children.append(
                ft.ProgressBar(
                    value=insight.log_count / 5,
                    color=theme.PRIMARY,
                    bgcolor=theme.BORDER,
                    bar_height=6,
                )
            )
        insight_holder.content = ft.Column(children, spacing=8)

    render_insight()

    # ------------------------------------------------------- riwayat mood
    # Default: bar chart 7-hari (murah, cocok buat sekilas lihat minggu ini).
    # "Lihat grafik bulanan" upgrade opsional -- garis + area per bulan.
    _y, _m = mood_chart.today_year_month()
    history_state = {"view": "week", "year": _y, "month": _m}
    history_holder = ft.Container()

    def render_history():
        children: list[ft.Control] = []
        if history_state["view"] == "week":
            children.append(
                ft.Row(
                    [
                        ui_helpers.section_header("7 catatan terakhir"),
                        ft.Container(expand=True),
                        ft.TextButton(
                            content=ft.Text("Lihat grafik bulanan", size=11.5, color=theme.PRIMARY),
                            on_click=lambda e: switch_history("month"),
                        ),
                    ],
                )
            )
            logs = storage.get_mood_logs()[:7]
            if logs:
                bars: list[ft.Control] = []
                for log in reversed(logs):
                    weekday = log.get("weekday")
                    label = DAY_NAMES[weekday][:3] if weekday is not None else log["date"][-2:]
                    bars.append(
                        ft.Column(
                            [
                                ft.Container(
                                    width=18,
                                    height=max(8, log["score"] * 14),
                                    bgcolor=SCORE_COLORS.get(log["score"], theme.MUTED),
                                    border_radius=5,
                                ),
                                ft.Text(label, size=9, color=theme.MUTED),
                            ],
                            spacing=4,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        )
                    )
                children.append(
                    ft.Container(
                        content=ft.Row(bars, spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                        alignment=ft.Alignment.BOTTOM_CENTER,
                        height=100,
                    )
                )
            else:
                children.append(ui_helpers.empty_state("Belum ada catatan mood.", ft.Icons.MOOD))
        else:
            children.append(
                ft.Row(
                    [
                        ui_helpers.section_header("Grafik bulanan"),
                        ft.Container(expand=True),
                        ft.TextButton(
                            content=ft.Text("Lihat 7 hari", size=11.5, color=theme.PRIMARY),
                            on_click=lambda e: switch_history("week"),
                        ),
                    ],
                )
            )
            children.append(
                mood_chart.month_nav(
                    history_state["year"], history_state["month"], shift_month(-1), shift_month(1)
                )
            )
            children.append(
                mood_chart.build_month_chart(
                    storage.get_mood_logs(), history_state["year"], history_state["month"], SCORE_COLORS
                )
            )
            # Bulan lampau = tren jangka panjang, itu bagian premium.
            # Bulan berjalan tetap kebuka gratis.
            if not storage.is_premium():
                children.append(
                    ui_helpers.upgrade_hint(
                        "Bulan ini kebuka gratis. Premium bisa telusuri "
                        "bulan-bulan sebelumnya buat lihat tren panjang."
                    )
                )
        history_holder.content = ft.Column(children, spacing=8)

    def switch_history(view: str):
        history_state["view"] = view
        render_history()
        page.update()

    def shift_month(delta: int):
        def handler(e):
            y, m = mood_chart.shift_month(
                history_state["year"], history_state["month"], delta
            )
            # Free tier dikunci di bulan berjalan. Bukan dibiarin kepencet
            # terus nggak ngapa-ngapain -- itu kelihatan kayak bug.
            cy, cm = mood_chart.today_year_month()
            if not storage.is_premium() and (y, m) != (cy, cm):
                page.show_dialog(
                    ft.AlertDialog(
                        modal=True,
                        title=ft.Text("Tren bulan lain", size=16),
                        content=ft.Text(
                            "Telusur bulan-bulan sebelumnya ada di Premium. "
                            "Grafik bulan ini tetap kebuka gratis.",
                            size=13,
                        ),
                        actions=[
                            ft.TextButton(
                                content=ft.Text("Oke"), on_click=lambda ev: page.pop_dialog()
                            )
                        ],
                    )
                )
                return
            history_state["year"], history_state["month"] = y, m
            render_history()
            page.update()

        return handler

    render_history()

    return ft.Column(
        [
            ui_helpers.page_header("Mood"),
            ui_helpers.card(
                ft.Column(
                    [
                        kalem_face,
                        kalem_words,
                        ft.Divider(color=theme.BORDER, height=1),
                        ui_helpers.subtitle("Hari ini kamu ngerasa gimana?"),
                        picker_holder,
                        tags_holder,
                        care_holder,
                        ui_helpers.wide_button("Simpan check-in", save_checkin),
                    ],
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
            ),
            result_holder,
            ui_helpers.nav_link_card(
                ft.Icons.MENU_BOOK,
                theme.PRIMARY,
                "Cerita tentang hari ini?",
                "Kalem dengerin. Ceritanya juga bantu dia ngerti pola kamu.",
                lambda e: navigate("diary"),
            ),
            ui_helpers.nav_link_card(
                ft.Icons.FAVORITE_BORDER,
                theme.TERTIARY,
                "Favorit kamu",
                f"{storage.favorites_filled()}/{len(storage.FAVORITE_FIELDS)} terisi · "
                "bikin saran Kalem lebih personal",
                lambda e: navigate("favorites"),
            ),
            ui_helpers.card(insight_holder),
            rec_holder,
            ui_helpers.card(history_holder),
            ui_helpers.disclaimer(
                "Pola di atas dipelajari dari catatan kamu sendiri, bukan diagnosis. "
                "Makin sering diisi, makin akurat -- dan tetap bukan penilaian klinis."
            ),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


def _energy_from_score(score: int) -> int:
    """Skor mood (1-5) -> level energi awal (1-6)."""
    return {1: 1, 2: 2, 3: 3, 4: 5, 5: 6}.get(score, 3)
