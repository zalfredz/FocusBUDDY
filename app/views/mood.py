"""Halaman check-in dan insight mood."""
from __future__ import annotations

import flet as ft

from app import buddy, clock, storage, theme, ui_helpers
from app.core import recommendations
from app.core.energy_predictor import (
    predict_workload,
    sleep_hours_for,
)
from app.core.medication_model import missed_streak
from app.core.mood_model import (
    analyse,
    checkin_streak,
    neglect_streak,
)
from app.views import mood_chart

SCORE_COLORS = {5: theme.PRIMARY, 4: theme.PRIMARY, 3: theme.WARN, 2: theme.WARN, 1: theme.DANGER}

CARE_MAKAN = ("ate_today", "Udah makan hari ini?", ft.Icons.RESTAURANT)
CARE_ISTIRAHAT = ("rested_enough", "Istirahat cukup semalam?", ft.Icons.BEDTIME)
CARE_QUESTIONS = [CARE_MAKAN, CARE_ISTIRAHAT]


def _care_hari_ini() -> list[tuple]:
    if storage.waktunya_tanya_makan():
        return [CARE_MAKAN, CARE_ISTIRAHAT]
    return [CARE_ISTIRAHAT]


def build(page: ft.Page, navigate) -> ft.Control:
    def open_favorites(e=None) -> None:
        setattr(page, "_focusbuddy_favorites_return", "mood")
        navigate("favorites")

    today_log = storage.today_mood()
    latest = today_log or storage.latest_mood()
    state = {
        "mood": latest["mood"] if latest else buddy.DEFAULT_MOOD,
        "care": {
            "ate_today": today_log.get("ate_today") if today_log else None,
            "rested_enough": today_log.get("rested_enough") if today_log else None,
        },
        "energy": (
            today_log.get("energy")
            if today_log and today_log.get("energy")
            else storage.today_energy()
            or _energy_from_score(buddy.score_for(latest["mood"] if latest else buddy.DEFAULT_MOOD))
        ),
        "energy_touched": bool(today_log and today_log.get("energy")),
        "has_checkin": today_log is not None,
        "editing": today_log is None,
    }

    kalem_face = buddy.face(state["mood"], 130)
    kalem_words = ft.Text(
        buddy.greeting_for(state["mood"]), size=13, color=theme.ON_BACKGROUND, text_align=ft.TextAlign.CENTER
    )
    picker_holder = ft.Container()
    energy_holder = ft.Container()
    care_holder = ft.Container()
    checkin_holder = ft.Container()
    result_holder = ft.Container(visible=False)

    def pick_mood(mood: str):
        state["mood"] = mood
        kalem_face.src = buddy.asset_for(mood)
        kalem_words.value = buddy.greeting_for(mood)
        if not state["energy_touched"]:
            state["energy"] = _energy_from_score(buddy.score_for(mood))
            render_energy()
        render_picker()
        page.update()

    def render_picker():
        picker_holder.content = buddy.mood_picker(state["mood"], pick_mood)


    def pick_energy(level: int):
        state["energy"] = level
        state["energy_touched"] = True
        render_energy()
        page.update()

    def render_energy():
        chips: list[ft.Control] = []
        for level in range(1, 7):
            active = level == state["energy"]
            chips.append(
                ft.Container(
                    content=ft.Text(
                        str(level),
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color="#FFFFFF" if active else theme.ON_BACKGROUND,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    height=40,
                    expand=True,
                    bgcolor=theme.PRIMARY if active else theme.SURFACE,
                    border=ft.Border.all(1, theme.PRIMARY if active else theme.BORDER),
                    border_radius=12,
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda e, lv=level: pick_energy(lv),
                    ink=True,
                )
            )
        energy_holder.content = ft.Column(
            [
                ui_helpers.subtitle("Tenaga kamu sekarang gimana? (1-6)"),
                ft.Row(chips, spacing=6),
            ],
            spacing=8,
        )


    def cycle_care(key: str):
        current = state["care"][key]
        state["care"][key] = {None: True, True: False, False: None}[current]
        render_care()
        page.update()

    def render_care():
        rows: list[ft.Control] = []
        for key, question, icon in _care_hari_ini():
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
        judul = (
            "Udah makan & istirahat cukup? (opsional, boleh dilewat)"
            if storage.waktunya_tanya_makan()
            else "Istirahat cukup semalam? (opsional, boleh dilewat)"
        )
        care_holder.content = ft.Column(
            [ui_helpers.subtitle(judul, 12), *rows],
            spacing=4,
        )

    def render_condition():
        current = storage.today_mood()
        if not current:
            result_holder.visible = False
            result_holder.content = None
            return
        sleep_condition = storage.get_profile().get("sleep_condition", "")
        logs_now = storage.get_mood_logs()
        neglect_days = neglect_streak(logs_now)
        prediction = predict_workload(
            sleep_hours=sleep_hours_for(sleep_condition),
            mood_score=int(current.get("score", 3)),
            energy_level=int(current.get("energy", 3)),
            streak=checkin_streak(logs_now),
            neglect_days=neglect_days,
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

    def load_today_into_state():
        current = storage.today_mood()
        if not current:
            return
        state["mood"] = current.get("mood", buddy.DEFAULT_MOOD)
        state["energy"] = int(current.get("energy", 3) or 3)
        state["energy_touched"] = True
        state["care"] = {
            "ate_today": current.get("ate_today"),
            "rested_enough": current.get("rested_enough"),
        }
        kalem_face.src = buddy.asset_for(state["mood"])
        kalem_words.value = buddy.greeting_for(state["mood"])
        render_picker()
        render_energy()
        render_care()

    def begin_edit(e):
        load_today_into_state()
        state["editing"] = True
        render_checkin()
        page.update()

    def cancel_edit(e):
        load_today_into_state()
        state["editing"] = False
        render_checkin()
        page.update()

    def render_checkin():
        if state["has_checkin"] and not state["editing"]:
            summary: list[ft.Control] = [
                kalem_face,
                ft.Text(
                    f"{buddy.MOOD_LABELS.get(state['mood'], state['mood'].title())} "
                    f"· Energi {state['energy']}/6",
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    color=theme.ON_BACKGROUND,
                ),
            ]
            summary.extend(
                [
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                content=ft.Text("Sudah check-in", weight=ft.FontWeight.BOLD),
                                icon=ft.Icons.CHECK_CIRCLE,
                                disabled=True,
                                expand=True,
                            )
                        ],
                        spacing=0,
                    ),
                    ft.TextButton(
                        content=ft.Text("Ubah check-in"),
                        icon=ft.Icons.EDIT_OUTLINED,
                        on_click=begin_edit,
                    ),
                ]
            )
            checkin_holder.content = ui_helpers.card(
                ft.Column(
                    summary,
                    spacing=10,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
            return

        actions: list[ft.Control] = [
            ui_helpers.wide_button(
                "Simpan perubahan" if state["has_checkin"] else "Simpan check-in",
                save_checkin,
            )
        ]
        if state["has_checkin"]:
            actions.append(
                ft.TextButton(content=ft.Text("Batal"), on_click=cancel_edit)
            )
        checkin_holder.content = ui_helpers.card(
            ft.Column(
                [
                    kalem_face,
                    kalem_words,
                    ft.Divider(color=theme.BORDER, height=1),
                    ui_helpers.subtitle("Hari ini kamu ngerasa gimana?"),
                    picker_holder,
                    energy_holder,
                    care_holder,
                    *actions,
                ],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    def save_checkin(e):
        was_existing = bool(state["has_checkin"])
        mood = state["mood"]
        score = buddy.score_for(mood)
        energy = int(state["energy"])
        existing = storage.today_mood()
        storage.add_mood_log(
            mood=mood,
            score=score,
            energy=energy,
            diary=existing.get("diary", "") if existing else "",
            tags=existing.get("tags", []) if existing else None,
            quick_tags=existing.get("quick_tags", []) if existing else [],
            ate_today=state["care"]["ate_today"],
            rested_enough=state["care"]["rested_enough"],
        )
        storage.set_today_energy(energy)
        state["has_checkin"] = True
        state["editing"] = False
        render_checkin()
        render_condition()
        render_insight()
        render_history()
        rec_state["cards"] = None
        rec_state["index"] = 0
        render_rec()
        page.update()
        if storage.ready_for_morning_brief():
            navigate("home")
            return
        if not was_existing:
            offer_diary(mood)

    def offer_diary(mood: str):
        today_entry = storage.today_mood()
        has_story = any(
            entry.get("date") == clock.today().isoformat()
            and (entry.get("diary") or "").strip()
            for entry in storage.diary_entries()
        )
        if has_story or (today_entry and (today_entry.get("diary") or "").strip()):
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
    render_energy()
    render_care()
    render_checkin()
    render_condition()

    rec_state = {"cards": None, "index": 0}
    rec_holder = ft.Container()

    def render_rec():
        if rec_state["cards"] is None:
            rec_holder.content = ui_helpers.card(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.AUTO_AWESOME, color=theme.TERTIARY, size=20),
                        ft.Text(
                            "KALEM punya rekomendasi personal buat kamu",
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
                ui_helpers.wide_button("Isi Favorit", open_favorites, icon=ft.Icons.FAVORITE_BORDER)
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
        energy_level = storage.today_energy() or (latest.get("energy", 3) if latest else 3)

        async def kerjakan():
            cards = await ui_helpers.jalankan_dengan_progres(
                page, rec_holder,
                lambda: recommendations.build_cards(favorites, energy_level),
                "KALEM lagi mikir rekomendasi buat kamu...",
            )
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

    insight_holder = ft.Container()

    def render_insight():
        insight = analyse(
            storage.get_mood_logs(),
            focus_records=storage.get_focus_records(),
            diary_entries=storage.diary_entries(),
        )
        children: list[ft.Control] = [
            ui_helpers.premium_header(
                "Yang KALEM pelajari tentang kamu", not storage.is_premium()
            ),
            ft.Text(insight.headline, size=13, weight=ft.FontWeight.BOLD,
                    color=theme.ON_BACKGROUND),
        ]

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

    _y, _m = mood_chart.today_year_month()
    history_state = {"year": _y, "month": _m}
    history_holder = ft.Container()

    def render_history():
        logs = storage.get_mood_logs()
        children: list[ft.Control] = [
            ui_helpers.section_header("Grafik bulanan"),
            mood_chart.month_nav(
                history_state["year"], history_state["month"], shift_month(-1), shift_month(1)
            ),
            mood_chart.build_month_chart(
                logs, history_state["year"], history_state["month"], SCORE_COLORS
            ),
            mood_chart.build_month_summary(
                logs, history_state["year"], history_state["month"]
            ),
        ]
        if not storage.is_premium():
            children.append(
                ui_helpers.upgrade_hint(
                    "Bulan ini kebuka gratis. Premium bisa telusuri "
                    "bulan-bulan sebelumnya buat lihat tren panjang."
                )
            )
        history_holder.content = ft.Column(children, spacing=8)

    def shift_month(delta: int):
        def handler(e):
            y, m = mood_chart.shift_month(
                history_state["year"], history_state["month"], delta
            )
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

    terisi = storage.favorites_filled()
    total_favorit = len(storage.FAVORITE_FIELDS)
    header_row = ft.Row(
        [
            ft.Container(content=ui_helpers.title("Mood", 22), expand=True),
            ft.IconButton(
                icon=ft.Icons.FAVORITE_BORDER,
                icon_color=theme.TERTIARY,
                icon_size=20,
                tooltip=f"Favorit kamu — {terisi}/{total_favorit} terisi · "
                        "bikin saran KALEM lebih personal",
                on_click=open_favorites,
            ),
        ],
        spacing=0,
    )

    return ft.Column(
        [
            header_row,
            checkin_holder,
            result_holder,
            ui_helpers.nav_link_card(
                ft.Icons.MENU_BOOK,
                theme.PRIMARY,
                "Cerita Kamu",
                "Tulis cerita hari ini, atau baca lagi yang udah pernah kamu tulis.",
                lambda e: navigate("diary"),
            ),
            ui_helpers.card(insight_holder),
            ui_helpers.card(history_holder),
            rec_holder,
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
    return {1: 1, 2: 2, 3: 3, 4: 5, 5: 6}.get(score, 3)
