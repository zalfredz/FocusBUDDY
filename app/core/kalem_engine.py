"""Kalem decision engine -- "satu otak" yang dipanggil semua halaman.

Tujuannya bikin 5 fitur MVP terasa nyambung, bukan numpuk fitur terpisah.
Semua halaman baca dari fungsi yang sama, cuma pakai bagian output yang beda:

    Home    -> pesan prioritas + next-action card + ekspresi Kalem
    Tracker -> durasi default sesi fokus (dari level energi)
    Reset   -> urutan opsi calming (via kalem_ml.model_penenang)
    Mood    -> ekspresi default Kalem sebelum user check-in

URUTAN PRIORITASNYA rule-based (harus bisa dijelasin ke juri dalam satu
kalimat), tapi ISI SETIAP KEPUTUSAN sekarang lewat `kalem_ml` dulu, baru
dirender jadi kalimat:

    "pola berat kebaca?"    -> kalem_ml.model_overwhelm  (dulu 2-syarat rule)
    "beban kerja hari ini?" -> kalem_ml.model_energi      (dulu predict_workload langsung)
    "mood hari ini gimana?" -> kalem_ml.model_mood        (dulu rata-rata mentah)

Ketiganya sendiri punya prior rule-based buat hari pertama (belum ada data
buat dipelajari) dan pelan-pelan ganti ke versi yang belajar dari histori
user begitu datanya cukup -- lihat docstring masing-masing modul.

Modul ini nggak impor flet -- biar gampang dites tanpa bikin UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from app import clock
from app.core.medication_model import check_status, missed_streak

# Jam paling awal Kalem boleh nanya soal obat.
MED_NUDGE_HOUR = 7

# Level energi (1-6) -> (menit fokus, menit istirahat).
# Inilah yang bikin "Adaptive Focus Timer" beneran adaptif: energi rendah
# otomatis nawarin sesi lebih pendek, bukan 25 menit standar Pomodoro.
ENERGY_BLOCKS = {
    1: (5, 3),
    2: (10, 5),
    3: (15, 5),
    4: (20, 5),
    5: (25, 5),
    6: (30, 8),
}

# Jam produktif sekarang tinggal di storage (`PRODUCTIVE_PRESETS` buat
# preset onboarding, `profile["productive_hours"]` buat rentang yang diatur
# sendiri di Settings). Peta statis yang dulu ada di sini udah dibuang biar
# nggak ada dua sumber kebenaran yang bisa beda.

# Urutan kuadran Eisenhower dari yang paling mendesak.
QUADRANT_PRIORITY = ["lakukan", "delegasikan", "jadwalkan", "nanti"]


@dataclass
class KalemDecision:
    """Satu pesan prioritas tertinggi -- bukan numpuk semua sekaligus."""

    kind: str                       # "med" | "pre_escalate" | "next_action" | "calm"
    message: str
    mood: str                       # nama aset ekspresi Kalem
    detail: str = ""
    action_label: str = ""
    action_kind: str = ""           # "med_taken" | "reset" | "focus" | "add_task"
    task: Optional[dict] = None
    step_text: str = ""
    step_index: int = 0
    focus_minutes: int = 15


@dataclass
class DayState:
    """Snapshot SEMUA data yang dibaca engine -- termasuk lapisan ML.

    Sengaja lengkap: `decide()` dan `build_morning_brief()` harus jadi fungsi
    murni dari `(profile, day)`. Dulu nggak gitu -- lapisan ML-nya (lewat
    `kalem_ml.fitur.bangun_fitur()`) diam-diam baca `storage` lagi, jadi
    ngasih `day` buatan (pola yang jelas didukung dataclass ini) nggak
    ngefek ke separuh keputusannya. Yang kelihatan pure padahal nggak itu
    jebakan paling gampang bikin test bohong.

    Empat field terakhir ditambahin buat nutup celah itu: `bangun_fitur()`
    butuh gambaran yang lebih luas dari sekadar "hari ini".
    """

    tasks_today: list[dict] = field(default_factory=list)
    mood_logs: list[dict] = field(default_factory=list)
    reset_events: list[dict] = field(default_factory=list)
    medication: Optional[dict] = None
    energy_level: Optional[int] = None
    # Menit kerja yang BENERAN tersedia buat keputusan saat ini -- BUKAN
    # total menit tugas, BUKAN durasi sesi fokus, BUKAN energi. None berarti
    # app nggak punya sumber data yang jujur buat ini (lihat `snapshot()` --
    # SENGAJA nggak pernah nebak angka ini dari productive_hours atau
    # sumber lain yang sebenernya ngukur hal beda). Cuma keisi kalau ada
    # pemanggil yang eksplisit ngasih (mis. SettingDemo lewat `run_demo()`).
    available_minutes: Optional[int] = None
    # --- dipakai lapisan fitur (kalem_ml), bukan sama rule di modul ini ---
    all_tasks: list[dict] = field(default_factory=list)   # buat rasio selesai & umur tugas
    favorites: dict = field(default_factory=dict)
    focus_records: list[dict] = field(default_factory=list)
    inbox_count: int = 0
    decision_records: list[dict] = field(default_factory=list)


# --------------------------------------------------------------- helpers


def focus_minutes_for(energy_level: int) -> int:
    """Durasi sesi fokus yang disaranin buat level energi ini."""
    focus, _ = ENERGY_BLOCKS.get(energy_level, ENERGY_BLOCKS[3])
    return focus


def break_minutes_for(energy_level: int) -> int:
    _, rest = ENERGY_BLOCKS.get(energy_level, ENERGY_BLOCKS[3])
    return rest


def focus_reason(energy_level: int) -> str:
    """Kenapa durasinya segitu -- ditampilkan di bawah timer."""
    if energy_level <= 2:
        return "Disesuaikan karena energi kamu lagi rendah."
    if energy_level >= 5:
        return "Energi kamu lagi bagus, jadi sesinya boleh lebih panjang."
    return "Durasi standar buat energi sedang."


def in_productive_window(profile: dict, now: Optional[datetime] = None) -> Optional[bool]:
    """None kalau user nggak nentuin jam produktif (jangan nebak-nebak).

    Sumbernya `profile["productive_hours"]` -- rentang jam yang bisa diatur
    sendiri di Settings, dan boleh lebih dari satu (mis. pagi + malam).
    Preset lama dari onboarding udah diterjemahin ke bentuk ini pas load.
    """
    from app import storage

    return storage.in_productive_hours(profile, (now or clock.now()).hour)


def _recent(items: list[dict], days: int, today: Optional[date] = None) -> list[dict]:
    today = today or clock.today()
    out = []
    for item in items:
        try:
            when = date.fromisoformat(item["date"])
        except (KeyError, ValueError):
            continue
        if (today - when).days < days:
            out.append(item)
    return out


def _muat_kapasitas(task: dict, available_minutes: Optional[int]) -> bool:
    """Tugas ini muat di waktu yang tersedia? `None` = nggak ada info waktu
    tersedia -> selalu dianggap muat (nggak ngefek ke urutan sama sekali,
    biar perilaku lama TETAP SAMA kalau nggak ada yang ngasih angka ini).

    Dipakai `assess_capacity()` yang udah ada, bukan bikin perbandingan
    baru -- satu sumber kebenaran soal "muat" itu apa. Konsekuensinya ikut
    kebawa: tugas TANPA `menit_est` (nggak pernah diperkirakan) dianggap
    MUAT, bukan didiskualifikasi cuma karena datanya nggak ada.
    """
    if available_minutes is None:
        return True
    from app.core.decision_quality import assess_capacity

    return assess_capacity([task], available_minutes).fits


def urgency_score(task: dict, now: Optional[datetime] = None) -> int:
    """Skor urgensi rule-based yang bisa dijelaskan dari deadline nyata.

    Nilai lebih besar berarti perlu dilihat lebih dulu *di dalam kuadran yang
    sama*. Deadline terlewat selalu berada di atas deadline mendatang; di
    masing-masing kelompok, semakin lama terlambat atau semakin dekat batas
    waktunya, semakin besar skornya. Tugas tanpa deadline tetap netral (0).

    Kuadran Eisenhower tetap menentukan prioritas utama. Kapasitas dan
    kesulitan hanya tie-break setelah urgensi, jadi tugas sangat mendesak
    tidak hilang hanya karena estimasinya besar.
    """
    from app import storage

    batas = storage.deadline_at(task)
    if batas is None:
        return 0
    now = now or clock.now()
    remaining_minutes = int((batas - now).total_seconds() // 60)
    if remaining_minutes <= 0:
        return 3_000_000 + abs(remaining_minutes)
    if remaining_minutes <= 24 * 60:
        return 2_000_000 - remaining_minutes
    # Tetap bedakan deadline besok dan minggu depan untuk kuadran
    # "jadwalkan", tanpa membuat angka negatif bagi deadline yang jauh.
    return max(1, 1_000_000 - remaining_minutes)


def pick_next_action(
    tasks: list[dict], available_minutes: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Optional[tuple[dict, int, str]]:
    """Pilih satu tugas + satu langkah pertama buat dikerjain sekarang.

    Urutannya: kuadran paling mendesak duluan, lalu deadline paling dekat
    (atau yang paling lama overdue), baru tugas yang MUAT di
    `available_minutes`, kesulitan paling rendah, dan waktu dibuat. Kuadran
    tetap yang paling nentuin. Capacity membantu memilih dua kandidat yang
    urgensinya sebanding, tetapi tidak menghapus urgensi nyata.

    `available_minutes=None` (default) = urutan PERSIS kayak sebelum ada
    parameter ini -- capacity nggak ngefek sama sekali kalau nggak ada yang
    ngasih angkanya. Tugas yang nggak muat TETAP bisa kepilih kalau dia
    satu-satunya (atau semua pilihan sama-sama nggak muat) -- fungsi ini
    milih PRIORITAS, bukan nyaring/ngilangin tugas.

    Return (task, index langkah, teks langkah) atau None.
    """
    from app import storage  # lokal: hindari circular import saat modul dimuat

    pending = [t for t in tasks if not storage.task_is_done(t)]
    if not pending:
        return None

    def sort_key(task: dict):
        quadrant = storage.quadrant_of(task, now=now)
        rank = QUADRANT_PRIORITY.index(quadrant) if quadrant in QUADRANT_PRIORITY else 99
        muat = 0 if _muat_kapasitas(task, available_minutes) else 1
        return (
            rank,
            -urgency_score(task, now=now),
            muat,
            task.get("difficulty_est", 2),
            task.get("created_at", ""),
        )

    pending.sort(key=sort_key)
    chosen = pending[0]

    for i, step in enumerate(chosen.get("steps", [])):
        if not step.get("done"):
            return chosen, i, step.get("text", chosen["title"])

    # Tugas tanpa langkah: pakai judulnya sendiri sebagai langkah pertama.
    return chosen, 0, chosen["title"]


def predicted_mood(mood_logs: list[dict], default: str = "tenang") -> str:
    """Ekspresi Kalem dari histori 2-3 hari terakhir.

    Bikin Kalem bisa kelihatan lelah/cemas duluan sebelum user check-in
    manual -- app-nya kelihatan "merhatiin", bukan cuma nunggu diisi.
    """
    recent = _recent(mood_logs, 3)
    if not recent:
        return default

    scores = [log["score"] for log in recent if log.get("score") is not None]
    if not scores:
        return recent[0].get("mood", default)

    # Ambang ini HARUS ngikutin buddy.MOOD_SCORE (cemas=1, sedih=2, lelah=3,
    # tenang=4, semangat=5) -- dua tempat nyimpen pemetaan yang sama, jangan
    # sampai keduanya diedit sendiri-sendiri.
    avg = sum(scores) / len(scores)
    if avg <= 1.5:
        return "cemas"
    if avg <= 2.5:
        return "sedih"
    if avg <= 3.5:
        return "lelah"
    if avg <= 4.5:
        return "tenang"
    return "semangat"


# --------------------------------------------------------------- engine


def decide(
    profile: dict,
    day: DayState,
    now: Optional[datetime] = None,
) -> KalemDecision:
    """Urutan cek prioritas -- yang pertama kena, itu yang ditampilkan."""
    now = now or clock.now()
    name = profile.get("name") or "kamu"
    mood = predicted_mood(day.mood_logs)
    energy = day.energy_level or _energy_from_logs(day.mood_logs)
    minutes = focus_minutes_for(energy)

    # --- 1. Obat belum diabsen hari ini ---
    med_status = check_status(day.medication)
    # pills_remaining <= 0: stoknya udah fisik habis, jangan nawarin "udah
    # minum" lagi -- itu bakal nyatet absen palsu. Banner "stok habis" di
    # Home yang ambil alih dari sini.
    if med_status.active and med_status.pills_remaining > 0 and now.hour >= MED_NUDGE_HOUR:
        taken_today = (day.medication or {}).get("last_taken") == clock.today().isoformat()
        if not taken_today:
            return KalemDecision(
                kind="med",
                message=f"Udah minum {med_status.name} hari ini?",
                detail="Kalau udah, pencet aja -- stoknya Kalem yang hitung.",
                mood=mood,
                action_label="Udah minum",
                action_kind="med_taken",
                focus_minutes=minutes,
            )

    # --- 2. Pola berat kebaca (pre-escalation yang lembut) ---
    # Dulu rule 2-syarat (SOS>=2/3hari DAN mood<=3.0) yang ditulis di sini
    # langsung. Sekarang lewat `model_overwhelm`: sama-sama mulai dari prior
    # rule-based (malah lebih kaya -- ikut mempertimbangkan tidur, obat, beban
    # tugas), dan begitu ada >=10 hari ber-label dia beralih ke model yang
    # belajar dari pola SOS user sendiri. Threshold-nya SENGAJA lebih longgar
    # dari eskalasi keras di halaman Reset (yang itu 3x/7hari + mood<=2.0) --
    # di sini cuma buat Kalem nyapa duluan dengan lembut, bukan nyodorin
    # rujukan profesional. Akses ke halaman Reset tetap selalu terbuka.
    from app.kalem_ml import fitur as kfitur
    from app.kalem_ml import model_overwhelm

    fitur_sekarang = kfitur.bangun_fitur(now, day=day, profil=profile)
    risiko = model_overwhelm.nilai(fitur_sekarang)
    if risiko.perlu_diringankan:
        return KalemDecision(
            kind="pre_escalate",
            message="Beberapa hari ini kelihatannya berat ya.",
            detail="Nggak harus produktif dulu. Mau berhenti sebentar sama Kalem?",
            mood="cemas",
            action_label="Ambil jeda",
            action_kind="reset",
            focus_minutes=minutes,
        )

    # --- 3. Next action dari tugas hari ini ---
    found = pick_next_action(
        day.tasks_today, available_minutes=day.available_minutes, now=now,
    )
    if found:
        task, step_index, step_text = found
        # ML_KALEM hanya boleh menurunkan tuntutan setelah punya cukup label
        # fokus lokal. Ia tidak boleh mengubah urutan safety atau memilih
        # tugas lain, sehingga fallback tetap keputusan rule-based yang jelas.
        from app.kalem_ml import model_kalem

        engagement = model_kalem.nilai(fitur_sekarang, records=day.decision_records)
        if engagement.perlu_diringankan:
            minutes = max(5, minutes - 5)
        gentle = in_productive_window(profile, now) is False
        message = (
            "Kalau lagi nggak di jam terbaik kamu, satu langkah kecil aja udah cukup."
            if gentle
            else "Satu hal ini dulu aja."
        )
        return KalemDecision(
            kind="next_action",
            message=message,
            detail=task["title"],
            mood=mood,
            action_label=f"FOKUS {minutes} menit",
            action_kind="focus",
            task=task,
            step_text=step_text,
            step_index=step_index,
            focus_minutes=minutes,
        )

    # --- 4. Nggak ada tugas: pesan tenang ---
    return KalemDecision(
        kind="calm",
        message=f"Nggak ada tugas hari ini, {name}. Nikmati aja.",
        detail="Istirahat juga termasuk progress.",
        mood=mood,
        action_label="Tambah tugas",
        action_kind="add_task",
        focus_minutes=minutes,
    )


def _energy_from_logs(mood_logs: list[dict]) -> int:
    today_iso = clock.today().isoformat()
    for log in mood_logs:
        if log.get("date") == today_iso and log.get("energy"):
            return int(log["energy"])
    if mood_logs and mood_logs[0].get("energy"):
        return int(mood_logs[0]["energy"])
    return 3


def snapshot() -> tuple[dict, DayState]:
    """Ambil profil + DayState terkini dari storage.

    Dipakai halaman-halaman biar nggak masing-masing nyusun state sendiri.
    INI SATU-SATUNYA tempat engine nyentuh storage -- sesudah ini semuanya
    jalan dari `day` yang dioper, termasuk lapisan ML-nya.
    """
    from app import storage

    profile = storage.get_profile()
    day = DayState(
        tasks_today=storage.tasks_actionable_today(),
        mood_logs=storage.get_mood_logs(),
        reset_events=storage.get_reset_events(),
        medication=storage.get_medication(),
        all_tasks=storage.get_tasks(),
        favorites=storage.get_favorites(),
        focus_records=storage.get_focus_records(),
        inbox_count=len(storage.get_inbox()),
        decision_records=storage.get_decision_records(),
        # Level energi hari ini kalau udah dikunci (dari Morning Brief atau
        # koreksi manual di Tracker). None = biar engine nebak dari mood log.
        energy_level=storage.today_energy(),
    )
    return profile, day


# ------------------------------------------------------- morning brief
# Membalik arah interaksi: Kalem nyapa duluan tiap pagi dengan ramalan
# konkret, sebelum user check-in apa pun. Mesin prediksinya dari
# `kalem_ml.model_mood` + `kalem_ml.model_energi` -- yang berubah dari versi
# lama cuma kapan hasilnya keluar dan bentuknya: dari kalimat info pasif
# jadi aksi default yang langsung nyetel energi & durasi sesi hari itu.
#
# (Peta beban->energi dulu ada duplikatnya di sini -- `WORKLOAD_TO_ENERGY`,
# sama persis kayak `model_energi.BEBAN_KE_ENERGI`. Dihapus, satu sumber aja.)


@dataclass
class MorningBrief:
    ready: bool                 # False = data belum cukup buat meramal
    greeting: str
    forecast: str               # ramalan hari ini, bahasa manusia
    plan: str                   # apa yang Kalem siapin
    mood: str                   # ekspresi Kalem
    energy_level: int           # yang bakal di-set kalau user bilang "sesuai"
    focus_minutes: int
    reasons: list[str] = field(default_factory=list)   # dasar ramalannya
    task_count: int = 0
    burnout_risk: bool = False
    encouragement: str = ""     # kalimat penyemangat user sendiri
    # Premium: narasi yang nyambungin pola berminggu-minggu, mis. "3 Selasa
    # terakhir kamu selalu drop". Kosong di free tier.
    long_pattern: str = ""


def build_morning_brief(
    profile: dict,
    day: DayState,
    now: Optional[datetime] = None,
) -> MorningBrief:
    """Susun ramalan pagi dari pola user sendiri.

    Jujur soal ketidaktahuan: kalau catatan mood masih di bawah ambang
    `model_mood.MIN_POLA`, `ready=False` dan pesannya ngaku belum bisa
    meramal -- konsisten sama mood_model.analyse() yang nggak pernah
    ngarang pola dari data yang belum cukup.

    Ramalannya sendiri sekarang lewat kalem_ml: `model_mood.ramal()` buat
    skor mood hari ini, `model_energi.nilai()` buat beban kerja + level
    energi (dia yang sekarang ngurus koreksi burnout & jam-capek, bukan
    fungsi ini lagi -- lihat catatan di bawah).
    """
    from app import storage
    from app.core.energy_predictor import MISSED_MED_THRESHOLD
    from app.kalem_ml import fitur as kfitur
    from app.kalem_ml import model_energi, model_mood

    now = now or clock.now()
    name = profile.get("name") or "kamu"
    logs = [log for log in day.mood_logs if log.get("score") is not None]
    encouragement = day.favorites.get("penyemangat", "").strip()

    hour = now.hour
    if hour < 11:
        greeting = f"Pagi, {name}!"
    elif hour < 15:
        greeting = f"Siang, {name}!"
    elif hour < 19:
        greeting = f"Sore, {name}!"
    else:
        greeting = f"Malam, {name}!"

    task_count = len([t for t in day.tasks_today if not _task_done(t)])

    f = kfitur.bangun_fitur(now, day=day, profil=profile)
    ramalan = model_mood.ramal(f)

    # --- Lama nggak muncul: SAPA, jangan ramal dari data basi ---
    #
    # Ini yang njaga "capek jangan tervalidasi terus-terusan". Kalau catatan
    # terakhir user isinya berat lalu dia menghilang seminggu, meramal dari
    # situ artinya nyuruh dia pelan-pelan berdasarkan perasaan minggu lalu --
    # dan itu bisa bikin makin nggak jalan.
    #
    # Absen NGGAK dianggap sinyal buruk maupun baik. Bisa lupa, bisa lagi
    # berat beneran, dan dua-duanya nggak pantes ditebak-tebak. Jadi Kalem
    # berhenti meramal, nyapa apa adanya, dan minta satu check-in baru.
    if f["data_mood_basi"]:
        jarak = int(f["hari_sejak_checkin"])
        return MorningBrief(
            ready=False,
            greeting=greeting,
            forecast=f"Udah {jarak} hari nggak ketemu. Seneng kamu balik lagi.",
            plan=(
                "Aku sengaja nggak nebak-nebak hari kamu dari catatan lama — "
                "itu udah lewat. Check-in bentar yuk, biar aku mulai dari "
                "kondisi kamu yang sekarang."
            ),
            mood="tenang",
            energy_level=3,
            focus_minutes=focus_minutes_for(3),
            reasons=[],
            task_count=task_count,
            encouragement=encouragement,
        )

    # --- Data belum cukup: tetap nyapa, tapi ngaku belum bisa meramal ---
    if not ramalan.siap:
        return MorningBrief(
            ready=False,
            greeting=greeting,
            forecast=(
                f"Kalem belum cukup data buat meramal hari kamu "
                f"({ramalan.n_data}/{model_mood.MIN_POLA} catatan)."
            ),
            plan=(
                "Cerita dikit di check-in hari ini biar makin kebaca ke depannya. "
                "Sementara ini aku pakai setelan tengah dulu."
            ),
            mood="tenang",
            energy_level=3,
            focus_minutes=focus_minutes_for(3),
            reasons=[],
            task_count=task_count,
            encouragement=encouragement,
        )

    # --- Ramalan beneran: model dulu, baru dirender jadi kalimat ---
    predicted_score = ramalan.skor
    saran = model_energi.nilai(f, skor_mood=predicted_score)

    # `saran.level_energi` UDAH final -- model_energi sendiri yang nurunin
    # buat burnout & jam-capek (pakai `f["di_jam_capek"]`, sinyal yang sama
    # kayak `tired_now` di bawah). Jangan dikoreksi ulang di sini, nanti
    # ke-double.
    energy_level = saran.level_energi
    tired_now = bool(f["di_jam_capek"])

    # --- Alasan: kenapa Kalem mikir gitu (transparan, bukan kotak hitam) ---
    # Arah spesifik ("berat"/"lumayan buat kamu") butuh perbandingan ke hari
    # ini, jadi tetap dirakit di sini -- tapi angkanya semua dari `f`
    # (lapisan fitur bersama), bukan dihitung ulang lewat jalur lain.
    reasons: list[str] = []
    weekday_name = _WEEKDAY_NAMES[clock.today().weekday()]
    if predicted_score <= 2.5:
        reasons.append(f"{weekday_name} biasanya berat buat kamu")
    elif predicted_score >= 4:
        reasons.append(f"{weekday_name} biasanya lumayan buat kamu")
    if f["tidur_jam"] < 5.5:
        reasons.append("pola tidur kamu lagi berantakan")
    if f["streak_abai"] >= 2:
        reasons.append(f"{int(f['streak_abai'])} hari terakhir makan/istirahat kelewat")
    if f["energi_terakhir"] <= 2:
        reasons.append("energi terakhir kamu rendah")
    if tired_now:
        reasons.append("ini jam yang kamu bilang biasanya paling capek")
    if f["obat_kelewat"] >= MISSED_MED_THRESHOLD:
        # Ditulis netral: fakta yang Kalem tau, bukan tuduhan.
        reasons.append(f"obat kamu belum keabsen {int(f['obat_kelewat'])} hari terakhir")

    if saran.label == "rendah" or saran.burnout:
        forecast = "Hari ini kemungkinan bakal berat."
        mood = "lelah"
    elif saran.label == "tinggi":
        forecast = "Hari ini kemungkinan lagi enak-enaknya."
        mood = "semangat"
    else:
        forecast = "Hari ini kemungkinan biasa aja."
        mood = "tenang"

    minutes = focus_minutes_for(energy_level)
    if energy_level <= 2:
        plan = (
            f"Aku udah susunin: ambil yang paling ringan aja, sesi fokus {minutes} menit."
        )
    elif energy_level >= 5:
        plan = (
            f"Boleh ambil yang agak berat hari ini, sesi fokus {minutes} menit."
        )
    else:
        plan = f"Aku setel sesi fokus {minutes} menit dulu -- santai tapi jalan."

    if in_productive_window(profile, now) is False:
        plan += " Ini juga lagi di luar jam terbaik kamu, jadi santai aja."

    return MorningBrief(
        ready=True,
        greeting=greeting,
        forecast=forecast,
        plan=plan,
        mood=mood,
        energy_level=energy_level,
        focus_minutes=minutes,
        reasons=reasons,
        task_count=task_count,
        burnout_risk=saran.burnout,
        encouragement=encouragement,
        # Premium: narasi lintas minggu. Free tier tetap dapat ramalan
        # harian penuh di atas -- yang dikunci kedalamannya, bukan fungsinya.
        long_pattern=long_range_pattern(logs) if storage.is_premium() else "",
    )


_WEEKDAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

# Minimal berapa minggu data sebelum berani ngomongin pola lintas-minggu.
LONG_PATTERN_MIN_WEEKS = 3


def long_range_pattern(logs: list[dict], today: Optional[date] = None) -> str:
    """Narasi pola lintas MINGGU -- ini isi premium yang sebenernya.

    Beda dari ramalan harian: yang ini butuh histori panjang, jadi cuma
    numpuk kalau user beneran stay. Itu yang bikin nggak bisa ditiru
    dengan buka ChatGPT sekali.

    Return "" kalau datanya belum cukup -- jangan ngarang pola dari 2
    minggu doang, itu ngerusak kepercayaan yang susah dibangun lagi.
    """
    today = today or clock.today()
    weekday = today.weekday()

    same_day = []
    for log in logs:
        if log.get("score") is None:
            continue
        try:
            when = date.fromisoformat(log["date"])
        except (KeyError, ValueError):
            continue
        if when.weekday() == weekday and when != today:
            same_day.append((when, log["score"]))

    if len(same_day) < LONG_PATTERN_MIN_WEEKS:
        return ""

    same_day.sort(key=lambda pair: pair[0], reverse=True)
    recent = same_day[:4]
    scores = [s for _, s in recent]
    name = _WEEKDAY_NAMES[weekday]

    others = [
        log["score"]
        for log in logs
        if log.get("score") is not None
        and date.fromisoformat(log["date"]).weekday() != weekday
    ]
    if not others:
        return ""

    avg_day = sum(scores) / len(scores)
    avg_other = sum(others) / len(others)
    gap = avg_day - avg_other

    if gap <= -0.8:
        return (
            f"{len(recent)} {name} terakhir mood kamu konsisten lebih rendah "
            f"({avg_day:.1f} vs {avg_other:.1f} di hari lain). Kalau ada yang "
            f"bisa digeser dari {name}, mungkin worth dicoba."
        )
    if gap >= 0.8:
        return (
            f"{len(recent)} {name} terakhir mood kamu konsisten lebih bagus "
            f"({avg_day:.1f} vs {avg_other:.1f}). Hari yang pas buat naruh "
            "yang berat-berat."
        )
    return (
        f"Dari {len(recent)} {name} terakhir, mood kamu di hari ini relatif "
        "stabil — nggak ada pola khusus yang kebaca."
    )


def _task_done(task: dict) -> bool:
    from app import storage

    return storage.task_is_done(task)


def morning_brief_now() -> MorningBrief:
    profile, day = snapshot()
    return build_morning_brief(profile, day)
