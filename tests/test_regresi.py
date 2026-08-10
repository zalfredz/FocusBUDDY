"""Regresi FocusBuddy -- jalanin: python tests/test_regresi.py

Sengaja ditaruh DI DALAM project (bukan folder temp) biar ikut ke-commit dan
nggak ilang tiap sesi ganti. Nggak butuh pytest -- cukup python biasa, karena
yang paling penting itu tesnya BISA DIJALANIN kapan aja tanpa setup.

Tiap tes bikin storage-nya sendiri di folder temp, jadi data asli user di
~/.focusbuddy nggak pernah kesentuh.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

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
    """Storage kosong di folder temp. Return path file datanya."""
    d = Path(tempfile.mkdtemp(prefix=prefix))
    storage.DATA_DIR = d / ".focusbuddy"
    storage.DATA_FILE = storage.DATA_DIR / "data.json"
    storage.reset_all_data()
    return storage.DATA_FILE


def pasang_logs(skor: int, n: int, energi: int = 3, sos_idx=(), mulai_dari: int = 0):
    """Isi mood_logs n hari ke belakang. `mulai_dari` nggeser jendelanya
    (buat nyimulasiin user yang udah lama nggak check-in)."""
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
    """Cukup buat manggil build() halaman tanpa UI beneran."""

    def update(self): pass
    def show_dialog(self, d): pass
    def pop_dialog(self): pass
    def run_task(self, fn): pass
    @property
    def overlay(self): return []


def cari_tombol_berteks(kontrol, awalan_label: str):
    """Cari kontrol pertama di tree Flet yang `on_click`-nya keisi & teks
    di dalamnya diawali `awalan_label`. Dipakai buat nge-tes tombol beneran
    yang kepasang di halaman, bukan nyimulasiin ulang logikanya."""
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
    isi = getattr(kontrol, "content", None)
    if isi is not None:
        hasil = cari_tombol_berteks(isi, awalan_label)
        if hasil is not None:
            return hasil
    return None


# ===================================================================== tes


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

    # Jam deadline dihormati
    pagi = storage.add_task("Deadline jam 6 pagi", hari_ini, important=True,
                            deadline_time="06:00")
    sore = datetime.combine(clock.today(), datetime.min.time()).replace(hour=17)
    ok(storage.is_urgent(pagi, sore), "jam 17:00, deadline 06:00 hari ini -> udah lewat, mendesak")

    besok = (clock.today() + timedelta(days=1)).isoformat()
    t_besok_malam = storage.add_task("Besok malam", besok, important=True, deadline_time="23:00")
    pagi_ini = datetime.combine(clock.today(), datetime.min.time()).replace(hour=8)
    ok(not storage.is_urgent(t_besok_malam, pagi_ini),
       "jam 08:00, deadline besok 23:00 (39 jam lagi) -> belum mendesak")

    # Tugas tanpa deadline_time nggak bikin error
    ok(storage.is_urgent({"deadline": hari_ini}) is True, "tanpa deadline_time -> tetap jalan")
    ok(storage.is_urgent({}) is False, "tanpa deadline sama sekali -> False, bukan crash")


def tes_data_basi():
    bagian("Data mood basi TIDAK dipakai buat nebak hari ini")
    from app.core import kalem_engine as ke
    import app.kalem_ml as ml
    from app.kalem_ml import fitur as F

    # User check-in 10 hari lalu, isinya capek banget, terus menghilang.
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

    # Morning Brief: nyapa, BUKAN ramal dari data basi
    p, day = ke.snapshot()
    brief = ke.build_morning_brief(p, day)
    ok(not brief.ready, "brief nggak meramal pas datanya basi")
    ok("balik lagi" in brief.forecast.lower(),
       f"brief-nya nyapa, bukan nakut-nakutin: {brief.forecast!r}")
    ok(brief.energy_level == 3, "energi default netral, bukan 1 dari catatan lama")

    # Kontrol: user yang check-in kemarin TIDAK dianggap basi
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
    import app.kalem_ml as ml
    from app.kalem_ml import fitur as F, riwayat

    storage_baru("kosong_")
    # Check-in cuma di hari 0, 5, 10 -- sisanya bolong.
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
    from app.kalem_ml import fitur as F, model_mood

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

    storage.DATA_FILE = b            # user lain, proses SAMA, tanpa reset
    rb = model_mood.ramal(F.bangun_fitur())
    tanda_b, id_b = model_mood._tanda, id(model_mood._model)

    ok(tanda_a != tanda_b, "sidik jari data beda -> kunci cache beda")
    ok(id_a != id_b, "model di-retrain buat user B")
    ok(rb.skor < 2.0, f"user B (mood 1) dapet skor dari datanya sendiri: {rb.skor:.2f}")
    ok(ra.skor > 4.0, f"user A (mood 5) tetap benar: {ra.skor:.2f}")


def tes_fungsi_murni():
    bagian("decide()/build_morning_brief() murni dari argumen")
    from app import clock
    import app.kalem_ml as ml
    from app.core import kalem_engine as ke

    storage_baru("murni_")
    pasang_logs(skor=1, n=12, energi=1, sos_idx=[0, 1, 2])   # storage: BERAT
    ml.reset_semua()
    profile = storage.get_profile()

    hasil = ke.decide(profile, ke.DayState())   # argumen: kosong/tenang
    ok(hasil.kind != "pre_escalate",
       f"day kosong -> kind={hasil.kind}, nggak keseret storage yang berat")

    logs_berat = [
        {"date": (clock.today() - timedelta(days=i)).isoformat(), "mood": "x", "score": 1,
         "energy": 1, "diary": "", "tags": [], "quick_tags": [],
         "ate_today": False, "rested_enough": False, "weekday": 0, "is_weekend": False}
        for i in range(12)
    ]
    storage_baru("murni2_")
    pasang_logs(skor=5, n=12, energi=5)          # storage: TENANG
    ml.reset_semua()
    profile = storage.get_profile()
    day_berat = ke.DayState(
        mood_logs=logs_berat,
        reset_events=[
            {"timestamp": "", "date": (clock.today() - timedelta(days=i)).isoformat(),
             "choice": "napas", "mood_score": None} for i in (0, 1, 2)
        ],
    )
    ok(ke.decide(profile, day_berat).kind == "pre_escalate",
       "day berat -> eskalasi, walau storage-nya tenang")


def tes_halaman_kebangun():
    bagian("Semua halaman kebangun")
    import app.kalem_ml as ml
    from app.views import (diary, favorites, home, inbox, med_setup, mood,
                           morning_brief, onboarding, reset, settings, tracker)

    storage_baru("ui_")
    pasang_logs(skor=4, n=30, energi=4)
    storage.add_task("Tugas contoh", storage.clock.today().isoformat(), important=True,
                     steps=[{"text": "langkah", "done": False}])
    ml.reset_semua()

    p = HalamanPalsu()
    for nama, modul in [
        ("home", home), ("tracker", tracker), ("mood", mood), ("diary", diary),
        ("reset", reset), ("med_setup", med_setup), ("favorites", favorites),
        ("settings", settings), ("morning_brief", morning_brief),
        ("inbox", inbox), ("onboarding", onboarding),
    ]:
        try:
            modul.build(p, lambda r: None)
            ok(True, nama)
        except Exception as exc:                       # noqa: BLE001
            ok(False, f"{nama}: {type(exc).__name__}: {exc}")


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
    bagian("Mode fokus ngunci halaman lain (kecuali jeda)")
    import app.main as main_mod
    from app import focus_session

    ok("reset" in main_mod.FOKUS_BOLEH,
       "halaman JEDA tetap boleh dibuka -- ngunci jalan keluar orang kewalahan itu bahaya")
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

    storage_baru("makan_")  # ini juga nge-reset offset hari & jam lewat reset_all_data()

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
        for _ in range(30):  # dorong lewat tengah malam, nggak peduli jam sekarang berapa
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
    from app.core import decomposer_logic as dl
    from app.kalem_ml import model_pecah

    storage_baru("pecah_")

    rec = [
        {"title": "Quiz Kalkulus 1", "description": "latihan soal integral bab 3",
         "steps": ["Baca catatan", "Kerjain 5 soal"], "source": "ai"},
        {"title": "Laporan bulanan", "description": "rekap penjualan",
         "steps": ["Kumpulin data", "Bikin grafik"], "source": "ai"},
    ]

    # --- pencocokan: yang mirip kena, yang nggak nyambung ditolak ---
    ok(model_pecah.cari("Quiz Kalkulus 1", "latihan soal integral bab 3", rec).ketemu,
       "judul+deskripsi sama persis -> kepungut")
    ok(model_pecah.cari("Quiz Kalkulus 1", "", rec).ketemu,
       "judul sama tapi deskripsi kosong -> TETAP kepungut "
       "(catatan lama yang deskripsinya panjang nggak boleh bikin skor jatuh)")
    ok(not model_pecah.cari("Masak nasi goreng", "buat makan malam", rec).ketemu,
       "tugas nggak nyambung -> DITOLAK, jangan asal pungut")
    ok(not model_pecah.cari("Quiz Matematika Diskrit", "kombinatorik", rec).ketemu,
       "quiz matkul LAIN -> ditolak (mirip dikit doang nggak cukup)")

    # --- deskripsi terstruktur: langkahnya dipakai apa adanya, nol API ---
    tugas = {"title": "Bikin proposal", "description": "Cari ide\nCari solusi\nTulis draft",
             "important": True, "kategori": "", "jumlah_unit": 0, "menit_est": 0}
    langkah, sumber = dl._langkah_lokal(tugas)
    ok(sumber == "manual", f"deskripsi per-baris -> jalur manual (dapet {sumber!r})")
    ok(langkah == ["Cari ide", "Cari solusi", "Tulis draft"],
       "langkahnya dipakai APA ADANYA, nggak dikirim ke AI buat dipecah lagi")

    # --- alur penuh: AI cuma kepanggil buat yang beneran baru ---
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

    # --- hasil AI ikut kesimpen buat dipungut lain kali ---
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
    """Paraphrase realistis (bukan variasi awalan) buat SATU niat yang sama:
    "kamar berantakan, nggak tau mulai dari mana". Beda dari uji retrieval
    yang cuma ngecek "ketemu apa nggak" -- ini negasiin WRONG retrieval
    secara eksplisit, termasuk ke entri dataset lain yang kata-katanya mirip
    ("kamar mandi") tapi identitas tugasnya beda. Target: wrong-retrieval
    0%, coverage boleh turun (fallback ke AI/template itu aman)."""
    bagian("Pecah Tugas: retrieval bahasa natural (paraphrase, bukan variasi awalan)")
    from app.kalem_ml import model_pecah

    bawaan = list(model_pecah._pola_bawaan())
    target = "Beresin kamar"

    # (query, wajib_ketemu) -- "wajib_ketemu" diukur lebih dulu lewat
    # model_pecah.cari() langsung (bukan ditebak), lihat riwayat percakapan.
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

    # Kontrol: kata "kamar" muncul, tapi identitas tugasnya BEDA (kamar mandi,
    # bukan kamar tidur) -- ini yang paling gampang ketuker kalau retrieval
    # cuma modal kata kunci, bukan kemiripan dokumen penuh.
    kamar_mandi = model_pecah.cari("kamar mandi gue kotor banget", records=bawaan)
    ok(not kamar_mandi.ketemu or kamar_mandi.dari_judul != target,
       f"'kamar mandi kotor' TIDAK nyasar ke {target!r} "
       f"(dapet: {'fallback' if not kamar_mandi.ketemu else kamar_mandi.dari_judul!r})")

    # Kontrol: query yang sama sekali nggak nyambung ke beres-beres kamar.
    tugas_lain = model_pecah.cari("bikin proposal buat ikut lomba hackathon", records=bawaan)
    ok(not tugas_lain.ketemu or tugas_lain.dari_judul != target,
       "query yang nggak nyambung sama sekali TIDAK nyasar ke 'Beresin kamar'")


def tes_fallback_ai_valid():
    """Kasus yang SENGAJA dibuat sulit buat retrieval lokal ("gue stuck
    banget sama skripsi" -- diverifikasi dulu skornya 0.43, jauh di bawah
    ambang 0.72). Yang diuji bukan cuma "AI menghasilkan output", tapi
    seluruh rantainya: confidence lokal rendah -> fallback ke AI beneran
    kejadian -> output AI dipakai -> source label bilang "ai" (bukan ngaku
    "lokal") -> hasilnya kesimpen dengan source="ai" (bukan "dataset")."""
    bagian("Pecah Tugas: fallback AI buat kasus yang lokal-nya nggak yakin")
    from unittest.mock import patch

    from app.core import ai_client, decomposer_logic as dl
    from app.kalem_ml import model_pecah

    storage_baru("fallback_ai_")

    judul = "gue stuck banget sama skripsi"
    # Pastiin dulu premisnya BENERAN: lokal nggak yakin (di bawah AMBANG_MIRIP).
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
    from app.kalem_ml import fitur as F

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

    # Sesudah dipencet, tampilan berikutnya jadi catatan BARU -- itu keputusan
    # yang beda (konteksnya udah berubah), bukan lanjutan yang lama.
    storage.record_decision_shown("next_action", "focus", f, "FOKUS 20 menit")
    ok(len(storage.get_decision_records()) == 2,
       "sesudah dipencet, tampilan berikutnya jadi catatan baru")

    ok(not storage.record_decision_acted("calm", "add_task"),
       "nandai keputusan yang nggak pernah ditampilin -> False, bukan bikin data palsu")
    ok(storage.record_decision_shown("", "focus", f) is None, "kind kosong -> nggak dicatat")


def tes_ml_kalem_tidak_kontaminasi():
    """Pastiin fitur yang dipakai buat TRAINING model_kalem itu snapshot
    DECISION TIME (pas keputusan ditampilin), bukan ikut kena update sama
    apa pun yang kejadian SESUDAHNYA (klik, atau tampilan ulang dengan
    kondisi yang udah beda). Kalau `fitur` diam-diam ketimpa data yang lebih
    baru, model bisa belajar dari sesuatu yang sebenernya cuma keliatan
    SESUDAH keputusan itu dibuat -- prediksi yang keliatan akurat padahal
    cuma ngintip hasilnya sendiri."""
    bagian("ML_KALEM: fitur decision-time TIDAK boleh ketimpa data outcome-time")
    from app.kalem_ml import fitur as F
    from app.kalem_ml import model_kalem

    storage_baru("kontaminasi_")

    fitur_awal = F.Fitur(
        nilai={"energi_terakhir": 1.0, "skor_3h": 2.0, "n_belum_selesai": 6.0},
        tanggal=storage.clock.today().isoformat(), catatan={},
    )
    storage.record_decision_shown("next_action", "focus", fitur_awal, "FOKUS 15 menit")

    # Simulasikan kondisi user BERUBAH di render berikutnya hari yang sama
    # (mis. tugas baru diselesain, energi kecatet ulang) SEBELUM diklik --
    # fitur yang kesimpen HARUS tetap yang pertama, bukan yang belakangan.
    fitur_belakangan = F.Fitur(
        nilai={"energi_terakhir": 6.0, "skor_3h": 5.0, "n_belum_selesai": 0.0},
        tanggal=storage.clock.today().isoformat(), catatan={},
    )
    storage.record_decision_shown("next_action", "focus", fitur_belakangan, "FOKUS 15 menit")
    tersimpan_sebelum_klik = storage.get_decision_records()[0]["fitur"]
    ok(tersimpan_sebelum_klik["energi_terakhir"] == 1.0,
       "tampilan ulang dengan kondisi yang UDAH BEDA tidak menimpa fitur decision-time "
       f"yang tercatat pertama kali (tetap energi_terakhir={tersimpan_sebelum_klik['energi_terakhir']})")

    # Klik terjadi SESUDAHNYA -- pastiin itu nggak diam-diam ngubah fitur juga.
    storage.record_decision_acted("next_action", "focus")
    tersimpan_sesudah_klik = storage.get_decision_records()[0]["fitur"]
    ok(tersimpan_sesudah_klik == tersimpan_sebelum_klik,
       "record_decision_acted() (outcome time) TIDAK mengubah field fitur (decision time) sama sekali")

    # Struktural: FEATURES model_kalem nggak boleh ada nama field yang
    # cuma kebaca SESUDAH keputusan dibuat (acted/n_tampil/acted_at, atau
    # started/completed andaikata nanti ditambah) -- kalau salah satu masuk
    # FEATURES, model bisa "mempredik'si dirinya sendiri" dari outcome-nya.
    field_outcome = {"acted", "acted_at", "n_tampil", "started", "started_at",
                     "completed", "completed_at"}
    bocor = field_outcome & set(model_kalem.FEATURES)
    ok(not bocor, f"model_kalem.FEATURES nggak nyerempet field outcome-only (dapet bocor: {bocor})")

    # Dokumentasi granularitas data SEKARANG: skema decision_records baru
    # nyatet shown (n_tampil/timestamp) & acted (klik) -- BELUM ada
    # started/completed. Kalau field itu ditambah nanti, test ini yang
    # pertama kali harus diperbarui buat mikirin ulang kontaminasinya.
    kolom_skema = set(storage.get_decision_records()[0].keys())
    ok({"started", "completed"} & kolom_skema == set(),
       "[KARAKTERISASI] skema decision_records saat ini cuma shown+acted -- "
       "started/completed belum ada, jadi belum ada risiko kontaminasi dari situ")


def tes_regresi_data_dan_tugas_berulang():
    """Bug yang mudah kambuh karena UI-nya menulis ke storage yang sama."""
    bagian("Diary, Reset, overdue, dan tugas berulang")
    from app import clock
    from app.core.reset_preferences import detect_distress

    storage_baru("regresi_baru_")

    # Diary/check-in adalah satu record harian; field care nggak boleh lenyap.
    storage.add_mood_log("lelah", 2, 2, ate_today=True, rested_enough=False)
    storage.add_mood_log("lelah", 2, 2, diary="Hari ini berat")
    log = storage.today_mood()
    ok(log["ate_today"] is True and log["rested_enough"] is False,
       "simpan Diary nggak menghapus jawaban makan/istirahat")

    # Banyak aktivitas dalam satu kunjungan lama tidak boleh jadi eskalasi.
    today = clock.today()
    logs = [{"date": today.isoformat(), "score": 1}]
    events_same_day = [{"date": today.isoformat(), "choice": "napas"} for _ in range(4)]
    ok(not detect_distress(events_same_day, logs).escalate,
       "4 event di hari sama bukan 4 hari distress")

    # Tugas sekali jalan yang lewat tetap masuk kandidat Beranda.
    yesterday = (today - timedelta(days=1)).isoformat()
    overdue = storage.add_task("Tugas kemarin", yesterday, steps=[{"text": "mulai", "done": False}])
    ok(any(t["id"] == overdue["id"] for t in storage.tasks_actionable_today()),
       "tugas terlambat tidak menghilang dari next action")

    # Checklist occurrence mingguan terisolasi dari minggu berikutnya.
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


def tes_langkah_tambahan_dan_ml_kalem():
    bagian("Langkah tambahan user & ML_KALEM")
    from app.core import decomposer_logic as dl
    from app.kalem_ml import model_kalem

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

    # Riwayat sintetis dipakai HANYA untuk mengetes gerbang/arah model,
    # bukan sebagai data produk. Energi rendah -> sering tidak dipencet;
    # energi tinggi -> sering dipencet.
    records = []
    for i in range(24):
        low = i < 12
        records.append({
            "kind": "next_action", "action_kind": "focus", "acted": not low,
            "n_tampil": 1,
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

    # Decoy ditambahin DULUAN dengan kesulitan lebih berat -- kalau ada kode
    # yang nyari ulang tugas lewat storage.tasks_actionable_today() dicocokin
    # ke JUDUL (bug lama), `next()` bakal kena tugas ini duluan karena dia
    # yang pertama nangkring di storage, walau bukan yang dipilih engine.
    storage.add_task(
        "Tugas kembar", today, important=True, difficulty_est=3,
        kategori="Rumah", jumlah_unit=99,
        steps=[{"text": "langkah decoy", "done": False}],
    )
    # Ini yang beneran dipilih pick_next_action(): kesulitan lebih rendah
    # menang di kuadran yang sama (lihat kalem_engine.pick_next_action).
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

    # Tugas SEKALI JALAN, judul sama, kesulitan lebih berat -- decoy.
    storage.add_task(
        "Tugas", today, important=True, difficulty_est=3,
        kategori="Organisasi", jumlah_unit=7,
        steps=[{"text": "langkah organisasi", "done": False}],
    )
    # Tugas BERULANG (harian), judul sama, kesulitan lebih rendah -> menang.
    # occurrence-nya dibentuk lewat storage.tasks_for()/tasks_actionable_today()
    # sebagai SALINAN task dict (bertanda _occurrence_date), bukan objek yang
    # sama persis -- ini yang mau dipastikan tetap ke-resolve dengan benar.
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

    # ID tugas HARUS tetap ID tugas dasarnya -- occurrence itu salinan
    # tampilan, bukan tugas baru yang beda identitas tiap hari.
    ulang = storage.tasks_actionable_today()
    dipilih = next((t for t in ulang if t.get("kategori") == "Kuliah"), None)
    ok(dipilih is not None and dipilih["id"] == tugas_berulang["id"]
       and dipilih.get("_occurrence_date") == today,
       "occurrence tugas berulang bawa id tugas dasar yang sama + _occurrence_date yang benar")
    focus_session.stop()


def tes_pecah_tugas_judul_kembar():
    """Rencana dan write-back harus tetap memakai ID, bukan judul tugas."""
    bagian("Pecah Tugas: judul kembar tidak saling menimpa")
    from app.core import decomposer_logic as dl

    storage_baru("pecah_kembar_")
    pertama = storage.add_task(
        "Belajar", storage.clock.today().isoformat(), description="Buka catatan A\nTandai rumus A",
    )
    kedua = storage.add_task(
        "Belajar", storage.clock.today().isoformat(), description="Buka catatan B\nTandai rumus B",
    )
    result = dl.plan_today([pertama, kedua], allow_ai=False)
    ok([s["text"] for s in result.task_steps[pertama["id"]]] == ["Buka catatan A", "Tandai rumus A"],
       "tugas judul kembar pertama mempertahankan langkahnya sendiri")
    ok([s["text"] for s in result.task_steps[kedua["id"]]] == ["Buka catatan B", "Tandai rumus B"],
       "tugas judul kembar kedua tidak tertimpa langkah tugas pertama")


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
        tes_langkah_tambahan_dan_ml_kalem,
        tes_fokus_pakai_decision_task,
        tes_fokus_pakai_decision_task_tugas_berulang,
        tes_pecah_tugas_judul_kembar,
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
