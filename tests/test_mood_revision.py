"""Behavior contract untuk lifecycle, insight, dan personalisasi Mood."""
from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import flet as ft

from app import clock, storage
from app.core import kalem_engine, recommendations
from app.core.mood_model import analyse
from app.views import diary, favorites, mood, mood_chart


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  [OK] " if condition else "  [FAIL] ") + message)
    if not condition:
        FAILURES.append(message)


class FakePage:
    def __init__(self) -> None:
        self.dialogs: list = []
        self.overlay: list = []

    def update(self) -> None:
        pass

    def show_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def run_task(self, fn, *args) -> None:
        pass


def walk(control):
    if control is None:
        return
    yield control
    for child in getattr(control, "controls", []) or []:
        yield from walk(child)
    for action in getattr(control, "actions", []) or []:
        yield from walk(action)
    yield from walk(getattr(control, "title", None))
    yield from walk(getattr(control, "subtitle", None))
    yield from walk(getattr(control, "content", None))


def texts(root) -> list[str]:
    return [
        control.value
        for control in walk(root)
        if isinstance(getattr(control, "value", None), str)
    ]


def clickable(root, label: str):
    return next(
        (
            control
            for control in walk(root)
            if getattr(control, "on_click", None) is not None
            and getattr(getattr(control, "content", None), "value", None) == label
        ),
        None,
    )


def text_field(root, label: str):
    return next(
        (
            control
            for control in walk(root)
            if isinstance(control, ft.TextField) and control.label == label
        ),
        None,
    )


def energy_slider(root):
    return next(
        (
            control
            for control in walk(root)
            if isinstance(control, ft.Slider)
            and control.min == 1
            and control.max == 6
        ),
        None,
    )


def set_slider(slider, value: int) -> None:
    slider.value = value
    slider.on_change(SimpleNamespace(control=slider))


def prepare() -> None:
    state = storage.reset_all_data()
    state["profile"].update(
        {
            "name": "Ari",
            "onboarded": True,
            "sleep_condition": "cukup",
            "productive_hours": [[8, 12]],
        }
    )
    state["last_brief_date"] = clock.today().isoformat()
    storage.save_state(state)


def scenario_checkin_upsert_and_recompute() -> None:
    print("\n=== Check-in satu kali, bisa diedit, dan mengubah kapasitas ===")
    yesterday = (clock.today() - timedelta(days=1)).isoformat()
    state = storage.load_state()
    state["mood_logs"] = [
        {
            "date": yesterday,
            "mood": "sedih",
            "score": 2,
            "energy": 2,
            "diary": "catatan lama",
            "tags": ["lama"],
            "quick_tags": [],
            "ate_today": True,
            "rested_enough": False,
            "weekday": (clock.today() - timedelta(days=1)).weekday(),
            "is_weekend": (clock.today() - timedelta(days=1)).weekday() >= 5,
        }
    ]
    storage.save_state(state)

    page = FakePage()
    routes: list[str] = []
    root = mood.build(page, routes.append)
    check("Simpan check-in" in texts(root), "form awal memakai tombol Simpan check-in")
    check("Sudah check-in" not in texts(root), "status selesai belum muncul sebelum simpan")
    initial_text = texts(root)
    order_labels = [
        "Yang KALEM paling pelajarin tentang kamu",
        "Grafik Bulanan",
        "Cerita Kamu",
    ]
    check(
        all(label in initial_text for label in order_labels)
        and [initial_text.index(label) for label in order_labels]
        == sorted(initial_text.index(label) for label in order_labels),
        "Mood mengurutkan insight + rekomendasi, grafik, lalu Cerita",
    )
    favorite_shortcut = next(
        (
            control for control in walk(root)
            if isinstance(control, ft.IconButton)
            and control.icon == ft.Icons.FAVORITE_BORDER
            and control.tooltip == "Favorit Kamu"
        ),
        None,
    )
    check(
        favorite_shortcut is not None
        and "Tambah favoritmu di sini" not in initial_text,
        "Favorit dipindahkan menjadi ikon hati di kanan atas Mood",
    )
    check("Istirahat cukup semalam?" in initial_text,
          "form Check-in menampilkan pertanyaan istirahat di layar yang sama")
    check(not any("paling ngaruh hari ini" in value.lower() for value in texts(root)),
          "pertanyaan faktor yang paling berpengaruh tidak tampil di Check-in")

    energy_one = energy_slider(root)
    save = clickable(root, "Simpan check-in")
    check(energy_one is not None and save is not None,
          "slider energi 1–6 dan tombol simpan tersedia di form yang sama")
    if energy_one is not None:
        set_slider(energy_one, 1)
    if save is not None:
        save.on_click(None)

    first = storage.today_mood() or {}
    check(first.get("energy") == 1, "energi check-in tersimpan")
    check(first.get("quick_tags") == [],
          "field quick tag lama tetap kompatibel tanpa input di Check-in")
    check(sum(log.get("date") == clock.today().isoformat()
              for log in storage.get_mood_logs()) == 1,
          "hanya ada satu record mood untuk hari ini")
    check("Sudah check-in" in texts(root) and "Ubah check-in" in texts(root),
          "sesudah simpan UI berubah menjadi status check-in dan akses edit")
    check("Kamu kelihatan capek. Istirahat juga termasuk progress loh..." in texts(root),
          "energi 1–3 memakai maskot dan pesan lelah yang sama dengan Home/Tracker")
    check(not routes and not page.dialogs,
          "selesai Check-in tetap di ringkasan Mood tanpa pindah halaman atau popup")
    check(any("Beban kerja yang disaranin" in value for value in texts(root)),
          "hasil kapasitas kerja langsung dihitung dari check-in")

    edit = clickable(root, "Ubah check-in")
    if edit is not None:
        edit.on_click(None)
    details = root.controls[2] if len(root.controls) > 2 else None
    check(details is not None and not details.visible,
          "edit Check-in menyembunyikan konten panjang agar scroll tetap ringan")
    energy_five = energy_slider(root)
    update = clickable(root, "Simpan perubahan")
    check(energy_five is not None and update is not None,
          "mode edit memuat ulang input Check-in hari ini")
    if energy_five is not None:
        set_slider(energy_five, 5)
    if update is not None:
        update.on_click(None)
    check(details is not None and details.visible,
          "selesai edit menampilkan kembali insight dan grafik")

    updated = storage.today_mood() or {}
    old = next((log for log in storage.get_mood_logs() if log.get("date") == yesterday), {})
    check(updated.get("energy") == 5 and storage.today_energy() == 5,
          "edit menyinkronkan mood log dan energi aktif KALEM")
    check("Semangat untuk Hari Ini!" in texts(root),
          "energi 4–6 memakai maskot dan pesan semangat yang sama dengan Home/Tracker")
    check(updated.get("quick_tags") == [],
          "edit tidak membuat quick tag baru dari Check-in")
    check(sum(log.get("date") == clock.today().isoformat()
              for log in storage.get_mood_logs()) == 1,
          "edit melakukan upsert, bukan menambah record kedua")
    check(old.get("diary") == "catatan lama" and old.get("energy") == 2,
          "histori hari sebelumnya tidak ikut berubah")

    task = storage.add_task(
        "Tugas kapasitas",
        clock.today().isoformat(),
        menit_est=60,
        steps=[{"text": "Mulai", "done": False}],
    )
    _, day = kalem_engine.snapshot()
    high_minutes, _ = kalem_engine.task_focus_minutes(
        task, 0, day.energy_level or 3, storage.get_focus_records()
    )
    low_minutes, _ = kalem_engine.task_focus_minutes(
        task, 0, 1, storage.get_focus_records()
    )
    check(day.energy_level == 5 and high_minutes > low_minutes,
          "snapshot Home dan durasi Focus membaca energi hasil edit")


def scenario_diary_does_not_fake_checkin() -> None:
    print("\n=== Diary tidak membuat check-in palsu ===")
    page = FakePage()
    root = diary.build(page, lambda route: None)
    field = next(
        (control for control in walk(root)
         if isinstance(control, ft.TextField) and control.multiline),
        None,
    )
    save = clickable(root, "Kirim ke KALEM")
    check(field is not None and save is not None, "form Diary bisa diisi dan disimpan")
    shown = texts(root)
    check("Cerita yuk" in shown and "Cerita Sebelumnya" in shown,
          "halaman Cerita memakai susunan judul dan riwayat yang baru")
    check(field is not None and field.suffix is not None,
          "rekam suara tetap tersedia langsung di kolom Cerita")
    check(
        root.horizontal_alignment == ft.CrossAxisAlignment.STRETCH
        and field.bgcolor == "#484863",
        "textbox Cerita memakai tema gelap dan memenuhi lebar container",
    )
    if field is not None:
        field.value = "Hari ini capek karena deadline dan butuh istirahat."
    if save is not None:
        save.on_click(None)
    check(storage.today_mood() is None,
          "menulis Diary tanpa check-in tidak menciptakan mood default")
    entries = storage.diary_entries()
    check(len(entries) == 1 and "deadline" in entries[0].get("tags", []),
          "Diary tetap tersimpan dan menghasilkan tag untuk insight")


def scenario_monthly_summary_uses_thresholds() -> None:
    print("\n=== Ringkasan bulanan memakai data nyata dan threshold ===")
    sparse = [
        {"date": "2026-08-01", "score": 2, "energy": 1, "is_weekend": True},
        {"date": "2026-08-03", "score": 4, "energy": 5, "is_weekend": False},
    ]
    sparse_summary = mood_chart.analyse_month(sparse, 2026, 8)
    check(sparse_summary.checkin_days == 2 and sparse_summary.average == 3,
          "rata-rata dan jumlah hari dihitung dari log periode aktif")
    check(not sparse_summary.comparison,
          "dua check-in belum dipakai untuk klaim perbandingan periode")

    enough = sparse + [
        {"date": "2026-08-04", "score": 5, "energy": 5, "is_weekend": False},
        {"date": "2026-08-08", "score": 2, "energy": 1, "is_weekend": True},
        {"date": "2026-07-02", "score": 2, "energy": 2, "is_weekend": False},
        {"date": "2026-07-03", "score": 3, "energy": 3, "is_weekend": False},
        {"date": "2026-07-04", "score": 1, "energy": 2, "is_weekend": True},
    ]
    summary = mood_chart.analyse_month(enough, 2026, 8)
    check(summary.checkin_days == 4 and summary.previous_days == 3,
          "periode aktif dan sebelumnya dihitung terpisah")
    check("lebih tinggi" in summary.comparison,
          "perbandingan baru muncul setelah dua periode melewati threshold")
    check(any("tertinggi" in item and "terendah" in item for item in summary.insights),
          "hari mood tertinggi dan terendah ditampilkan dari data nyata")
    check(any("weekend" in item or "hari kerja" in item for item in summary.insights),
          "pola weekday/weekend menunggu minimal dua data per kelompok")
    check(any("energi" in item for item in summary.insights),
          "hubungan energi dan mood muncul saat dua kelompok cukup data")


def scenario_personal_insight_thresholds_and_sources() -> None:
    print("\n=== Insight personal menggabungkan sumber tanpa klaim tipis ===")
    four_logs = [
        {"date": f"2026-08-0{index + 1}", "score": 3, "energy": 3,
         "weekday": index, "is_weekend": False, "quick_tags": []}
        for index in range(4)
    ]
    waiting = analyse(four_logs)
    check(not waiting.ready and "4/5" in waiting.headline,
          "insight pola belum aktif sebelum lima check-in")

    five_thin_days = four_logs + [
        {"date": "2026-08-05", "score": 5, "energy": 5,
         "weekday": 4, "is_weekend": False, "quick_tags": []}
    ]
    thin = analyse(five_thin_days)
    check(thin.ready and thin.best_day is None and thin.hardest_day is None,
          "satu sampel per weekday tidak dijadikan pola hari terbaik/terberat")

    rich_logs = []
    for index in range(10):
        low = index < 5
        rich_logs.append(
            {
                "date": (date(2026, 7, 1) + timedelta(days=index)).isoformat(),
                "score": 2 if low else 5,
                "energy": 2 if low else 5,
                "weekday": index % 2,
                "is_weekend": False,
                "quick_tags": ["kuliah"] if low else ["istirahat"],
                "tags": ["deadline"] if low else [],
            }
        )
    diary_entries = [
        {"date": "2026-07-01", "tags": ["deadline"]},
        {"date": "2026-07-02", "tags": ["deadline"]},
    ]
    focus_records = [
        *[{"energi": 2, "actual_focus_minutes": 8} for _ in range(3)],
        *[{"energi": 5, "actual_focus_minutes": 22} for _ in range(3)],
    ]
    rich = analyse(rich_logs, focus_records, diary_entries)
    all_details = " ".join(rich.details)
    check("energi berada di level 1–2" in all_details,
          "riwayat mood dan energi menghasilkan insight setelah sampel cukup")
    check("sesi fokusmu cenderung lebih pendek" in all_details,
          "durasi Focus ikut menjadi sumber insight personal")
    check("deadline" in all_details and "Kuliah" in all_details,
          "quick tags dan tag Diary ikut menjadi sumber pola")


def scenario_favorites_preserve_and_personalize() -> None:
    print("\n=== Favorit bertahap menjaga data lama dan dipakai rekomendasi ===")
    storage.set_favorite("musik", "lo-fi lama")
    storage.set_favorite("orang", "Rani")
    page = FakePage()
    popup_messages: list[str] = []
    original_reward = favorites.ui_helpers.reward_overlay
    favorites.ui_helpers.reward_overlay = (
        lambda _page, message="": popup_messages.append(message)
    )
    root = favorites.build(page, lambda route: None)
    shown = texts(root)
    for group in (
        "A. Hal yang membantu fokus",
        "B. Saat sedang overwhelmed",
        "C. Preferensi mengerjakan tugas",
        "D. Personal support",
    ):
        check(group in shown, f"Favorit menampilkan kelompok '{group}'")

    alone = clickable(root, "Sendiri")
    safe = text_field(root, storage.FAVORITE_FIELDS["rasa_aman"])
    save = clickable(root, "Simpan")
    check(alone is not None and safe is not None and save is not None,
          "preferensi multi-select dan dukungan bebas bisa diisi")
    if alone is not None:
        alone.on_click(None)
    if safe is not None:
        safe.value = "duduk sebentar di kamar"
    if save is not None:
        save.on_click(None)
    favorites.ui_helpers.reward_overlay = original_reward
    check(popup_messages == ["Favorit kamu tersimpan 🤍"],
          "Simpan Favorit menampilkan popup hijau, bukan teks status permanen")
    favorite_fields = [
        control for control in walk(root) if isinstance(control, ft.TextField)
    ]
    check(favorite_fields and all(field.color == "#FFFFFF" for field in favorite_fields),
          "seluruh input Favorit menggunakan tulisan putih")
    check(
        favorite_fields
        and all(field.label_style.color == "#A5A3B2" for field in favorite_fields)
        and all(field.hint_style.color == "#8F8D9E" for field in favorite_fields),
        "label dan placeholder Favorit redup saat field masih kosong",
    )

    stored = storage.get_favorites()
    check(stored.get("musik") == "lo-fi lama" and stored.get("orang") == "Rani",
          "data Favorit versi lama tidak hilang saat struktur diperluas")
    check(stored.get("preferensi_kerja") == "sendiri"
          and stored.get("rasa_aman") == "duduk sebentar di kamar",
          "field baru tersimpan lewat schema string yang kompatibel")
    reloaded = storage.load_state()["favorites"]
    check(reloaded.get("musik") == "lo-fi lama"
          and reloaded.get("rasa_aman") == "duduk sebentar di kamar",
          "data lama dan baru tetap ada setelah state dimuat ulang")

    local_cards = recommendations.build_cards(
        {**storage.get_favorites(), "musik": "", "hobi": ""}, energy_level=2
    )
    check(any(card.kind == "support" and card.source == "local" for card in local_cards),
          "dukungan personal dipakai rekomendasi KALEM tanpa wajib memanggil API")
    focus_cards = recommendations.build_cards(
        {**storage.get_favorites(), "musik": "", "hobi": ""}, energy_level=5
    )
    check(any("kerja sendiri" in card.body for card in focus_cards),
          "pilihan cara kerja multi-select ikut dipakai rekomendasi fokus")


def main() -> int:
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    with tempfile.TemporaryDirectory(prefix="focusbuddy_mood_revision_") as directory:
        storage.DATA_DIR = Path(directory)
        storage.DATA_FILE = storage.DATA_DIR / "data.json"
        storage.BACKUP_FILE = storage.DATA_DIR / "data.json.bak"
        try:
            for scenario in (
                scenario_checkin_upsert_and_recompute,
                scenario_diary_does_not_fake_checkin,
                scenario_monthly_summary_uses_thresholds,
                scenario_personal_insight_thresholds_and_sources,
                scenario_favorites_preserve_and_personalize,
            ):
                prepare()
                scenario()
        finally:
            storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original
            clock.reset_offset()

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"GAGAL: {len(FAILURES)} behavior Mood belum terpenuhi")
        return 1
    print("SEMUA BEHAVIOR MOOD LULUS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
