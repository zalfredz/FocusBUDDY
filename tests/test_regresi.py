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
    ok(buddy.MOOD_ORDER[0] == "sedih", f"paling kiri = sedih (dapet {buddy.MOOD_ORDER[0]})")
    ok(buddy.MOOD_ORDER[-1] == "semangat", f"paling kanan = semangat (dapet {buddy.MOOD_ORDER[-1]})")
    ok(skor == sorted(skor), f"skornya naik monoton: {skor}")
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
