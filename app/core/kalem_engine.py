"""Kalem decision engine -- "satu otak" yang dipanggil semua halaman.

Tujuannya bikin 5 fitur MVP terasa nyambung, bukan numpuk fitur terpisah.
Semua halaman baca dari fungsi yang sama, cuma pakai bagian output yang beda:

    Home    -> pesan prioritas + next-action card + ekspresi Kalem
    Tracker -> durasi default sesi fokus (dari level energi)
    Reset   -> urutan opsi calming (via reset_preferences)
    Mood    -> ekspresi default Kalem sebelum user check-in

Sengaja rule-based, bukan ML: urutan prioritasnya harus bisa dijelasin ke
juri dalam satu kalimat, dan nggak butuh data latih.

Modul ini nggak impor flet -- biar gampang dites tanpa bikin UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from app import clock
from app.core.medication_model import check_status, missed_streak

# --- Ambang deteksi "soft escalation" ---
# Sengaja LEBIH LONGGAR dari eskalasi keras di halaman Reset (3x/7 hari +
# mood <= 2.0). Di sini cuma buat Kalem nyapa duluan dengan lembut, bukan
# nyodorin rujukan profesional. Akses ke halaman Reset tetap selalu terbuka.
PRE_ESCALATION_WINDOW_DAYS = 3
PRE_ESCALATION_SOS_COUNT = 2
PRE_ESCALATION_MOOD = 3.0

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
    """Snapshot data harian yang dibaca engine."""

    tasks_today: list[dict] = field(default_factory=list)
    mood_logs: list[dict] = field(default_factory=list)
    reset_events: list[dict] = field(default_factory=list)
    medication: Optional[dict] = None
    energy_level: Optional[int] = None


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


def pick_next_action(tasks: list[dict]) -> Optional[tuple[dict, int, str]]:
    """Pilih satu tugas + satu langkah pertama buat dikerjain sekarang.

    Urutannya: kuadran paling mendesak duluan, lalu di dalam kuadran itu
    ambil yang `difficulty_est`-nya paling rendah. Jadi tetap ngerjain hal
    yang penting, tapi mulai dari pintu masuk paling gampang -- ini yang
    bikin tugas berat nggak kelihatan mustahil buat dimulai.

    Return (task, index langkah, teks langkah) atau None.
    """
    from app import storage  # lokal: hindari circular import saat modul dimuat

    pending = [t for t in tasks if not storage.task_is_done(t)]
    if not pending:
        return None

    def sort_key(task: dict):
        quadrant = storage.quadrant_of(task)
        rank = QUADRANT_PRIORITY.index(quadrant) if quadrant in QUADRANT_PRIORITY else 99
        return (rank, task.get("difficulty_est", 2), task.get("created_at", ""))

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

    avg = sum(scores) / len(scores)
    if avg <= 1.5:
        return "sedih"
    if avg <= 2.5:
        return "lelah"
    if avg <= 3.5:
        return "cemas"
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

    # --- 2. Pola SOS berulang + mood rendah (pre-escalation yang lembut) ---
    pre = detect_pre_escalation(day.reset_events, day.mood_logs)
    if pre:
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
    found = pick_next_action(day.tasks_today)
    if found:
        task, step_index, step_text = found
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


def detect_pre_escalation(reset_events: list[dict], mood_logs: list[dict]) -> bool:
    """Sinyal lembut: SOS berulang + mood rendah dalam 3 hari terakhir.

    Bukan buat nge-gate tombol apa pun -- cuma bikin Kalem nyapa duluan.
    Eskalasi yang beneran ngarahin ke profesional ada di halaman Reset
    dengan ambang yang lebih ketat.
    """
    recent_sos = _recent(reset_events, PRE_ESCALATION_WINDOW_DAYS)
    if len(recent_sos) < PRE_ESCALATION_SOS_COUNT:
        return False

    scores = [
        log["score"]
        for log in _recent(mood_logs, PRE_ESCALATION_WINDOW_DAYS)
        if log.get("score") is not None
    ]
    if not scores:
        return False
    return sum(scores) / len(scores) <= PRE_ESCALATION_MOOD


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
    """
    from app import storage

    profile = storage.get_profile()
    day = DayState(
        tasks_today=storage.tasks_today(),
        mood_logs=storage.get_mood_logs(),
        reset_events=storage.get_reset_events(),
        medication=storage.get_medication(),
        # Level energi hari ini kalau udah dikunci (dari Morning Brief atau
        # koreksi manual di Tracker). None = biar engine nebak dari mood log.
        energy_level=storage.today_energy(),
    )
    return profile, day


def decide_now() -> KalemDecision:
    """Jalan pintas: snapshot + decide dalam satu panggilan."""
    profile, day = snapshot()
    return decide(profile, day)


# ------------------------------------------------------- morning brief
# Membalik arah interaksi: Kalem nyapa duluan tiap pagi dengan ramalan
# konkret, sebelum user check-in apa pun. Dua mesin prediksi yang dipakai
# (_predict_today & predict_workload) UDAH ADA -- yang berubah cuma kapan
# hasilnya keluar dan bentuknya: dari kalimat info pasif jadi aksi default
# yang langsung nyetel energi & durasi sesi hari itu.


# Beban kerja yang diramal -> level energi default yang disaranin.
WORKLOAD_TO_ENERGY = {"rendah": 2, "sedang": 4, "tinggi": 5}


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

    Jujur soal ketidaktahuan: kalau catatan mood masih di bawah
    MIN_LOGS_FOR_PATTERN, `ready=False` dan pesannya ngaku belum bisa
    meramal -- konsisten sama mood_model.analyse() yang nggak pernah
    ngarang pola dari data yang belum cukup.
    """
    from app import storage
    from app.core.energy_predictor import (
        MISSED_MED_THRESHOLD,
        predict_workload,
        sleep_hours_for,
    )
    from app.core.mood_model import (
        MIN_LOGS_FOR_PATTERN,
        _predict_today,
        checkin_streak,
        neglect_streak,
    )

    now = now or clock.now()
    name = profile.get("name") or "kamu"
    logs = [log for log in day.mood_logs if log.get("score") is not None]
    favorites = storage.get_favorites()
    encouragement = favorites.get("penyemangat", "").strip()

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

    # --- Data belum cukup: tetap nyapa, tapi ngaku belum bisa meramal ---
    if len(logs) < MIN_LOGS_FOR_PATTERN:
        return MorningBrief(
            ready=False,
            greeting=greeting,
            forecast=(
                f"Kalem belum cukup data buat meramal hari kamu "
                f"({len(logs)}/{MIN_LOGS_FOR_PATTERN} catatan)."
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

    # --- Ramalan beneran ---
    predicted_score = _predict_today(logs)
    sleep_hours = sleep_hours_for(profile.get("sleep_condition", ""))
    neglect_days = neglect_streak(day.mood_logs)
    recent_energy = logs[0].get("energy") or 3

    prediction = predict_workload(
        sleep_hours=sleep_hours,
        mood_score=int(round(predicted_score)) if predicted_score else 3,
        energy_level=recent_energy,
        # Pakai streak yang SAMA kayak halaman Mood. Dulu di sini nggak
        # dikirim sama sekali (default 0) sementara Mood ngirim angka lain,
        # jadi dua halaman bisa ngasih vonis beban beda di hari yang sama.
        streak=checkin_streak(day.mood_logs),
        neglect_days=neglect_days,
        # Nggak absen = dianggap nggak minum. Ini yang bikin "belakangan
        # kok berat ya" punya penjelasan, bukan misteri.
        missed_med_days=missed_streak(day.medication),
    )

    energy_level = WORKLOAD_TO_ENERGY.get(prediction.workload_label, 3)
    # Burnout ngalahin ramalan beban kerja: kalau kebaca burnout, jangan
    # nyaranin hari yang padat walaupun modelnya bilang "tinggi".
    if prediction.burnout_risk:
        energy_level = min(energy_level, 2)

    # Kalau brief-nya kebuka pas jam yang user sendiri bilang paling capek,
    # ekspektasinya diturunin satu tingkat -- ini beda dari "jam produktif"
    # di onboarding (itu titik tertinggi, ini titik terendah).
    tired_now = storage.in_tired_window(now)
    if tired_now:
        energy_level = max(1, energy_level - 1)

    # --- Alasan: kenapa Kalem mikir gitu (transparan, bukan kotak hitam) ---
    reasons: list[str] = []
    if predicted_score is not None:
        weekday_name = _WEEKDAY_NAMES[clock.today().weekday()]
        if predicted_score <= 2.5:
            reasons.append(f"{weekday_name} biasanya berat buat kamu")
        elif predicted_score >= 4:
            reasons.append(f"{weekday_name} biasanya lumayan buat kamu")
    if sleep_hours < 5.5:
        reasons.append("pola tidur kamu lagi berantakan")
    if neglect_days >= 2:
        reasons.append(f"{neglect_days} hari terakhir makan/istirahat kelewat")
    if recent_energy <= 2:
        reasons.append("energi terakhir kamu rendah")
    if tired_now:
        reasons.append("ini jam yang kamu bilang biasanya paling capek")
    missed_med = missed_streak(day.medication)
    if missed_med >= MISSED_MED_THRESHOLD:
        # Ditulis netral: fakta yang Kalem tau, bukan tuduhan.
        reasons.append(f"obat kamu belum keabsen {missed_med} hari terakhir")

    if prediction.workload_label == "rendah" or prediction.burnout_risk:
        forecast = "Hari ini kemungkinan bakal berat."
        mood = "lelah"
    elif prediction.workload_label == "tinggi":
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
        burnout_risk=prediction.burnout_risk,
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
