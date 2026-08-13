"""Regresi aplikasi yang dapat dijalankan tanpa pytest."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.storage as storage  # noqa: E402

_GAGAL: list[str] = []


def ok(kondisi: bool, pesan: str) -> None:
    print(("  [OK] " if kondisi else "  [GAGAL] ") + pesan)
    if not kondisi:
        _GAGAL.append(pesan)


def bagian(judul: str) -> None:
    print(f"\n=== {judul} ===")


def storage_baru(prefix: str = "fb_") -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix))
    storage.DATA_DIR = d / ".focusbuddy"
    storage.DATA_FILE = storage.DATA_DIR / "data.json"
    storage.reset_all_data()
    return storage.DATA_FILE


def pasang_logs(skor: int, n: int, energi: int = 3, sos_idx=(), mulai_dari: int = 0):
    from app import clock

    st = storage.load_state()
    logs = []
    for i in range(n):
        d = clock.today() - timedelta(days=i + mulai_dari)
        logs.append({
            "date": d.isoformat(), "mood": "tenang", "score": skor, "energy": energi,
            "diary": "", "tags": [], "quick_tags": [],
            "ate_today": True, "rested_enough": True,
            "weekday": d.weekday(), "is_weekend": d.weekday() >= 5,
        })
    st["mood_logs"] = logs
    st["reset_events"] = [
        {"timestamp": "", "date": (clock.today() - timedelta(days=i)).isoformat(),
         "choice": "napas", "mood_score": None}
        for i in sos_idx
    ]
    storage.save_state(st)


class HalamanPalsu:

    def update(self): pass
    def show_dialog(self, d): pass
    def pop_dialog(self): pass
    def run_task(self, fn): pass
    @property
    def overlay(self): return []


def cari_tombol_berteks(kontrol, awalan_label: str):
    if kontrol is None:
        return None
    on_click = getattr(kontrol, "on_click", None)
    if on_click is not None:
        isi = getattr(kontrol, "content", None)
        teks = getattr(isi, "value", None) if isi is not None else None
        if isinstance(teks, str) and teks.startswith(awalan_label):
            return kontrol
    for anak in (getattr(kontrol, "controls", None) or []):
        hasil = cari_tombol_berteks(anak, awalan_label)
        if hasil is not None:
            return hasil
    for aksi in (getattr(kontrol, "actions", None) or []):
        hasil = cari_tombol_berteks(aksi, awalan_label)
        if hasil is not None:
            return hasil
    isi = getattr(kontrol, "content", None)
    if isi is not None:
        hasil = cari_tombol_berteks(isi, awalan_label)
        if hasil is not None:
            return hasil
    return None


def jalan_tree(kontrol):
    if kontrol is None:
        return
    yield kontrol
    for anak in (getattr(kontrol, "controls", None) or []):
        yield from jalan_tree(anak)
    for aksi in (getattr(kontrol, "actions", None) or []):
        yield from jalan_tree(aksi)
    yield from jalan_tree(getattr(kontrol, "title", None))
    yield from jalan_tree(getattr(kontrol, "subtitle", None))
    yield from jalan_tree(getattr(kontrol, "suffix", None))
    yield from jalan_tree(getattr(kontrol, "content", None))


def cari_kontrol(kontrol, kondisi):
    return next((item for item in jalan_tree(kontrol) if kondisi(item)), None)


def punya_teks(kontrol, teks: str) -> bool:
    return any(getattr(item, "value", None) == teks for item in jalan_tree(kontrol))


def tes_mendesak_dari_deadline():
    bagian("Mendesak DIHITUNG dari deadline, bukan centang user")
    from app import clock
    storage_baru("urgent_")

    hari_ini = clock.today().isoformat()
    lusa = (clock.today() + timedelta(days=5)).isoformat()

    t_dekat = storage.add_task("Deadline hari ini", hari_ini, important=True)
    t_jauh = storage.add_task("Deadline 5 hari lagi", lusa, important=True)

    ok(storage.is_urgent(t_dekat), "deadline hari ini -> mendesak")
    ok(not storage.is_urgent(t_jauh), "deadline 5 hari lagi -> nggak mendesak")
    ok(storage.quadrant_of(t_dekat) == "lakukan", "kuadran: penting+mendesak = lakukan")
    ok(storage.quadrant_of(t_jauh) == "jadwalkan", "kuadran: penting doang = jadwalkan")

    pagi = storage.add_task("Deadline jam 6 pagi", hari_ini, important=True,
                            deadline_time="06:00")
    sore = datetime.combine(clock.today(), datetime.min.time()).replace(hour=17)
    ok(storage.is_urgent(pagi, sore), "jam 17:00, deadline 06:00 hari ini -> udah lewat, mendesak")

    besok = (clock.today() + timedelta(days=1)).isoformat()
    t_besok_malam = storage.add_task("Besok malam", besok, important=True, deadline_time="23:00")
    pagi_ini = datetime.combine(clock.today(), datetime.min.time()).replace(hour=8)
    ok(not storage.is_urgent(t_besok_malam, pagi_ini),
       "jam 08:00, deadline besok 23:00 (39 jam lagi) -> belum mendesak")

    ok(storage.is_urgent({"deadline": hari_ini}) is True, "tanpa deadline_time -> tetap jalan")
    ok(storage.is_urgent({}) is False, "tanpa deadline sama sekali -> False, bukan crash")


def tes_data_basi():
    bagian("Data mood basi TIDAK dipakai buat nebak hari ini")
    from app.core import kalem_engine as ke
    import models as ml
    from models import fitur as F

    storage_baru("basi_")
    pasang_logs(skor=1, n=6, energi=1, mulai_dari=10)
    ml.reset_semua()

    jarak = storage.hari_sejak_checkin()
    ok(jarak == 10, f"hari sejak check-in terakhir = {jarak}")
    ok(storage.data_mood_basi(), "ditandai basi (> 3 hari)")

    f = F.bangun_fitur()
    ok(f["energi_terakhir"] == 3.0,
       f"energi_terakhir balik ke netral 3, bukan 1 dari 10 hari lalu (dapet {f['energi_terakhir']})")
    ok(f["streak_abai"] == 0.0, "streak abai di-nol-in, bukan diwarisin dari catatan lama")
    ok(f["hari_sejak_checkin"] == 10.0, "fitur hari_sejak_checkin kebaca model")

    p, day = ke.snapshot()
    brief = ke.build_morning_brief(p, day)
    ok(not brief.ready, "brief nggak meramal pas datanya basi")
    ok("balik lagi" in brief.forecast.lower(),
       f"brief-nya nyapa, bukan nakut-nakutin: {brief.forecast!r}")
    ok(brief.energy_level == 3, "energi default netral, bukan 1 dari catatan lama")

    storage_baru("segar_")
    pasang_logs(skor=1, n=6, energi=1)
    ml.reset_semua()
    ok(not storage.data_mood_basi(), "check-in hari ini -> nggak basi")
    f2 = F.bangun_fitur()
    ok(f2["energi_terakhir"] == 1.0,
       f"data segar TETAP dipakai (energi {f2['energi_terakhir']}) -- fix-nya nggak kebablasan")


def tes_hari_kosong_bukan_hari_buruk():
    bagian("Hari tanpa check-in = KOSONG, bukan hari buruk")
    from app import clock
    import models as ml
    from models import fitur as F, riwayat

    storage_baru("kosong_")
    st = storage.load_state()
    logs = []
    for i in (0, 5, 10):
        d = clock.today() - timedelta(days=i)
        logs.append({
            "date": d.isoformat(), "mood": "tenang", "score": 4, "energy": 4,
            "diary": "", "tags": [], "quick_tags": [],
            "ate_today": True, "rested_enough": True,
            "weekday": d.weekday(), "is_weekend": d.weekday() >= 5,
        })
    st["mood_logs"] = logs
    storage.save_state(st)
    ml.reset_semua()

    X, meta = riwayat.baris_harian()
    ok(len(X) == 3, f"cuma 3 baris latih dari 3 check-in (dapet {len(X)}) -- hari bolong nggak diisi tebakan")
    ok(len({m["tanggal"] for m in meta}) == 3, "nggak ada hari duplikat/dikarang")

    f = F.bangun_fitur()
    ok(f["n_catatan"] == 3.0, "jumlah catatan apa adanya, nggak dipoles")


def tes_urutan_mood():
    bagian("Urutan mood naik (paling berat -> paling enak)")
    from app import buddy

    skor = [buddy.MOOD_SCORE[m] for m in buddy.MOOD_ORDER]
    ok(buddy.MOOD_ORDER[0] == "cemas", f"paling kiri = cemas (dapet {buddy.MOOD_ORDER[0]})")
    ok(buddy.MOOD_ORDER[-1] == "semangat", f"paling kanan = semangat (dapet {buddy.MOOD_ORDER[-1]})")
    ok(skor == sorted(skor), f"skornya naik monoton: {skor}")
    ok(len(set(skor)) == len(skor), f"nggak ada skor kembar (dapet {skor})")
    ok(len(buddy.MOOD_ORDER) == len(buddy.MOOD_ASSETS), "semua mood punya aset")
    for m in buddy.MOOD_ORDER:
        ok(m in buddy.MOOD_LABELS and m in buddy.MOOD_SCORE, f"{m}: label & skor lengkap")


def tes_isolasi_model_antar_user():
    bagian("Cache model nggak bocor antar-user")
    from app import clock
    from models import fitur as F, model_mood

    def tulis(prefix: str, skor: int) -> Path:
        d = Path(tempfile.mkdtemp(prefix=prefix)) / ".focusbuddy"
        d.mkdir(parents=True, exist_ok=True)
        logs = []
        for i in range(14):
            dd = clock.today() - timedelta(days=i)
            logs.append({
                "date": dd.isoformat(), "mood": "x", "score": skor, "energy": skor,
                "diary": "", "tags": [], "quick_tags": [],
                "ate_today": True, "rested_enough": True,
                "weekday": dd.weekday(), "is_weekend": dd.weekday() >= 5,
            })
        st = storage._default_state()
        st["profile"]["onboarded"] = True
        st["profile"]["name"] = "X"
        st["mood_logs"] = logs
        (d / "data.json").write_text(json.dumps(st))
        return d / "data.json"

    a, b = tulis("userA_", 5), tulis("userB_", 1)

    storage.DATA_FILE = a
    ra = model_mood.ramal(F.bangun_fitur())
    tanda_a, id_a = model_mood._tanda, id(model_mood._model)

    storage.DATA_FILE = b
    rb = model_mood.ramal(F.bangun_fitur())
    tanda_b, id_b = model_mood._tanda, id(model_mood._model)

    ok(tanda_a != tanda_b, "sidik jari data beda -> kunci cache beda")
    ok(id_a != id_b, "model di-retrain buat user B")
    ok(rb.skor < 2.0, f"user B (mood 1) dapet skor dari datanya sendiri: {rb.skor:.2f}")
    ok(ra.skor > 4.0, f"user A (mood 5) tetap benar: {ra.skor:.2f}")


def tes_fungsi_murni():
    bagian("decide()/build_morning_brief() murni dari argumen")
    from app import clock
    import models as ml
    from app.core import kalem_engine as ke

    storage_baru("murni_")
    pasang_logs(skor=1, n=12, energi=1, sos_idx=[0, 1, 2])
    ml.reset_semua()
    profile = storage.get_profile()

    hasil = ke.decide(profile, ke.DayState())
    ok(hasil.kind != "pre_escalate",
       f"day kosong -> kind={hasil.kind}, nggak keseret storage yang berat")

    logs_berat = [
        {"date": (clock.today() - timedelta(days=i)).isoformat(), "mood": "x", "score": 1,
         "energy": 1, "diary": "", "tags": [], "quick_tags": [],
         "ate_today": False, "rested_enough": False, "weekday": 0, "is_weekend": False}
        for i in range(12)
    ]
    storage_baru("murni2_")
    pasang_logs(skor=5, n=12, energi=5)
    ml.reset_semua()
    profile = storage.get_profile()
    day_berat = ke.DayState(
        mood_logs=logs_berat,
        reset_events=[
            {"timestamp": "", "date": (clock.today() - timedelta(days=i)).isoformat(),
             "choice": "napas", "mood_score": None} for i in (0, 1, 2)
        ],
    )
    keputusan_berat = ke.decide(profile, day_berat)
    ok(keputusan_berat.kind == "recovery" and keputusan_berat.action_kind == "rest",
       "day berat -> recovery tanpa Reset otomatis, walau storage-nya tenang")


def tes_halaman_kebangun():
    bagian("Semua halaman kebangun")
    import models as ml
    from app.views import (demo_tools, diary, favorites, home, inbox, med_setup, mood,
                           morning_brief, onboarding, reset, settings,
                           subscription, tracker)

    storage_baru("ui_")
    pasang_logs(skor=4, n=30, energi=4)
    storage.add_task("Tugas contoh", storage.clock.today().isoformat(), important=True,
                     steps=[{"text": "langkah", "done": False}])
    ml.reset_semua()

    p = HalamanPalsu()
    for nama, modul in [
        ("home", home), ("demo_tools", demo_tools),
        ("tracker", tracker),
        ("mood", mood), ("diary", diary),
        ("reset", reset), ("med_setup", med_setup), ("favorites", favorites),
        ("settings", settings), ("profile_settings", settings),
        ("morning_brief", morning_brief),
        ("subscription", subscription), ("inbox", inbox),
        ("onboarding", onboarding),
    ]:
        try:
            builder = settings.build_profile if nama == "profile_settings" else modul.build
            builder(p, lambda r: None)
            ok(True, nama)
        except Exception as exc:                       # noqa: BLE001
            ok(False, f"{nama}: {type(exc).__name__}: {exc}")


def tes_langganan_demo():
    bagian("Halaman langganan & aktivasi demo")
    import json
    import flet as ft
    import app.main as main_mod
    from app import theme
    from app.views import subscription

    class HalamanPembayaran(HalamanPalsu):
        def __init__(self):
            self.dialogs = []

        def show_dialog(self, dialog):
            self.dialogs.append(dialog)

        def pop_dialog(self):
            if self.dialogs:
                self.dialogs.pop()

    storage_baru("subs_demo_")
    tujuan: list[str] = []
    page = HalamanPembayaran()
    root = subscription.build(page, tujuan.append)

    ok("subscription" in main_mod.ROUTES, "halaman langganan terdaftar di router")
    ok(
        punya_teks(root, "KALEM Freemium")
        and punya_teks(root, "Kamu sedang memakai paket Free")
        and punya_teks(root, "IDR 29.000/Bulan")
        and cari_kontrol(
            root,
            lambda control: getattr(control, "on_click", None) is not None
            and punya_teks(control, "Upgrade ke Freemium"),
        ) is not None,
        "card pertama menampilkan status Free, harga, dan upgrade Freemium",
    )
    tombol_on = cari_tombol_berteks(root, "Coba pembayaran demo")
    ok(tombol_on is not None, "paket Free membuka checkout pembayaran demo")
    if tombol_on is None:
        return

    tombol_on.on_click(None)
    checkout = page.dialogs[-1] if page.dialogs else None
    ok(checkout is not None and punya_teks(checkout, "Checkout Freemium — DEMO"),
       "checkout demo tampil sebelum Freemium diaktifkan")
    ok(not storage.is_premium(), "membuka checkout belum mengaktifkan Premium")

    fields = [control for control in jalan_tree(checkout) if isinstance(control, ft.TextField)]
    card = next((field for field in fields if field.label == "Nomor kartu demo"), None)
    gopay = next((field for field in fields if field.label == "Nomor GoPay demo"), None)
    expiry = next((field for field in fields if field.label == "Bulan/Tahun"), None)
    cvc = next((field for field in fields if field.label == "CVC"), None)
    consent = next(
        (control for control in jalan_tree(checkout)
         if isinstance(control, ft.Checkbox) and "simulasi" in (control.label or "")),
        None,
    )
    payment_method = next(
        (control for control in jalan_tree(checkout)
         if isinstance(control, ft.RadioGroup) and control.value == "card"),
        None,
    )
    lanjut = cari_tombol_berteks(checkout, "Lanjut konfirmasi")
    ok(card is not None and gopay is not None and expiry is not None and cvc is not None
       and consent is not None
       and payment_method is not None and lanjut is not None,
       "checkout menyediakan kartu lengkap, GoPay, dan persetujuan simulasi")
    if (card is None or gopay is None or expiry is None or cvc is None
            or consent is None or payment_method is None or lanjut is None):
        return
    ok(
        card.value == "0000 0000 0000 0000"
        and gopay.value == "081234567890"
        and checkout.bgcolor == theme.SURFACE,
        "checkout gelap memakai nomor pembayaran demo yang baru",
    )
    payment_method.value = "gopay"
    payment_method.on_change(None)
    ok(gopay.visible and not card.visible,
       "memilih GoPay mengganti input tanpa mengaktifkan Premium")
    payment_method.value = "card"
    payment_method.on_change(None)
    card.value = "0000 0000 0000 0000"
    expiry.value = "12/30"
    cvc.value = "000"
    consent.value = True
    lanjut.on_click(None)
    confirmation = page.dialogs[-1] if page.dialogs else None
    ok(confirmation is not None and punya_teks(confirmation, "Konfirmasi pembayaran demo"),
       "data dummy harus melewati layar konfirmasi kedua")
    ok(not storage.is_premium(), "Premium belum aktif sebelum konfirmasi akhir")

    confirm = cari_tombol_berteks(confirmation, "Konfirmasi demo")
    if confirm is not None:
        confirm.on_click(None)
    ok(confirm is not None and storage.is_premium(),
       "konfirmasi akhir baru mengaktifkan Premium pada akun aktif")
    ok(tujuan == ["subscription"], "halaman dirender ulang setelah status berubah")
    serialized = json.dumps(storage.load_state())
    ok("0000000000000000" not in serialized and "081234567890" not in serialized,
       "nomor pembayaran demo tidak pernah disimpan ke state/Supabase")

    root = subscription.build(HalamanPalsu(), tujuan.append)
    ok(
        cari_tombol_berteks(root, "Subs Off - Untuk DEMO") is not None,
        "Premium aktif menampilkan tombol untuk mematikan simulasi",
    )


def tes_alat_demo_terpusat():
    bagian("Kontrol presentasi terpusat di Alat Demo")
    import flet as ft
    import app.main as main_mod
    from app.views import demo_tools, home

    storage_baru("demo_tools_")
    storage.save_profile({"name": "Ari"})
    tujuan: list[str] = []
    root = demo_tools.build(HalamanPalsu(), tujuan.append)

    ok("demo_tools" in main_mod.ROUTES, "Alat Demo terdaftar saat DEMO_MODE aktif")
    maju = cari_kontrol(
        root,
        lambda control: getattr(control, "on_click", None) is not None
        and punya_teks(control, "Maju 1 hari"),
    )
    ok(maju is not None, "kontrol maju hari tersedia di halaman terpusat")
    if maju is not None:
        maju.on_click(None)
    ok(storage.day_offset() == 1, "maju hari tetap bekerja dari Alat Demo")

    root = demo_tools.build(HalamanPalsu(), tujuan.append)
    pulihkan = cari_kontrol(
        root,
        lambda control: getattr(control, "on_click", None) is not None
        and punya_teks(control, "Kembali ke waktu asli"),
    )
    ok(pulihkan is not None, "waktu simulasi punya aksi pemulihan yang jelas")
    if pulihkan is not None:
        pulihkan.on_click(None)
    ok(storage.day_offset() == 0 and storage.hour_offset() == 0,
       "pemulihan mengembalikan tanggal dan jam asli")

    storage.set_last_brief_date()
    ok(not storage.ready_for_morning_brief(),
       "kontrol: Morning Brief sudah pernah tampil hari ini")
    tujuan.clear()
    root = demo_tools.build(HalamanPalsu(), tujuan.append)
    ulang = cari_kontrol(
        root,
        lambda control: getattr(control, "on_click", None) is not None
        and punya_teks(control, "Ulang alur pembukaan"),
    )
    ok(ulang is not None, "kontrol ulang alur pembukaan tersedia")
    if ulang is not None:
        ulang.on_click(None)
    ok(storage.ready_for_morning_brief(),
       "ulang alur pembukaan memaksa Morning Brief tampil lagi untuk demo")
    ok(tujuan == ["home"],
       "ulang alur pembukaan masuk lewat route Home agar gate Brief dijalankan")

    home_root = home.build(HalamanPalsu(), tujuan.append)
    demo_icons = [
        item for item in jalan_tree(home_root)
        if isinstance(item, ft.IconButton) and item.tooltip == "Alat Demo"
    ]
    old_icons = [
        item for item in jalan_tree(home_root)
        if isinstance(item, ft.IconButton)
        and isinstance(item.tooltip, str)
        and any(label in item.tooltip for label in (
            "Maju 1 hari", "Lompat ke malam", "Tutup & buka lagi app", "Auto Feel"
        ))
    ]
    ok(len(demo_icons) == 1, "header hanya menampilkan satu ikon Alat Demo")
    ok(not old_icons, "empat shortcut demo lama sudah tidak memenuhi header")


def tes_komponen_baru():
    bagian("Komponen baru: badge premium & rayaan tugas")
    from app import ui_helpers

    ok(hasattr(ui_helpers, "premium_badge"), "premium_badge ada")
    ok(hasattr(ui_helpers, "premium_header"), "premium_header ada")
    ok(hasattr(ui_helpers, "reward_overlay"), "reward_overlay ada")
    ok(len(ui_helpers.REWARD_LINES) >= 3, "kalimat rayaan lebih dari satu (nggak ngulang terus)")

    terkunci = ui_helpers.premium_header("Judul", True)
    bebas = ui_helpers.premium_header("Judul", False)
    ok(len(terkunci.controls) == 2, "free tier -> judul + badge")
    ok(len(bebas.controls) == 1, "premium -> judul doang, nggak diiklanin lagi")


def tes_fokus_ngunci():
    bagian("Mode fokus ngunci seluruh navigation utama")
    import flet as ft
    import app.main as main_mod
    from app import focus_session, theme

    ok([route for route, _, _ in main_mod.NAV_ROUTES] == ["tracker", "home", "mood"],
       "navigasi bawah berurutan Tracker — Home — Mood")
    ok(
        [label for _, label, _ in main_mod.NAV_ROUTES]
        == ["Tracker", "Home", "Mood"]
        and main_mod.NAV_LABEL_BEHAVIOR
        == ft.NavigationBarLabelBehavior.ONLY_SHOW_SELECTED
        and main_mod.NAV_BACKGROUND == "#1C1C26"
        and main_mod.NAV_FOREGROUND == "#DDE0FF"
        and main_mod.NAV_INDICATOR == "#484863",
        "navigation gelap menampilkan ikon dan label aktif berwarna cerah",
    )
    app_theme = theme.build_theme()
    ok(
        app_theme.dialog_theme.bgcolor == "#1C1C26"
        and app_theme.dialog_theme.title_text_style.color == "#FFFFFF"
        and app_theme.dialog_theme.content_text_style.color == "#FFFFFF",
        "popup cerita dan dialog default memakai latar gelap dengan tulisan putih",
    )
    from app.views import daily_checkin, reset
    ok(
        theme.BACKGROUND == daily_checkin.BACKGROUND == "#141416"
        and reset.BACKGROUND == "#232337",
        "background shell dan Check-in #141416; Kewalahan khusus #232337",
    )

    ok("reset" not in main_mod.FOKUS_BOLEH,
       "OVERWHELM tidak dibuka di tengah sesi; user mengakhiri sesi dulu")
    ok("home" in main_mod.FOKUS_BOLEH, "Beranda boleh (di situ timernya tinggal)")
    ok("tracker" not in main_mod.FOKUS_BOLEH, "Tracker dikunci pas lagi fokus")

    focus_session.stop()
    ok(not focus_session.is_running(), "nggak ada sesi -> nggak ngunci apa-apa")
    focus_session.start(20, label="Nulis bab 1")
    ok(focus_session.is_running(), "sesi jalan -> kunci aktif")
    focus_session.stop()


def tes_pertanyaan_makan_dan_jam():
    bagian("Pertanyaan 'udah makan?' cuma nongol lewat jam 18, jam app bisa dilompatin buat demo")
    from app import clock

    storage_baru("makan_")

    try:
        maju = clock.hours_until(18)
        ok(0 < maju <= 24, f"hours_until(18) selalu > 0, nggak pernah mundur (dapet {maju})")

        storage.jump_to_hour(storage.MEAL_ASK_HOUR)
        ok(clock.now().hour >= storage.MEAL_ASK_HOUR,
           f"jump_to_hour(18) -> jam app sekarang {clock.now().hour}, harus >= 18")
        ok(storage.waktunya_tanya_makan(), "udah lewat jam 18 -> waktunya_tanya_makan True")
        ok(storage.hour_offset() > 0, "offset jam ikut kesimpen ke storage")

        ok(storage.today_mood() is None, "belum check-in (kontrol)")
        ok(not storage.perlu_tanya_makan(),
           "udah malem tapi BELUM check-in -> perlu_tanya_makan tetap False")

        storage.add_mood_log(mood="tenang", score=4, energy=5, diary="cerita",
                             tags=["produktif"], quick_tags=["kuliah"])
        ok(storage.perlu_tanya_makan(), "udah check-in + lewat jam 18 -> perlu_tanya_makan True")

        log = storage.today_mood()
        storage.add_mood_log(mood=log["mood"], score=log["score"], energy=log["energy"],
                             diary=log["diary"], tags=log["tags"], quick_tags=log["quick_tags"],
                             ate_today=False, rested_enough=log.get("rested_enough"))
        after = storage.today_mood()
        ok(after["ate_today"] is False, "jawaban 'belum makan' kesimpen jadi False, bukan None")
        ok(after["diary"] == "cerita", "diary nggak kehapus pas jawab pertanyaan makan")
        ok(after["quick_tags"] == ["kuliah"], "quick_tags nggak kehapus pas jawab pertanyaan makan")
        ok(not storage.perlu_tanya_makan(), "udah dijawab -> gerbang nutup lagi")

        storage.advance_day(3)
        hari_setelah_maju = clock.today()
        storage.clear_hour_offset()
        ok(clock.today() == hari_setelah_maju,
           "clear_hour_offset() nggak ngutak-atik geseran hari yang udah dipasang")
        ok(storage.hour_offset() == 0, "clear_hour_offset() -> offset jam balik nol")

        storage.clear_day_offset()
        besok = clock.today() + timedelta(days=1)
        for _ in range(30):
            clock.advance_hours(1)
            if clock.today() == besok:
                break
        ok(clock.today() == besok,
           "today() diturunin dari now() -- geseran jam yang nyebrang tengah malam ikut ganti tanggal")
    finally:
        clock.reset_offset()

    storage_baru("bukaulang_")
    storage.save_profile({})
    storage.add_mood_log(mood="tenang", score=4, energy=5, ate_today=True)
    storage.set_last_brief_date()
    ok(not storage.needs_morning_brief(), "brief udah ditandai tampil hari ini")
    storage.clear_last_brief_date()
    ok(storage.needs_morning_brief(), "clear_last_brief_date() -> brief nyala lagi")
    ok(storage.today_mood()["ate_today"] is True, "clear_last_brief_date() nggak nyentuh data mood")


def tes_pecah_hemat_api():
    bagian("Pecah Tugas: pungut hasil lama biar nggak nelpon API terus")
    from unittest.mock import patch

    from app.core import decomposer_logic as dl
    from models import model_pecah

    storage_baru("pecah_")

    rec = [
        {"title": "Quiz Kalkulus 1", "description": "latihan soal integral bab 3",
         "steps": ["Baca catatan", "Kerjain 5 soal"], "source": "ai", "language": "id"},
        {"title": "Laporan bulanan", "description": "rekap penjualan",
         "steps": ["Kumpulin data", "Bikin grafik"], "source": "ai", "language": "id"},
    ]

    ok(model_pecah.cari("Quiz Kalkulus 1", "latihan soal integral bab 3", rec).ketemu,
       "judul+deskripsi sama persis -> kepungut")
    ok(model_pecah.cari("Quiz Kalkulus 1", "", rec).ketemu,
       "judul sama tapi deskripsi kosong -> TETAP kepungut "
       "(catatan lama yang deskripsinya panjang nggak boleh bikin skor jatuh)")
    ok(not model_pecah.cari("Masak nasi goreng", "buat makan malam", rec).ketemu,
       "tugas nggak nyambung -> DITOLAK, jangan asal pungut")
    ok(not model_pecah.cari("Quiz Matematika Diskrit", "kombinatorik", rec).ketemu,
       "quiz matkul LAIN -> ditolak (mirip dikit doang nggak cukup)")

    tugas = {"title": "Bikin proposal", "description": "Cari ide\nCari solusi\nTulis draft",
             "important": True, "kategori": "", "jumlah_unit": 0, "menit_est": 0}
    with patch.object(
        model_pecah,
        "cari",
        return_value=model_pecah.HasilPecah(ketemu=False, langkah=[]),
    ):
        langkah, sumber = dl._langkah_lokal(tugas)
    ok(sumber != "manual" and langkah is None,
       "baris deskripsi tetap menjadi konteks dan tidak disalin sebagai langkah manual")
    fallback = [step for _title, step, _minutes in dl._rule_based_steps([tugas], 4)]
    ok("Cari ide" not in fallback and "Cari solusi" not in fallback,
       "fallback juga tidak mengubah kalimat deskripsi menjadi daftar langkah")

    dipanggil = {"n": 0}
    asli = dl._ai_steps
    dl._ai_steps = lambda t, e: (dipanggil.__setitem__("n", dipanggil["n"] + 1),
                                 (None, "dimatiin buat tes"))[1]
    try:
        for r in rec:
            storage.add_decompose_record(r["title"], r["description"], r["steps"], r["source"])

        hasil = dl.plan_today(
            [{"title": "Quiz Kalkulus 1", "description": "", "important": True,
              "kategori": "", "jumlah_unit": 0, "menit_est": 0}], 4)
        ok(dipanggil["n"] == 0, f"tugas mirip catatan lama -> NOL panggilan API (dapet {dipanggil['n']})")
        ok(hasil.source == "lokal", f"source='lokal', bukan 'fallback' (dapet {hasil.source!r})")
        ok(hasil.n_lokal == 1 and hasil.n_ai == 0, "kehitung sebagai hemat, bukan panggilan AI")

        dl.plan_today(
            [{"title": "Nyuci motor sampe kinclong", "description": "", "important": False,
              "kategori": "", "jumlah_unit": 0, "menit_est": 0}], 4)
        ok(dipanggil["n"] == 1,
           f"tugas BENERAN baru -> tetap nelpon AI (dapet {dipanggil['n']}) -- "
           "penghematan nggak boleh sampai matiin fiturnya")
    finally:
        dl._ai_steps = asli

    storage_baru("pecah2_")
    storage.add_decompose_record("Tugas X", "", ["langkah 1", "langkah 2"], "ai")
    ok(len(storage.get_decompose_records()) == 1, "hasil pecahan kesimpen")
    storage.add_decompose_record("Tugas X", "", ["langkah beda"], "ai")
    ok(len(storage.get_decompose_records()) == 1,
       "judul+deskripsi sama -> DITIMPA, bukan numpuk duplikat yang nanti rebutan")
    ok(storage.get_decompose_records()[0]["steps"] == ["langkah beda"], "isinya yang terbaru")
    ok(storage.add_decompose_record("", "", ["x"], "ai") is None, "judul kosong -> nggak disimpen")
    ok(storage.add_decompose_record("Ada judul", "", [], "ai") is None, "langkah kosong -> nggak disimpen")


def tes_retrieval_bahasa_natural():
    bagian("Pecah Tugas: retrieval bahasa natural (paraphrase, bukan variasi awalan)")
    from models import model_pecah

    bawaan = list(model_pecah._pola_bawaan())
    target = "Beresin kamar"

    kasus = [
        ("gue harus beresin kamar", False),
        ("kamar gue udah berantakan", True),
        ("mau mulai rapihin kamar", False),
        ("tolong bantu gue mulai beberes", False),
        ("bingung mulai dari mana buat kamar", False),
    ]
    salah = 0
    for query, wajib in kasus:
        hasil = model_pecah.cari(query, records=bawaan)
        if not hasil.ketemu:
            ok(not wajib, f"'{query}' -> fallback ke AI/template (aman, bukan salah pungut)")
            continue
        cocok = hasil.dari_judul == target
        if cocok:
            ok(True, f"'{query}' -> retrieval BENAR ke {target!r} (skor {hasil.skor:.2f})")
        else:
            salah += 1
            ok(False, f"'{query}' -> SALAH PUNGUT ke {hasil.dari_judul!r} "
                      f"(skor {hasil.skor:.2f}), harusnya {target!r}")
    ok(salah == 0, f"wrong-retrieval-rate = 0% di lima paraphrase kamar berantakan (dapet {salah}/5 salah)")

    kamar_mandi = model_pecah.cari("kamar mandi gue kotor banget", records=bawaan)
    ok(not kamar_mandi.ketemu or kamar_mandi.dari_judul != target,
       f"'kamar mandi kotor' TIDAK nyasar ke {target!r} "
       f"(dapet: {'fallback' if not kamar_mandi.ketemu else kamar_mandi.dari_judul!r})")

    tugas_lain = model_pecah.cari("bikin proposal buat ikut lomba hackathon", records=bawaan)
    ok(not tugas_lain.ketemu or tugas_lain.dari_judul != target,
       "query yang nggak nyambung sama sekali TIDAK nyasar ke 'Beresin kamar'")


def tes_fallback_ai_valid():
    bagian("Pecah Tugas: fallback AI buat kasus yang lokal-nya nggak yakin")
    from unittest.mock import patch

    from app.core import ai_client, decomposer_logic as dl
    from models import model_pecah

    storage_baru("fallback_ai_")

    judul = "gue stuck banget sama skripsi"
    cek_lokal = model_pecah.cari(judul, records=list(model_pecah._pola_bawaan()))
    ok(not cek_lokal.ketemu and cek_lokal.skor < model_pecah.AMBANG_MIRIP,
       f"premis: retrieval lokal beneran nggak yakin buat '{judul}' "
       f"(skor {cek_lokal.skor:.2f} < ambang {model_pecah.AMBANG_MIRIP})")

    balasan_ai = [
        {"tugas": judul, "langkah": "Buka dokumen skripsi dan baca ulang bab terakhir"},
        {"tugas": judul, "langkah": "Tulis satu kalimat apa aja buat nyambungin, nggak usah sempurna"},
    ]
    dipanggil = {"n": 0}

    def ai_palsu(**kwargs):
        dipanggil["n"] += 1
        return balasan_ai, ""

    with patch.object(ai_client, "generate_json", side_effect=ai_palsu):
        hasil = dl.plan_today(
            [{"title": judul, "description": "", "important": True,
              "kategori": "", "jumlah_unit": 0, "menit_est": 30}],
            energy_level=3, allow_ai=True,
        )

    ok(dipanggil["n"] == 1, "confidence lokal rendah -> fallback ke AI BENERAN kejadian (dipanggil 1x)")
    ok(hasil.source == "ai", f"source label bilang 'ai' (dapet {hasil.source!r}), "
                             "TIDAK ngaku 'lokal'/'campuran' padahal lokal 0% kontribusi")
    ok(hasil.n_ai == 1 and hasil.n_lokal == 0,
       f"kehitung murni sebagai panggilan AI (n_ai={hasil.n_ai}, n_lokal={hasil.n_lokal})")

    teks_langkah = [b.step for b in hasil.blocks if not b.is_break]
    ok(teks_langkah == [item["langkah"] for item in balasan_ai],
       "langkah yang dipakai PERSIS dari balasan AI, bukan dikarang ulang atau dicampur pola lokal")

    tersimpan = storage.get_decompose_records()
    sumber_tersimpan = tersimpan[0]["source"] if tersimpan else None
    ok(len(tersimpan) == 1 and sumber_tersimpan == "ai",
       f"hasil AI kesimpen dengan source='ai' (dapet {sumber_tersimpan!r}) "
       "-- BUKAN 'dataset', biar nggak ngaku-ngaku asalnya dari pola bawaan")


def tes_label_keputusan():
    bagian("Label keputusan: 'Kalem nampilin X, user mencet apa nggak'")
    from models import fitur as F

    storage_baru("label_")

    f = F.bangun_fitur()
    storage.record_decision_shown("next_action", "focus", f, "FOKUS 20 menit")
    storage.record_decision_shown("next_action", "focus", f, "FOKUS 20 menit")
    storage.record_decision_shown("next_action", "focus", f, "FOKUS 20 menit")
    rec = storage.get_decision_records()
    ok(len(rec) == 1,
       f"3x ditampilin -> tetap 1 catatan (dapet {len(rec)}) -- bukan baris baru tiap render")
    ok(rec[0]["n_tampil"] == 3, f"n_tampil kehitung = 3 (dapet {rec[0]['n_tampil']})")
    ok(not rec[0]["acted"], "belum dipencet -> acted False")
    ok(len(rec[0]["fitur"]) > 5, "fitur kondisi saat itu ikut kesimpen buat bahan latih")

    ok(storage.record_decision_acted("next_action", "focus"), "penandaan dipencet berhasil")
    ok(storage.get_decision_records()[0]["acted"], "acted jadi True")

    storage.record_decision_shown("next_action", "focus", f, "FOKUS 20 menit")
    ok(len(storage.get_decision_records()) == 2,
       "sesudah dipencet, tampilan berikutnya jadi catatan baru")

    ok(not storage.record_decision_acted("calm", "add_task"),
       "nandai keputusan yang nggak pernah ditampilin -> False, bukan bikin data palsu")
    ok(storage.record_decision_shown("", "focus", f) is None, "kind kosong -> nggak dicatat")


def tes_ml_kalem_tidak_kontaminasi():
    bagian("ML_KALEM: fitur decision-time TIDAK boleh ketimpa data outcome-time")
    from models import fitur as F
    from models import model_kalem

    storage_baru("kontaminasi_")

    fitur_awal = F.Fitur(
        nilai={"energi_terakhir": 1.0, "skor_3h": 2.0, "n_belum_selesai": 6.0},
        tanggal=storage.clock.today().isoformat(), catatan={},
    )
    storage.record_decision_shown("next_action", "focus", fitur_awal, "FOKUS 15 menit")

    fitur_belakangan = F.Fitur(
        nilai={"energi_terakhir": 6.0, "skor_3h": 5.0, "n_belum_selesai": 0.0},
        tanggal=storage.clock.today().isoformat(), catatan={},
    )
    storage.record_decision_shown("next_action", "focus", fitur_belakangan, "FOKUS 15 menit")
    tersimpan_sebelum_klik = storage.get_decision_records()[0]["fitur"]
    ok(tersimpan_sebelum_klik["energi_terakhir"] == 1.0,
       "tampilan ulang dengan kondisi yang UDAH BEDA tidak menimpa fitur decision-time "
       f"yang tercatat pertama kali (tetap energi_terakhir={tersimpan_sebelum_klik['energi_terakhir']})")

    storage.record_decision_acted("next_action", "focus")
    tersimpan_sesudah_klik = storage.get_decision_records()[0]["fitur"]
    ok(tersimpan_sesudah_klik == tersimpan_sebelum_klik,
       "record_decision_acted() (outcome time) TIDAK mengubah field fitur (decision time) sama sekali")

    field_outcome = {"acted", "acted_at", "n_tampil", "started", "started_at",
                     "completed", "completed_at"}
    bocor = field_outcome & set(model_kalem.FEATURES)
    ok(not bocor, f"model_kalem.FEATURES nggak nyerempet field outcome-only (dapet bocor: {bocor})")

    kolom_skema = set(storage.get_decision_records()[0].keys())
    ok({"started", "completed", "helpful"} <= kolom_skema,
       "decision lifecycle punya started/completed/helpful sebagai outcome terpisah")


def tes_regresi_data_dan_tugas_berulang():
    bagian("Diary, Reset, overdue, dan tugas berulang")
    from app import clock
    from app.core.reset_preferences import detect_distress

    storage_baru("regresi_baru_")

    storage.add_mood_log("lelah", 2, 2, ate_today=True, rested_enough=False)
    storage.add_mood_log("lelah", 2, 2, diary="Hari ini berat")
    log = storage.today_mood()
    ok(log["ate_today"] is True and log["rested_enough"] is False,
       "simpan Diary nggak menghapus jawaban makan/istirahat")

    today = clock.today()
    logs = [{"date": today.isoformat(), "score": 1}]
    events_same_day = [{"date": today.isoformat(), "choice": "napas"} for _ in range(4)]
    ok(not detect_distress(events_same_day, logs).escalate,
       "4 event di hari sama bukan 4 hari distress")

    yesterday = (today - timedelta(days=1)).isoformat()
    overdue = storage.add_task("Tugas kemarin", yesterday, steps=[{"text": "mulai", "done": False}])
    ok(any(t["id"] == overdue["id"] for t in storage.tasks_actionable_today()),
       "tugas terlambat tidak menghilang dari next action")

    weekly = storage.add_task(
        "Review mingguan", today.isoformat(), steps=[{"text": "baca", "done": False}], repeat="weekly"
    )
    this_week = next(t for t in storage.tasks_for(today.isoformat()) if t["id"] == weekly["id"])
    storage.set_step_done(weekly["id"], 0, True, this_week["_occurrence_date"])
    this_week = next(t for t in storage.tasks_for(today.isoformat()) if t["id"] == weekly["id"])
    next_day = (today + timedelta(days=7)).isoformat()
    next_week = next(t for t in storage.tasks_for(next_day) if t["id"] == weekly["id"])
    ok(storage.task_is_done(this_week), "occurrence minggu ini bisa selesai")
    ok(not storage.task_is_done(next_week), "selesai minggu ini tidak menutup minggu depan")


def tes_voice_diary():
    bagian("Diary suara: audio sementara, transkrip bisa direview")
    import io
    import math
    import struct
    import wave
    from types import SimpleNamespace

    import flet as ft

    from app.core import speech_to_text as stt
    from app.views import diary

    pcm = b"".join(
        struct.pack("<h", int(2400 * math.sin(2 * math.pi * 220 * i / stt.SAMPLE_RATE)))
        for i in range(stt.SAMPLE_RATE)
    )
    wav_bytes = stt.pcm16_to_wav(pcm)
    with wave.open(io.BytesIO(wav_bytes), "rb") as audio:
        ok(audio.getnchannels() == 1 and audio.getframerate() == 16_000,
           "PCM dari browser dibungkus jadi WAV mono 16 kHz")
        ok(audio.getnframes() == stt.SAMPLE_RATE,
           "durasi frame WAV tidak berubah saat dibungkus")

    original_provider = stt._speech_provider
    original_gemini = stt._transcribe_gemini
    captured = {"wav": b""}
    try:
        stt._speech_provider = lambda: "gemini"

        def fake_transcribe(wav: bytes):
            captured["wav"] = wav
            return "Hari ini aku agak capek.", ""

        stt._transcribe_gemini = fake_transcribe
        transcript, error = stt.transcribe_pcm16(
            pcm + b"\x00" * stt.MAX_PCM_BYTES
        )
    finally:
        stt._speech_provider = original_provider
        stt._transcribe_gemini = original_gemini

    ok(transcript == "Hari ini aku agak capek." and not error,
       "hasil provider diteruskan sebagai teks Diary, bukan langsung disimpan")
    with wave.open(io.BytesIO(captured["wav"]), "rb") as audio:
        ok(audio.getnframes() * stt.SAMPLE_WIDTH == stt.MAX_PCM_BYTES,
           "audio yang dikirim tetap dipotong pada batas 120 detik")

    short_text, short_error = stt.transcribe_pcm16(b"\x00\x00" * 100)
    ok(not short_text and short_error == stt.PESAN_TERLALU_PENDEK,
       "rekaman terlalu pendek ditolak sebelum memanggil provider")

    silent_text, silent_error = stt.transcribe_pcm16(b"\x00\x00" * stt.SAMPLE_RATE)
    ok(not silent_text and silent_error == stt.PESAN_TIDAK_TERDENGAR,
       "rekaman panjang tetapi sunyi ditolak sebelum memanggil provider")

    quiet_pcm = b"".join(
        struct.pack("<h", int(40 * math.sin(2 * math.pi * 220 * i / stt.SAMPLE_RATE)))
        for i in range(stt.SAMPLE_RATE)
    )
    original_provider = stt._speech_provider
    original_gemini = stt._transcribe_gemini
    try:
        stt._speech_provider = lambda: "gemini"
        stt._transcribe_gemini = lambda wav: ("Suara pelan masih terbaca.", "")
        quiet_text, quiet_error = stt.transcribe_pcm16(quiet_pcm)
    finally:
        stt._speech_provider = original_provider
        stt._transcribe_gemini = original_gemini
    ok(quiet_text == "Suara pelan masih terbaca." and not quiet_error,
       "suara pelan dengan sinyal nyata tetap diteruskan ke provider")

    ok(not stt._clean_transcript("<noise>") and not stt._clean_transcript("[silence]"),
       "marker noise atau silence dari provider tidak masuk ke textbox")

    from app.voice_diary import VoiceDiary

    stream_probe = VoiceDiary.__new__(VoiceDiary)
    stream_probe.active = True
    stream_probe.recording = False
    stream_probe.stopping = True
    stream_probe.chunks = bytearray()
    stream_probe._on_audio_chunk(SimpleNamespace(chunk=b"\x01\x02"))
    ok(stream_probe.chunks == b"\x01\x02",
       "chunk terakhir tetap diterima ketika stop recording sedang berjalan")

    storage_baru("voice_diary_")
    page = HalamanPalsu()
    root = diary.build(page, lambda route: None)
    mic_button = cari_kontrol(
        root,
        lambda control: isinstance(control, ft.IconButton)
        and control.icon == ft.Icons.MIC_NONE
        and getattr(control, "on_click", None) is not None,
    )
    ok(mic_button is not None,
       "halaman Diary menyediakan tombol mikrofon kecil tanpa label panjang")
    ok(stt.MAX_RECORD_SECONDS == 120,
       "batas satu rekaman Diary suara adalah 120 detik")
    ok(any(
        "rekaman" in (getattr(item, "value", "") or "").lower()
        and "tidak disimpan" in (getattr(item, "value", "") or "").lower()
        for item in jalan_tree(root)
    ), "UI menjelaskan rekaman suara tidak disimpan")


def tes_langkah_tambahan_dan_ml_kalem():
    bagian("Langkah tambahan user & ML_KALEM")
    from app.core import decomposer_logic as dl
    from models import model_kalem

    storage_baru("kalem_baru_")
    tugas = {
        "title": "Latihan soal yang unik", "description": "", "important": True,
        "kategori": "", "jumlah_unit": 0, "menit_est": 30,
        "custom_steps": ["Ambil pensil", "Siapkan kalkulator"],
    }
    hasil = dl.plan_today([tugas], 3, allow_ai=False)
    teks = [step for _title, step, _menit in hasil.steps]
    ok(teks[1:3] == ["Ambil pensil", "Siapkan kalkulator"],
       "langkah tambahan disisipkan setelah langkah pembuka Kalem")

    records = []
    for i in range(24):
        low = i < 12
        records.append({
            "kind": "next_action", "action_kind": "focus", "acted": not low,
            "n_tampil": 3 if low else 1,
            "fitur": {
                "energi_terakhir": 1 if low else 6,
                "skor_3h": 2 if low else 5,
                "n_belum_selesai": 6 if low else 1,
            },
        })
    try:
        sinyal = model_kalem.nilai({"energi_terakhir": 1, "skor_3h": 2, "n_belum_selesai": 6}, records)
        ok(sinyal.siap and sinyal.perlu_diringankan,
           "ML_KALEM aktif setelah data cukup dan hanya meringankan target")
        sekali_dilihat = dict(records[0], n_tampil=1)
        ok(sekali_dilihat not in model_kalem._records_layak([sekali_dilihat]),
           "recommendation yang baru sekali terlihat dan belum dipencet tetap netral")
        tiga_kali_dilewati = dict(sekali_dilihat, n_tampil=3)
        ok(tiga_kali_dilewati in model_kalem._records_layak([tiga_kali_dilewati]),
           "recommendation yang dilewati berulang baru boleh menjadi sinyal peringanan")
        belum = model_kalem.nilai({}, records[:8])
        ok(not belum.siap, "ML_KALEM tetap diam saat data belum cukup")
    finally:
        model_kalem.reset_model()


def tes_fokus_pakai_decision_task():
    bagian("Home start_focus pakai decision.task, bukan cari ulang lewat judul")
    from app import focus_session
    from app.views import home

    storage_baru("dupejudul_")
    pasang_logs(skor=4, n=5, energi=4)
    today = storage.clock.today().isoformat()

    storage.add_task(
        "Tugas kembar", today, important=True, difficulty_est=3,
        kategori="Rumah", jumlah_unit=99,
        steps=[{"text": "langkah decoy", "done": False}],
    )
    storage.add_task(
        "Tugas kembar", today, important=True, difficulty_est=1,
        kategori="Akademik", jumlah_unit=5,
        steps=[{"text": "langkah benar", "done": False}],
    )

    focus_session.stop()
    root = home.build(HalamanPalsu(), lambda r: None)
    tombol = cari_tombol_berteks(root, "FOKUS")
    ok(tombol is not None, "tombol FOKUS ketemu di halaman Beranda")
    if tombol is None:
        return

    fake_event = type("FakeEvent", (), {"control": None})()
    tombol.on_click(fake_event)

    snap = focus_session.snapshot()
    ok(snap["kategori"] == "Akademik" and snap["jumlah_unit"] == 5,
       "sesi fokus makai metadata dari decision.task yang beneran dipilih "
       f"(dapet kategori={snap['kategori']!r}, jumlah_unit={snap['jumlah_unit']!r}), "
       "bukan tugas kembar yang judulnya kebetulan sama")
    focus_session.stop()


def tes_fokus_pakai_decision_task_tugas_berulang():
    bagian("Identitas decision.task tetap benar buat occurrence tugas berulang")
    from app import focus_session
    from app.views import home

    storage_baru("dupejudul_berulang_")
    pasang_logs(skor=4, n=5, energi=4)
    today = storage.clock.today().isoformat()

    storage.add_task(
        "Tugas", today, important=True, difficulty_est=3,
        kategori="Organisasi", jumlah_unit=7,
        steps=[{"text": "langkah organisasi", "done": False}],
    )
    tugas_berulang = storage.add_task(
        "Tugas", today, important=True, difficulty_est=1,
        kategori="Kuliah", jumlah_unit=3,
        steps=[{"text": "langkah kuliah", "done": False}], repeat="daily",
    )

    focus_session.stop()
    root = home.build(HalamanPalsu(), lambda r: None)
    tombol = cari_tombol_berteks(root, "FOKUS")
    ok(tombol is not None, "tombol FOKUS ketemu di halaman Beranda")
    if tombol is None:
        return

    fake_event = type("FakeEvent", (), {"control": None})()
    tombol.on_click(fake_event)

    snap = focus_session.snapshot()
    ok(snap["kategori"] == "Kuliah" and snap["jumlah_unit"] == 3,
       "sesi fokus makai metadata occurrence tugas BERULANG yang beneran dipilih "
       f"(dapet kategori={snap['kategori']!r}, jumlah_unit={snap['jumlah_unit']!r}), "
       "bukan tugas sekali-jalan yang judulnya kebetulan sama")

    ulang = storage.tasks_actionable_today()
    dipilih = next((t for t in ulang if t.get("kategori") == "Kuliah"), None)
    ok(dipilih is not None and dipilih["id"] == tugas_berulang["id"]
       and dipilih.get("_occurrence_date") == today,
       "occurrence tugas berulang bawa id tugas dasar yang sama + _occurrence_date yang benar")
    focus_session.stop()


def tes_pecah_tugas_judul_kembar():
    bagian("Pecah Tugas: judul kembar tidak saling menimpa")
    from app.core import decomposer_logic as dl

    storage_baru("pecah_kembar_")
    pertama = storage.add_task(
        "Belajar", storage.clock.today().isoformat(), description="Buka catatan A\nTandai rumus A",
        custom_steps=["Tandai rumus A"],
    )
    kedua = storage.add_task(
        "Belajar", storage.clock.today().isoformat(), description="Buka catatan B\nTandai rumus B",
        custom_steps=["Tandai rumus B"],
    )
    result = dl.plan_today([pertama, kedua], allow_ai=False)
    langkah_pertama = [s["text"] for s in result.task_steps[pertama["id"]]]
    langkah_kedua = [s["text"] for s in result.task_steps[kedua["id"]]]
    ok("Tandai rumus A" in langkah_pertama and "Tandai rumus B" not in langkah_pertama,
       "tugas judul kembar pertama mempertahankan langkahnya sendiri")
    ok("Tandai rumus B" in langkah_kedua and "Tandai rumus A" not in langkah_kedua,
       "tugas judul kembar kedua tidak tertimpa langkah tugas pertama")


def tes_onboarding_entry_dan_status_custom():
    import flet as ft
    from app.views import onboarding

    bagian("Entry onboarding: copy baru & kesibukan custom")
    storage_baru("onboarding_copy_")
    tujuan: list[str] = []
    page = HalamanPalsu()
    dialogs: list[ft.Control] = []
    page.show_dialog = dialogs.append
    root = onboarding.build(page, tujuan.append)

    name = cari_kontrol(
        root, lambda c: isinstance(c, ft.TextField) and c.label == "Nama panggilan kamu"
    )
    ok(name is not None and not name.hint_text,
       "field nama pakai 'Nama panggilan kamu' tanpa contoh placeholder")
    ok(name is not None and name.width == onboarding.FORM_WIDTH,
       "pertanyaan dan field nama memakai lebar form ringkas yang bisa dipusatkan")
    intro = cari_kontrol(
        root,
        lambda c: isinstance(c, ft.Text)
        and "".join(getattr(span, "text", "") for span in (c.spans or []))
        == "Haloo\nAku KALEM!",
    )
    ok(intro is not None and punya_teks(root, "Developed By ATURLAH - FASILKOM UI"),
       "entry memakai intro KALEM rata kiri dan credit developer")
    if intro is not None:
        ok(all(getattr(span.style, "height", 0) == 1.22 for span in intro.spans),
           "judul Haloo dan Aku KALEM punya jarak antarbaris yang lebih lega")
    ok(
        list(storage.PRODUCTIVE_TIME_OPTIONS.values())
        == ["Pagi", "Siang", "Sore", "Malam", "Tidak tentu"],
        "pilihan waktu fokus ringkas: Pagi–Siang–Sore–Malam–Tidak tentu",
    )
    ok(list(storage.MEDICATION_OPTIONS.values())
       == ["Ada, rutin", "Nggak ada", "Kadang-kadang aja"],
       "pilihan obat sesuai copy baru")
    ok(list(storage.TRIGGER_OPTIONS.values())
       == ["Tugas numpuk", "Deadline mepet", "Susah mulai sesuatu",
           "Gampang terdistraksi", "Kurang tidur", "Interaksi sosial"],
       "pilihan pemicu overwhelm sesuai copy baru")
    if name is None:
        return

    name.value = "Raka"
    lanjut = cari_tombol_berteks(root, "Selanjutnya")
    if lanjut is None:
        ok(False, "tombol lanjut entry ditemukan")
        return
    lanjut.on_click(None)

    tanggal = cari_kontrol(
        root,
        lambda c: getattr(c, "on_click", None) is not None
        and punya_teks(c, "Pilih tanggal lahir"),
    )
    if tanggal is None:
        ok(False, "field tanggal lahir ditemukan")
        return
    tanggal.on_click(None)
    picker = dialogs[-1] if dialogs else None
    ok(isinstance(picker, ft.DatePicker), "tanggal lahir membuka DatePicker native")
    if not isinstance(picker, ft.DatePicker):
        return
    picker.value = datetime(2004, 1, 28, 17, tzinfo=timezone.utc)
    picker.on_change(SimpleNamespace(data="2004-01-29"))
    ok(punya_teks(root, "Tanggal Lahir Kamu?"),
       "pertanyaan tanggal lahir memakai copy baru")

    nav = cari_kontrol(
        root,
        lambda c: isinstance(c, ft.Row)
        and len(c.controls) == 1
        and punya_teks(c.controls[0], "Selanjutnya"),
    )
    ok(nav is not None and not punya_teks(root, "Kembali"),
       "onboarding hanya menampilkan tombol Selanjutnya selebar area konten")
    lanjut = cari_tombol_berteks(root, "Selanjutnya")
    if lanjut is None:
        ok(False, "tombol lanjut tanggal lahir ditemukan")
        return
    lanjut.on_click(None)

    pekerjaan = cari_kontrol(
        root,
        lambda c: isinstance(c, ft.Dropdown)
        and c.hint_text == "Pilih pekerjaan atau kesibukan",
    )
    if pekerjaan is None:
        ok(False, "pekerjaan menggunakan dropdown")
        return
    ok(
        pekerjaan.fill_color == onboarding.INPUT_BG
        and pekerjaan.bgcolor == onboarding.INPUT_BG
        and pekerjaan.color == onboarding.TEXT_PRIMARY
        and all(
            getattr(option, "text", None) != getattr(option, "key", None)
            for option in pekerjaan.options
            if getattr(option, "key", None) != "lainnya"
        ),
        "dropdown gelap menampilkan label manusia, bukan nilai internal ber-underscore",
    )
    pekerjaan.value = "lainnya"
    pekerjaan.on_select(SimpleNamespace(control=pekerjaan))
    status = cari_kontrol(
        root, lambda c: isinstance(c, ft.TextField) and c.hint_text == "Tulis kesibukan kamu"
    )
    if status is None:
        ok(False, "Lainnya membuka input kesibukan")
        return
    status.value = "Content creator"
    simpan_status = cari_kontrol(
        root, lambda c: isinstance(c, ft.IconButton)
        and c.icon == ft.Icons.CHECK and getattr(c, "on_click", None) is not None
    )
    if simpan_status is None:
        ok(False, "tombol simpan kesibukan custom ditemukan")
        return
    simpan_status.on_click(None)

    def lewati_dan_pilih(hint: str, value: str, label: str) -> bool:
        lanjut = cari_tombol_berteks(root, "Lewati")
        if lanjut is None:
            ok(False, f"tombol lewati menuju {label} ditemukan")
            return False
        lanjut.on_click(None)
        control = cari_kontrol(
            root,
            lambda c: isinstance(c, ft.Dropdown) and c.hint_text == hint,
        )
        ok(control is not None, f"{label} menggunakan dropdown")
        if control is None:
            return False
        control.value = value
        control.on_select(SimpleNamespace(control=control))
        return True

    if not lewati_dan_pilih("Pilih waktu produktif", "pagi", "waktu produktif"):
        return
    if not lewati_dan_pilih("Pilih pola tidur", "cukup", "pola tidur"):
        return
    if not lewati_dan_pilih(
        "Pilih kondisi obat atau suplemen", "tidak", "obat atau suplemen"
    ):
        return
    if not lewati_dan_pilih(
        "Pilih pemicu yang paling sering", "deadline", "pemicu overwhelm"
    ):
        return

    selesai = cari_tombol_berteks(root, "Lewati")
    if selesai is None:
        ok(False, "tombol lewati terakhir onboarding ditemukan")
        return
    selesai.on_click(None)

    profile = storage.get_profile()
    ok(profile["name"] == "Raka"
       and profile["birth_date"] == "2004-01-29"
       and profile["age_range"] == "18-24"
       and profile["status"] == ["Content creator"]
       and profile["productive_time"] == "pagi"
       and profile["productive_hours"] == [[6, 11]]
       and profile["sleep_condition"] == "cukup"
       and profile["on_medication"] == "tidak"
       and profile["overwhelm_triggers"] == ["deadline"]
       and tujuan == ["home"],
       "tanggal lahir dan seluruh jawaban dropdown tersimpan ke profil")


def tes_viewport_phone_global():
    import flet as ft
    from app import main as main_app

    bagian("Viewport browser dikunci ke ukuran aplikasi HP")

    class PagePalsu:
        width = 1200
        on_resize = None

        def update(self):
            pass

    page = PagePalsu()
    wrapper = main_app.phone_view(page, ft.Text("Isi aplikasi"))
    shell = wrapper.controls[0]
    ok(shell.width == main_app.PHONE_VIEW_WIDTH == 430,
       "browser lebar tetap menampilkan aplikasi selebar 430 px")

    page.on_resize(SimpleNamespace(width=360))
    ok(shell.width == 360,
       "layar HP yang lebih kecil tetap muat tanpa horizontal overflow")


def tes_tema_picker_gelap():
    from app import theme

    bagian("Tema pemilih tanggal dan jam mengikuti permukaan gelap aplikasi")
    app_theme = theme.build_theme()
    ok(
        app_theme.visual_density.name == "COMFORTABLE",
        "kepadatan komponen global diperkecil tanpa transform zoom palsu",
    )
    date_theme = app_theme.date_picker_theme
    ok(
        date_theme is not None
        and date_theme.bgcolor == "#24242F"
        and date_theme.header_bgcolor == "#343446"
        and date_theme.header_foreground_color == theme.ON_BACKGROUND,
        "dialog tanggal memakai latar gelap dengan header dan teks putih",
    )
    time_theme = app_theme.time_picker_theme
    ok(
        time_theme is not None
        and time_theme.bgcolor == "#24242F"
        and time_theme.dial_bgcolor == "#343446"
        and time_theme.dial_text_color == theme.ON_BACKGROUND,
        "dialog jam memakai latar dan dial gelap dengan angka putih",
    )


def tes_onboarding_opsional_bisa_dilewati():
    import flet as ft
    from app.views import onboarding

    bagian("Onboarding: pertanyaan opsional bisa dilewati")
    storage_baru("onboarding_skip_")
    tujuan: list[str] = []
    page = HalamanPalsu()
    dialogs: list[ft.Control] = []
    page.show_dialog = dialogs.append
    root = onboarding.build(page, tujuan.append)

    name = cari_kontrol(
        root, lambda c: isinstance(c, ft.TextField) and c.label == "Nama panggilan kamu"
    )
    if name is None:
        ok(False, "field nama onboarding ditemukan")
        return
    name.value = "Raka"
    cari_tombol_berteks(root, "Selanjutnya").on_click(None)

    tanggal = cari_kontrol(
        root,
        lambda c: getattr(c, "on_click", None) is not None
        and punya_teks(c, "Pilih tanggal lahir"),
    )
    tanggal.on_click(None)
    picker = dialogs[-1]
    picker.value = date(2004, 8, 13)
    picker.on_change(None)
    cari_tombol_berteks(root, "Selanjutnya").on_click(None)

    lewati = cari_tombol_berteks(root, "Lewati")
    ok(lewati is not None and not punya_teks(root, "Kembali"),
       "pertanyaan opsional hanya menyediakan tombol Lewati tanpa Kembali")
    if lewati is None:
        return
    lewati.on_click(None)
    ok(punya_teks(root, "Kapan biasanya kamu paling enak buat fokus?")
       and not punya_teks(root, "Pilih atau isi jawaban dulu ya."),
       "jawaban opsional kosong tidak menghalangi langkah berikutnya")


def main() -> int:
    from app import clock
    clock.reset_offset()

    for tes in (
        tes_mendesak_dari_deadline,
        tes_data_basi,
        tes_hari_kosong_bukan_hari_buruk,
        tes_urutan_mood,
        tes_isolasi_model_antar_user,
        tes_fungsi_murni,
        tes_komponen_baru,
        tes_fokus_ngunci,
        tes_pertanyaan_makan_dan_jam,
        tes_pecah_hemat_api,
        tes_retrieval_bahasa_natural,
        tes_fallback_ai_valid,
        tes_label_keputusan,
        tes_ml_kalem_tidak_kontaminasi,
        tes_regresi_data_dan_tugas_berulang,
        tes_voice_diary,
        tes_langkah_tambahan_dan_ml_kalem,
        tes_fokus_pakai_decision_task,
        tes_fokus_pakai_decision_task_tugas_berulang,
        tes_pecah_tugas_judul_kembar,
        tes_onboarding_entry_dan_status_custom,
        tes_onboarding_opsional_bisa_dilewati,
        tes_viewport_phone_global,
        tes_tema_picker_gelap,
        tes_langganan_demo,
        tes_alat_demo_terpusat,
        tes_halaman_kebangun,
    ):
        tes()

    print(f"\n{'=' * 60}")
    if _GAGAL:
        print(f"GAGAL: {len(_GAGAL)}")
        for g in _GAGAL:
            print(f"  - {g}")
        return 1
    print("SEMUA LULUS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
