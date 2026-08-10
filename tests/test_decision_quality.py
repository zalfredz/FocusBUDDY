"""Scenario suite untuk decision quality, bukan sekadar fungsi tidak crash.

Jalankan:
    python tests/test_decision_quality.py

Setiap scenario punya keputusan yang bisa dinilai manusia. Jangan menambah
heuristik/model baru sebelum scenario ini tetap lulus atau diperbarui dengan
alasan produk yang eksplisit.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import clock
from app.core.decision_quality import assess_capacity
from app.core.kalem_engine import (
    DayState, decide, focus_minutes_for, pick_next_action, urgency_score,
)
from app.kalem_ml.model_overwhelm import Risiko


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  [OK] " if condition else "  [FAIL] ") + message)
    if not condition:
        FAILURES.append(message)


def task(
    title: str,
    *,
    deadline: str | None = None,
    important: bool = True,
    difficulty: int = 2,
    minutes: int = 30,
    done: bool = False,
    created: str = "2026-01-01T08:00:00",
    task_id: str | None = None,
    deadline_time: str = "",
) -> dict:
    return {
        "id": task_id or title,
        "title": title,
        "deadline": deadline or clock.today().isoformat(),
        "deadline_time": deadline_time,
        "important": important,
        "difficulty_est": difficulty,
        "menit_est": minutes,
        "created_at": created,
        "steps": [{"text": f"Mulai {title}", "done": done}],
    }


def scenario_pick_next_action() -> None:
    print("\n=== Kualitas pick_next_action ===")
    today = clock.today().isoformat()
    future = (clock.today() + timedelta(days=5)).isoformat()
    overdue = (clock.today() - timedelta(days=1)).isoformat()

    # Urgensi nyata harus menang atas tugas nyaman tetapi bisa ditunda.
    result = pick_next_action([
        task("Rapikan folder", deadline=future, difficulty=1),
        task("Kirim formulir hari ini", deadline=today, difficulty=3),
    ])
    check(result is not None and result[0]["title"] == "Kirim formulir hari ini",
          "deadline hari ini mengalahkan tugas mudah yang belum mendesak")

    # Saat urgensinya sama, pintu masuk termudah harus menang.
    result = pick_next_action([
        task("Laporan besar", deadline=today, difficulty=3),
        task("Balas email penting", deadline=today, difficulty=1),
    ])
    check(result is not None and result[0]["title"] == "Balas email penting",
          "di kuadran sama, tugas paling mudah dipilih lebih dulu")

    result = pick_next_action([
        task("Sudah selesai", deadline=today, difficulty=1, done=True),
        task("Masih perlu", deadline=today, difficulty=2),
    ])
    check(result is not None and result[0]["title"] == "Masih perlu",
          "tugas selesai tidak pernah direkomendasikan lagi")

    result = pick_next_action([
        task("Deadline kemarin", deadline=overdue, difficulty=2),
        task("Baca artikel", deadline=future, difficulty=1),
    ])
    check(result is not None and result[0]["title"] == "Deadline kemarin",
          "tugas terlambat tetap ditriage, bukan hilang")


def scenario_priority_and_reset() -> None:
    print("\n=== Prioritas safety dan Reset ===")
    profile = {"name": "Ari", "productive_hours": []}
    workload = task("Tugas penting", difficulty=1)

    # Kita menguji prioritas engine, bukan akurasi model overwhelm. Model
    # sendiri punya suite/data terpisah; di sini risiko disuntik eksplisit.
    with patch(
        "app.kalem_ml.model_overwhelm.nilai",
        return_value=Risiko(0.5, "waspada", "prior"),
    ):
        decision = decide(
            profile,
            DayState(
                tasks_today=[workload],
                mood_logs=[{"date": clock.today().isoformat(), "score": 2, "energy": 2}],
                reset_events=[{"date": clock.today().isoformat(), "choice": "napas"}],
            ),
            now=datetime.combine(clock.today(), datetime.min.time()).replace(hour=10),
        )
    check(decision.kind == "pre_escalate" and decision.action_kind == "reset",
          "setelah sinyal Reset/risk, jeda didahulukan daripada tugas")

    with patch(
        "app.kalem_ml.model_overwhelm.nilai",
        return_value=Risiko(0.0, "tenang", "prior"),
    ):
        decision = decide(
            profile,
            DayState(
                tasks_today=[workload],
                mood_logs=[{"date": clock.today().isoformat(), "score": 3, "energy": 1}],
            ),
            now=datetime.combine(clock.today(), datetime.min.time()).replace(hour=10),
        )
    check(decision.kind == "next_action" and decision.focus_minutes == 5,
          "sesudah kondisi tenang, next action kembali kecil saat energi rendah")


def scenario_capacity() -> None:
    print("\n=== Capacity-aware workload ===")
    assessment = assess_capacity([
        task("Proposal", minutes=120),
        task("Presentasi", minutes=100),
        task("Email", minutes=90),
    ], available_minutes=120)
    check(not assessment.fits and assessment.estimated_minutes == 310
          and assessment.overflow_minutes == 190,
          "310 menit pekerjaan dalam 120 menit dikenali sebagai overload 190 menit")

    uncertain = assess_capacity([
        task("Tugas terukur", minutes=30),
        task("Tugas belum diestimasi", minutes=0),
    ], available_minutes=120)
    check(uncertain.fits and uncertain.unknown_tasks == 1,
          "kapasitas melaporkan ketidakpastian, bukan menganggap tugas tanpa estimasi gratis")


def scenario_pick_next_action_agresif() -> None:
    """Matriks agresif: deadline x durasi x kesulitan x overdue.

    Tujuannya nyari KONFLIK ATURAN, bukan cuma nge-cek jalur yang udah pasti
    benar. Dua check terakhir SENGAJA didokumentasikan sebagai TEMUAN --
    perilaku asli yang terverifikasi, bukan yang seharusnya terjadi menurut
    asumsi siapa pun.
    """
    print("\n=== pick_next_action -- matriks agresif (deadline x durasi x kesulitan) ===")
    today = clock.today().isoformat()
    besok = (clock.today() + timedelta(days=5)).isoformat()
    kemarin = (clock.today() - timedelta(days=1)).isoformat()

    # Durasi TIDAK BOLEH ngalahin urgensi: 90 menit BESOK kalah dari
    # 15 menit HARI INI, walau "keliatan lebih cepat kelar".
    result = pick_next_action([
        task("A besar besok", deadline=besok, minutes=90, difficulty=2),
        task("B kecil hari ini", deadline=today, minutes=15, difficulty=2),
    ])
    check(result is not None and result[0]["title"] == "B kecil hari ini",
          "tugas 90 menit BESOK kalah dari tugas 15 menit HARI INI -- "
          "durasi nggak boleh ngalahin urgensi")

    # Overdue + lebih gampang menang telak atas hari-ini + lebih susah.
    result = pick_next_action([
        task("B kecil hari ini", deadline=today, minutes=15, difficulty=2),
        task("C overdue gampang", deadline=kemarin, minutes=30, difficulty=1),
    ])
    check(result is not None and result[0]["title"] == "C overdue gampang",
          "overdue + lebih gampang menang atas hari-ini + lebih susah")

    # Sebelum Phase 2, ini adalah karakterisasi bug: dua tugas yang sama-sama
    # urgent jatuh ke created_at. Sekarang overdue yang lebih lama harus
    # menang berdasarkan deadline nyata, walaupun dibuat belakangan.
    result = pick_next_action([
        task("B due 2 jam lagi", deadline=today, minutes=15, difficulty=2,
             created="2026-01-01T08:00:00", deadline_time="23:59"),
        task("C overdue 5 hari", deadline=(clock.today() - timedelta(days=5)).isoformat(),
             minutes=30, difficulty=2, created="2026-01-01T09:00:00", deadline_time="00:00"),
    ])
    check(result is not None and result[0]["title"] == "C overdue 5 hari",
          "overdue 5 hari mengalahkan deadline dekat walau dibuat belakangan")

    # --- Kalau available_minutes NGGAK dioper (default None), pick_next_action
    # tetap milih tugas ini -- BUKAN lagi karena fungsinya "nggak punya
    # parameter itu sama sekali" (sejak PHASE 1 dia punya), tapi karena
    # None secara sengaja berarti "nggak ada info waktu tersedia, jangan
    # ngefek ke apa pun". Lihat scenario_capacity_terhubung() buat kasus
    # PAS available_minutes BENERAN dioper.
    hasil = pick_next_action([task("Tugas 90 menit", deadline=today, minutes=90, difficulty=1)])
    check(hasil is not None and hasil[0]["title"] == "Tugas 90 menit",
          "tanpa available_minutes dioper (default None) -> tugas 90 menit tetap "
          "kepilih normal, capacity nggak ngefek kalau nggak ada datanya")

    # ...dan sesi yang BENERAN ditawarkan ke user tetap dibatesin
    # `focus_minutes_for(energy)` (5-30 menit dari level energi), independen
    # dari menit_est tugas -- lapisan mitigasi ini nggak berubah oleh PHASE 1.
    ditawarkan = focus_minutes_for(3)
    check(ditawarkan <= 20,
          f"...sesi yang BENERAN ditawarkan cuma {ditawarkan} menit (dari energi, "
          "bukan dari menit_est tugas) -- lapisan mitigasi lama, independen dari capacity")


def scenario_capacity_agresif() -> None:
    print("\n=== Capacity-aware -- tiga titik beban vs waktu tersedia ===")

    berat = assess_capacity([task("T1", minutes=240)], available_minutes=60)
    check(not berat.fits and berat.overflow_minutes == 180,
          "60 menit tersedia vs 240 menit beban -> overload 180 menit terdeteksi")

    lega = assess_capacity([task("T2", minutes=120)], available_minutes=180)
    check(lega.fits and lega.overflow_minutes == 0,
          "180 menit tersedia vs 120 menit beban -> muat, nggak overload")

    mepet = assess_capacity([task("T3", minutes=25)], available_minutes=30)
    check(mepet.fits and round(mepet.utilization, 2) == 0.83,
          "30 menit tersedia vs 25 menit beban -> muat MEPET (utilization ~83%), bukan overload")

    # --- [DIPERBAIKI PHASE 1] assess_capacity() BENAR ngedeteksi overload di
    # atas, dan sekarang DayState.available_minutes (kalau diisi pemanggil)
    # BENERAN nyampe ke pick_next_action() lewat decide() -- lihat
    # scenario_capacity_terhubung() buat bukti end-to-end-nya. assess_capacity()
    # sendiri TETAP nggak dipanggil langsung di dalam decide() -- yang
    # dipakai `pick_next_action._muat_kapasitas()`, satu fungsi kecil yang
    # manggil assess_capacity() per tugas, biar logikanya tetap satu sumber.
    check("available_minutes" in DayState().__dataclass_fields__,
          "DayState sekarang punya field available_minutes -- decide() punya jalur "
          "buat nerima 'waktu tersedia' (default None kalau nggak ada pemanggil yang ngisi)")


def scenario_capacity_terhubung() -> None:
    """PHASE 1 -- available_minutes beneran nyampe ke pick_next_action().

    Kasus A-F persis spesifikasi audit: A/B nunjukin tugas yang MUAT menang
    di kuadran+kesulitan yang sama, C mastiin tugas besar yang MASIH MUAT
    nggak salah ditolak, D mastiin `available_minutes=None` sama PERSIS
    kayak nggak dioper sama sekali (regresi-aman), E mastiin `0` DIBEDAIN
    dari `None` (bukan bug falsy-check), F mastiin satu-satunya tugas yang
    nggak muat TETEP ditawarin (bukan didiemin/dihilangin).
    """
    print("\n=== [PHASE 1] Capacity terhubung ke pick_next_action() ===")

    # --- A: available=60, A=90 vs B=30, "otherwise comparable" (kuadran & kesulitan sama) ---
    hasil = pick_next_action(
        [task("A besar", minutes=90, difficulty=2, task_id="a"),
         task("B kecil", minutes=30, difficulty=2, task_id="b")],
        available_minutes=60,
    )
    check(hasil is not None and hasil[0]["id"] == "b",
          "A: available=60, A=90 vs B=30 (kesulitan sama) -> B menang karena MUAT")

    # --- B: available=20, A=90 vs B=15 ---
    hasil = pick_next_action(
        [task("A besar", minutes=90, difficulty=2, task_id="a"),
         task("B kecil", minutes=15, difficulty=2, task_id="b")],
        available_minutes=20,
    )
    check(hasil is not None and hasil[0]["id"] == "b",
          "B: available=20, A=90 vs B=15 -> B menang karena MUAT")

    # --- C: available=120, A=90 (lebih gampang) vs B=30 -- A muat, jangan salah tolak ---
    hasil = pick_next_action(
        [task("A besar gampang", minutes=90, difficulty=1, task_id="a"),
         task("B kecil susah", minutes=30, difficulty=3, task_id="b")],
        available_minutes=120,
    )
    check(hasil is not None and hasil[0]["id"] == "a",
          "C: available=120, A=90(diff1) vs B=30(diff3) -- A MUAT (90<=120) jadi "
          "nggak ditolak salah, tie-break kesulitan normal yang menang (A)")

    # --- D: available_minutes=None HARUS sama persis kayak nggak dioper sama sekali ---
    tugas_d = [task("A besar", minutes=90, difficulty=3, task_id="a"),
               task("B kecil", minutes=15, difficulty=1, task_id="b")]
    default_lama = pick_next_action(tugas_d)
    eksplisit_none = pick_next_action(tugas_d, available_minutes=None)
    check(default_lama is not None and eksplisit_none is not None
          and default_lama[0]["id"] == eksplisit_none[0]["id"] == "b",
          "D: available_minutes=None eksplisit == nggak dioper sama sekali "
          "(dua-duanya jatuh ke tie-break kesulitan lama, B menang karena diff=1)")

    # --- E: available=0 HARUS beda dari None -- bukan falsy-check yang ke-skip ---
    hasil = pick_next_action(
        [task("Ada estimasi", minutes=10, difficulty=2, task_id="ada"),
         task("Tanpa estimasi", minutes=0, difficulty=2, task_id="tanpa")],
        available_minutes=0,
    )
    check(hasil is not None and hasil[0]["id"] == "tanpa",
          "E: available=0 -- tugas BER-estimasi (10 menit) dianggap TIDAK muat "
          "(0 diperlakukan beda dari None), tugas TANPA estimasi menang karena "
          "'nggak tau' bukan berarti 'nggak muat' (assess_capacity: unknown != overflow)")

    # --- F: satu-satunya tugas actionable nggak muat -- tetap ditawarin, bukan didiemin ---
    hasil = pick_next_action(
        [task("Satu-satunya tugas", minutes=90, difficulty=2, task_id="satu")],
        available_minutes=10,
    )
    check(hasil is not None and hasil[0]["id"] == "satu",
          "F: satu-satunya tugas actionable nggak muat (90 menit vs 10 tersedia) -- "
          "TETAP ditawarin, kontrak lama 'selalu ada next action kalau ada tugas' "
          "nggak boleh diam-diam berubah jadi 'kosongin kalau nggak muat'")


def scenario_urgency_ranking() -> None:
    """PHASE 2 -- deadline adalah sinyal berurutan, bukan boolean saja."""
    print("\n=== [PHASE 2] Urgency ranking dari deadline nyata ===")
    today = clock.today()
    now = datetime.combine(today, datetime.min.time()).replace(hour=12)

    overdue_5 = task(
        "Overdue 5 hari", deadline=(today - timedelta(days=5)).isoformat(),
        deadline_time="12:00", difficulty=2, created="2026-01-01T09:00:00",
    )
    due_2h = task(
        "Due 2 jam", deadline=today.isoformat(), deadline_time="14:00",
        difficulty=2, created="2026-01-01T08:00:00",
    )
    result = pick_next_action([due_2h, overdue_5], now=now)
    check(result is not None and result[0]["id"] == overdue_5["id"],
          "overdue 5 hari tidak diperlakukan sama dengan deadline 2 jam lagi")
    check(urgency_score(overdue_5, now) > urgency_score(due_2h, now),
          "skor urgensi overdue lebih besar dan dapat dijelaskan dari lama keterlambatan")

    overdue_1 = task("Overdue 1 hari", deadline=(today - timedelta(days=1)).isoformat(),
                     deadline_time="12:00", difficulty=2)
    due_today = task("Due malam ini", deadline=today.isoformat(), deadline_time="23:00", difficulty=2)
    result = pick_next_action([due_today, overdue_1], now=now)
    check(result is not None and result[0]["id"] == overdue_1["id"],
          "overdue 1 hari mengalahkan deadline hari ini")

    tomorrow = task("Deadline besok", deadline=(today + timedelta(days=1)).isoformat(),
                    deadline_time="13:00", difficulty=2)
    next_week = task("Deadline minggu depan", deadline=(today + timedelta(days=7)).isoformat(),
                     deadline_time="13:00", difficulty=2)
    result = pick_next_action([next_week, tomorrow], now=now)
    check(result is not None and result[0]["id"] == tomorrow["id"],
          "deadline besok mengalahkan deadline minggu depan dalam kuadran yang sama")

    important = task("Penting", deadline=(today + timedelta(days=3)).isoformat(), important=True, difficulty=3)
    non_important = task("Tidak penting", deadline=(today + timedelta(days=3)).isoformat(), important=False, difficulty=1)
    result = pick_next_action([non_important, important], now=now)
    check(result is not None and result[0]["id"] == important["id"],
          "tugas penting tetap menang atas tugas tidak penting saat urgensinya sebanding")

    urgent_large = task("Urgent besar", deadline=today.isoformat(), deadline_time="13:00",
                        minutes=90, difficulty=2)
    urgent_small = task("Urgent kecil", deadline=today.isoformat(), deadline_time="14:00",
                        minutes=15, difficulty=1)
    result = pick_next_action([urgent_small, urgent_large], available_minutes=20, now=now)
    check(result is not None and result[0]["id"] == urgent_large["id"],
          "kapasitas memperhitungkan ukuran, tapi tidak menghapus urgensi deadline yang lebih dekat")

    equal_old = task("Equal lama", deadline=today.isoformat(), deadline_time="18:00",
                     difficulty=2, created="2026-01-01T08:00:00")
    equal_new = task("Equal baru", deadline=today.isoformat(), deadline_time="18:00",
                     difficulty=2, created="2026-01-01T09:00:00")
    result = pick_next_action([equal_new, equal_old], now=now)
    check(result is not None and result[0]["id"] == equal_old["id"],
          "semua sinyal setara tetap memakai tie-break created_at yang deterministik")


def scenario_model_kalem_modifier() -> None:
    """Guardrail: model_kalem cuma boleh meringankan DURASI, nggak pernah
    ganti TUGAS yang kepilih. Risiko/model_kalem disuntik eksplisit -- yang
    diuji di sini perilaku `decide()`, bukan akurasi model_kalem sendiri
    (itu punya suite terpisah di tests/test_regresi.py)."""
    print("\n=== model_kalem cuma modifier durasi, bukan pemilih tugas (guardrail) ===")
    from app.kalem_ml.model_kalem import SinyalKalem

    profile = {"name": "Ari", "productive_hours": []}
    # Task A menang telak (kesulitan paling rendah) -- Task B cuma pembanding
    # buat mastiin dia TIDAK PERNAH kepilih gantiin Task A.
    tugas_a = task("Task A", difficulty=1, minutes=30, task_id="a")
    tugas_b = task("Task B", difficulty=3, minutes=30, task_id="b")
    day = DayState(
        tasks_today=[tugas_a, tugas_b],
        mood_logs=[{"date": clock.today().isoformat(), "score": 3, "energy": 6}],
    )
    now = datetime.combine(clock.today(), datetime.min.time()).replace(hour=10)

    with patch("app.kalem_ml.model_overwhelm.nilai", return_value=Risiko(0.0, "tenang", "prior")):
        # model_kalem BELUM siap (data belum cukup) -> nggak boleh ngubah apa-apa.
        with patch("app.kalem_ml.model_kalem.nilai",
                   return_value=SinyalKalem(skor=0.5, siap=False)):
            belum_aktif = decide(profile, day, now=now)
        check(belum_aktif.task is not None and belum_aktif.task["id"] == "a"
              and belum_aktif.focus_minutes == 30,
              "model_kalem BELUM siap -> Task A tetap kepilih, durasi 30 menit nggak disentuh")

        # model_kalem AKTIF & sinyal keterlibatan rendah -> BOLEH turunin
        # durasi, TAPI TIDAK BOLEH ganti tugas yang kepilih.
        with patch("app.kalem_ml.model_kalem.nilai",
                   return_value=SinyalKalem(skor=0.1, siap=True, n_latih=24, sumber="belajar")):
            aktif = decide(profile, day, now=now)
        check(aktif.task is not None and aktif.task["id"] == "a",
              "model_kalem AKTIF & 'perlu diringankan' TETAP nggak ngubah tugas -- "
              "masih Task A, bukan Task B")
        check(aktif.focus_minutes == 25,
              f"...durasi turun 30 -> {aktif.focus_minutes} menit (max(5, minutes-5)), "
              "sesuai kontrak 'cuma boleh meringankan'")


def scenario_reset_belum_meringankan() -> None:
    """[KARAKTERISASI] -- BUKAN test 'perilaku ideal', tapi baseline perilaku
    SEKARANG: riwayat Reset TIDAK membuat next-action berikutnya lebih
    ringan (task/step/durasi identik, dengan energi & mood ditahan konstan
    supaya perbandingannya bersih -- bukan ketuker sama efek energi yang
    memang SEHARUSNYA mengubah durasi).

    Kalau desain "lebih ringan setelah Reset" diimplementasikan nanti, test
    ini yang pertama kali harus diperbarui. Sampai saat itu, dia jadi
    penjaga: kalau `decide()` diubah dan diam-diam MULAI berbeda gara-gara
    reset_events, test ini bakal ribut duluan -- baik itu perubahan yang
    disengaja (perbarui test-nya) maupun nggak (itu regresi).
    """
    print("\n=== [KARAKTERISASI] Reset -> next action: belum ada mekanisme 'lebih ringan' ===")
    profile = {"name": "Ari", "productive_hours": []}
    tugas = task("Kerjakan laporan praktikum", difficulty=2, minutes=45, task_id="lapo")
    # Energi & mood DITAHAN KONSTAN di semua kondisi di bawah -- yang divariasikan
    # cuma reset_events, biar efeknya (atau bukti nggak-ada-efeknya) nggak
    # ketuker sama efek energi/mood yang memang seharusnya mengubah durasi.
    mood_logs = [{"date": clock.today().isoformat(), "score": 3, "energy": 4}]
    now = datetime.combine(clock.today(), datetime.min.time()).replace(hour=10)

    with patch("app.kalem_ml.model_overwhelm.nilai", return_value=Risiko(0.0, "tenang", "prior")):
        tanpa_reset = decide(
            profile, DayState(tasks_today=[tugas], mood_logs=mood_logs, reset_events=[]),
            now=now,
        )
        satu_reset = decide(
            profile,
            DayState(tasks_today=[tugas], mood_logs=mood_logs,
                     reset_events=[{"date": clock.today().isoformat(), "choice": "napas"}]),
            now=now,
        )
        riwayat_berat = [
            {"date": (clock.today() - timedelta(days=d)).isoformat(), "choice": "napas"}
            for d in range(5)
        ]
        reset_berat = decide(
            profile, DayState(tasks_today=[tugas], mood_logs=mood_logs, reset_events=riwayat_berat),
            now=now,
        )

    check(tanpa_reset.kind == "next_action" and tanpa_reset.task["id"] == "lapo",
          "baseline: tanpa riwayat Reset, next action normal ke tugas yang ada")

    check(satu_reset.task["id"] == tanpa_reset.task["id"]
          and satu_reset.step_text == tanpa_reset.step_text
          and satu_reset.focus_minutes == tanpa_reset.focus_minutes,
          "[KARAKTERISASI] 1x kunjungan Reset TIDAK mengubah task/step/durasi next action "
          f"sama sekali (tetap '{satu_reset.step_text}', {satu_reset.focus_minutes} menit)")

    check(reset_berat.task["id"] == tanpa_reset.task["id"]
          and reset_berat.step_text == tanpa_reset.step_text
          and reset_berat.focus_minutes == tanpa_reset.focus_minutes,
          "[KARAKTERISASI] BAHKAN 5x Reset dalam 5 hari terakhir tidak mengubah task/step/durasi "
          f"next action (tetap '{reset_berat.step_text}', {reset_berat.focus_minutes} menit) -- "
          "belum ada mekanisme yang membuat first action lebih kecil/ringan gara-gara riwayat Reset")


def scenario_energi_rendah_banyak_tugas() -> None:
    print("\n=== Energi rendah + banyak tugas ===")
    profile = {"name": "Ari", "productive_hours": []}
    banyak = [task(f"Tugas {i}", difficulty=(i % 3) + 1, task_id=str(i)) for i in range(5)]
    now = datetime.combine(clock.today(), datetime.min.time()).replace(hour=10)

    with patch("app.kalem_ml.model_overwhelm.nilai", return_value=Risiko(0.0, "tenang", "prior")):
        d = decide(
            profile,
            DayState(tasks_today=banyak,
                     mood_logs=[{"date": clock.today().isoformat(), "score": 3, "energy": 1}]),
            now=now,
        )
    check(d.kind == "next_action" and d.task["id"] == "0",
          "5 tugas actionable, energi 1 -> tetap milih yang paling gampang (difficulty=1), bukan bingung")
    check(d.focus_minutes == focus_minutes_for(1),
          f"durasi ikut energi terendah ({d.focus_minutes} menit), banyaknya tugas tidak membuat "
          "sesi yang ditawarkan lebih panjang")


def scenario_overwhelm_dan_overdue() -> None:
    print("\n=== High overwhelm + tugas overdue ===")
    profile = {"name": "Ari", "productive_hours": []}
    overdue = task("Laporan telat", deadline=(clock.today() - timedelta(days=3)).isoformat(), difficulty=1)
    now = datetime.combine(clock.today(), datetime.min.time()).replace(hour=10)

    with patch("app.kalem_ml.model_overwhelm.nilai", return_value=Risiko(0.7, "berat", "prior")):
        d = decide(
            profile,
            DayState(tasks_today=[overdue],
                     mood_logs=[{"date": clock.today().isoformat(), "score": 2, "energy": 2}]),
            now=now,
        )
    check(d.kind == "pre_escalate" and d.action_kind == "reset",
          "overwhelm 'berat' menang atas tugas overdue -- jeda didahulukan, bukan dipaksa "
          "ngerjain tugas telat cuma karena deadline-nya udah lewat")


def scenario_tidak_ada_tugas() -> None:
    print("\n=== Tidak ada tugas sama sekali ===")
    profile = {"name": "Ari", "productive_hours": []}
    now = datetime.combine(clock.today(), datetime.min.time()).replace(hour=10)

    with patch("app.kalem_ml.model_overwhelm.nilai", return_value=Risiko(0.0, "tenang", "prior")):
        d = decide(
            profile,
            DayState(tasks_today=[], mood_logs=[{"date": clock.today().isoformat(), "score": 4, "energy": 4}]),
            now=now,
        )
    check(d.kind == "calm" and d.task is None and d.action_kind == "add_task",
          "tidak ada tugas -> pesan tenang + ajakan nambah tugas, bukan error atau kartu kosong")


def main() -> int:
    clock.reset_offset()
    scenario_pick_next_action()
    scenario_priority_and_reset()
    scenario_capacity()
    scenario_pick_next_action_agresif()
    scenario_urgency_ranking()
    scenario_capacity_agresif()
    scenario_capacity_terhubung()
    scenario_model_kalem_modifier()
    scenario_reset_belum_meringankan()
    scenario_energi_rendah_banyak_tugas()
    scenario_overwhelm_dan_overdue()
    scenario_tidak_ada_tugas()
    print("\n" + "=" * 60)
    if FAILURES:
        print(f"GAGAL: {len(FAILURES)}")
        return 1
    print("SEMUA SCENARIO KUALITAS LULUS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
