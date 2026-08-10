"""Persistensi FocusBuddy (cache sesi server + database Supabase).

Schema v3 memisahkan dua lapisan yang dipakai Kalem decision engine:

- **Profil statis** -- hasil onboarding + menu Favorite. Jarang berubah.
- **DayState harian** -- energi, mood, tugas, absen obat, riwayat SOS.
  Berubah tiap hari/sesi.

Setelah login, cache server dipisah per ``user_id`` dan sesi browser, lalu
setiap perubahan disinkronkan ke row Supabase milik user tersebut. UI tetap
memakai API storage lama agar decision engine tidak perlu tahu detail cloud.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from app import clock, session_scope

DATA_DIR = Path.home() / ".focusbuddy"
DATA_FILE = DATA_DIR / "data.json"
BACKUP_FILE = DATA_DIR / "data.json.bak"
SCHEMA_VERSION = 3

_CLOUD_SAVE_HOOK: Optional[Callable[[dict[str, Any]], None]] = None
_SESSION_STORAGE_KEY = "focusbuddy.storage.v1"


@dataclass
class _StorageBinding:
    data_dir: Path
    data_file: Path
    backup_file: Path
    cloud_save_hook: Optional[Callable[[dict[str, Any]], None]] = None


def _session_binding() -> Optional[_StorageBinding]:
    store = session_scope.current_store()
    if store is None:
        return None
    value = store.get(_SESSION_STORAGE_KEY)
    return value if isinstance(value, _StorageBinding) else None


def _paths() -> tuple[Path, Path, Path]:
    binding = _session_binding()
    if binding is not None:
        return binding.data_dir, binding.data_file, binding.backup_file
    # Fallback ini dipakai script CLI dan regression test di luar Flet.
    return DATA_DIR, DATA_FILE, BACKUP_FILE


def current_data_file() -> Path:
    """Lokasi cache milik sesi aktif (berguna untuk startup/sinkronisasi)."""
    return _paths()[1]


def configure_user_storage(user_id: str, cache_root: Optional[Path] = None) -> None:
    """Arahkan cache ke folder user + sesi browser yang terautentikasi.

    Folder sesi yang unik mencegah dua tab akun yang sama menulis temporary
    file bersamaan. Supabase tetap menjadi salinan persisten lintas sesi.
    """
    global DATA_DIR, DATA_FILE, BACKUP_FILE
    safe_id = "".join(c for c in str(user_id) if c.isalnum() or c in "-_")
    if not safe_id:
        raise ValueError("user_id tidak valid")
    session_id = "".join(
        c for c in session_scope.current_session_id() if c.isalnum() or c in "-_"
    )
    if session_id:
        root = cache_root or Path(
            os.getenv(
                "FOCUSBUDDY_CACHE_DIR",
                str(Path(tempfile.gettempdir()) / "focusbuddy-web-cache"),
            )
        )
        data_dir = root / safe_id / session_id
        session_scope.set_value(
            _SESSION_STORAGE_KEY,
            _StorageBinding(
                data_dir=data_dir,
                data_file=data_dir / "data.json",
                backup_file=data_dir / "data.json.bak",
            ),
        )
        return

    # Kompatibilitas script/testing tanpa Flet context.
    DATA_DIR = Path.home() / ".focusbuddy" / "users" / safe_id
    DATA_FILE = DATA_DIR / "data.json"
    BACKUP_FILE = DATA_DIR / "data.json.bak"


def set_cloud_save_hook(hook: Optional[Callable[[dict[str, Any]], None]]) -> None:
    """Pasang callback non-blocking sesudah penulisan lokal berhasil."""
    global _CLOUD_SAVE_HOOK
    binding = _session_binding()
    if binding is not None:
        binding.cloud_save_hook = hook
        return
    _CLOUD_SAVE_HOOK = hook


def clear_user_storage() -> None:
    """Lepas binding sesi saat logout; tidak memengaruhi browser lain."""
    session_scope.remove_value(_SESSION_STORAGE_KEY)


def _cloud_save_hook() -> Optional[Callable[[dict[str, Any]], None]]:
    binding = _session_binding()
    return binding.cloud_save_hook if binding is not None else _CLOUD_SAVE_HOOK

# Pilihan onboarding -- dipakai juga sama halaman onboarding buat render opsi.
STATUS_OPTIONS = {
    "mahasiswa": "Mahasiswa / pelajar",
    "kerja": "Kerja kantoran",
    "freelance": "Freelance / remote",
    "lainnya": "Lainnya",
}

PRODUCTIVE_TIME_OPTIONS = {
    "pagi": "Pagi (06.00-11.00)",
    "siang": "Siang (11.00-16.00)",
    "malam": "Malam (19.00-00.00)",
    "nggak_tentu": "Nggak tentu",
}

# Preset di atas -> rentang jam beneran. Dipakai buat nerjemahin jawaban
# onboarding yang cepat jadi `productive_hours` yang bisa diatur halus di
# Settings. None = "nggak tentu", artinya jangan nebak-nebak.
PRODUCTIVE_PRESETS: dict[str, Optional[tuple[int, int]]] = {
    "pagi": (6, 11),
    "siang": (11, 16),
    "malam": (19, 24),
    "nggak_tentu": None,
}

# Jam produktif disimpan sebagai list rentang [mulai, selesai] dalam jam 0-30.
# Kenapa bisa lewat 24: biar rentang yang nyeberang tengah malam kayak
# 20.00-01.00 cukup ditulis [20, 25] -- satu rentang utuh, bukan dipecah dua
# potong yang bikin bingung pas diedit.
HOUR_MIN, HOUR_MAX = 0, 30

SLEEP_OPTIONS = {
    "cukup": "Cukup teratur",
    "begadang": "Sering begadang",
    "susah_tidur": "Susah tidur (insomnia)",
    "berantakan": "Berantakan banget",
}

# Berapa banyak pemicu kewalahan yang boleh dipilih. Dinaikin dari 2: orang
# jarang cuma punya satu sumber kewalahan, dan mbatesin di 2 maksa user
# ngebuang konteks yang sebenernya kepakai buat nyusun halaman jeda.
MAX_TRIGGERS = 4

# Status pekerjaan boleh lebih dari satu -- "mahasiswa sambil kerja" itu
# kondisi yang umum banget, dan maksa milih satu bikin datanya bohong.
MAX_STATUS = 3

MEDICATION_OPTIONS = {
    "ya": "Iya, rutin",
    "tidak": "Nggak",
    "nggak_tau": "Belum yakin",
}

TRIGGER_OPTIONS = {
    "tugas_numpuk": "Tugas numpuk",
    "deadline": "Deadline mepet",
    "sosial": "Situasi sosial",
    "kurang_tidur": "Kurang tidur",
    "mulai_susah": "Susah mulai (padahal tau harus)",
    "gagal_fokus": "Gampang kedistract",
}

# Aturan main: field cuma boleh nambah kalau ADA fitur yang makainya.
# Kolom "dipakai di" bukan dokumentasi doang -- itu syarat masuk.
#
#   musik      -> opsi calming di Reset
#   snack      -> ditawarin di halaman jeda pas kewalahan (aksi nol usaha)
#   hobi       -> saran micro-task 60 detik di Reset
#   tempat     -> saran pindah suasana di Reset
#   penyemangat-> dikutip balik di Reset & Morning Brief
#   warna      -> aksen kartu Kalem punya user
#   orang      -> ditawarin pas eskalasi SOS berulang
#   gerak      -> saran micro-task versi gerak badan
#   jam_capek  -> Kalem nurunin ekspektasi di jam itu + input Morning Brief
FAVORITE_FIELDS = {
    "musik": "Musik / genre yang nenangin",
    "snack": "Comfort food / minuman favorit",
    "hobi": "Hobi santai kamu",
    "tempat": "Tempat yang bikin nyaman",
    "penyemangat": "Kalimat penyemangat versi kamu sendiri",
    "warna": "Warna favorit",
    "orang": "Orang yang biasa jadi tempat cerita",
    "gerak": "Gerak / olahraga ringan favorit",
    "jam_capek": "Jam kamu biasanya paling capek",
}

# Field yang UI-nya bukan teks bebas.
FAVORITE_COLORS = {
    "sage": ("Hijau sage", "#8FBCA0"),
    "biru": ("Biru langit", "#A9C6DE"),
    "peach": ("Peach", "#F3B88B"),
    "lavender": ("Lavender", "#B8AEDB"),
    "terracotta": ("Terracotta", "#D97B66"),
}

FAVORITE_TIRED_HOURS = {
    "pagi": ("Pagi (06-11)", (6, 11)),
    "siang": ("Siang (11-16)", (11, 16)),
    "sore": ("Sore (16-19)", (16, 19)),
    "malam": ("Malam (19-24)", (19, 24)),
}


def _default_profile() -> dict[str, Any]:
    return {
        "name": "",
        "onboarded": False,
        "age_range": "",
        # List, bukan string: "mahasiswa sambil kerja" itu satu orang.
        "status": [],
        # Preset cepat dari onboarding. Tetap disimpan sebagai jejak jawaban
        # awal; yang dipakai engine `productive_hours` di bawah.
        "productive_time": "",
        # Rentang jam produktif yang bisa diatur halus di Settings.
        # [[6, 11], [20, 25]] = pagi 06-11 DAN malam 20.00-01.00.
        "productive_hours": [],
        "sleep_condition": "",
        "on_medication": "",
        "overwhelm_triggers": [],
        # Pemicu kewalahan yang diketik sendiri user (di luar TRIGGER_OPTIONS).
        "custom_triggers": [],
        # True kalau user milih "lagi nggak pengen jawab" -- sisanya default netral.
        "skipped_detail": False,
    }


def _default_state() -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "profile": _default_profile(),
        "favorites": {key: "" for key in FAVORITE_FIELDS},
        "tasks": [],
        "mood_logs": [],
        "reset_events": [],
        "medication": None,
        # Quick capture: tulisan mentah yang belum jadi tugas.
        "inbox": [],
        # Tanggal terakhir Morning Brief ditampilkan -- biar cuma sekali
        # sehari, buka app kedua kali langsung ke Home.
        "last_brief_date": "",
        # Level energi yang berlaku hari ini (dari brief atau koreksi manual
        # di Tracker). {"date": ISO, "level": 1-6}
        "today_energy": {"date": "", "level": 0},
        # Status langganan. Di build demo di-toggle manual lewat tombol SUBS
        # di header Home; di produksi nanti diisi hasil verifikasi pembayaran.
        "subscription": {"is_premium": False},
        # Pemakaian harian fitur berkuota (free tier). {"date": ISO, "<fitur>": n}
        "usage": {"date": ""},
        # Sesi fokus yang beneran kelar -- bahan buat rata-rata kecepatan
        # personal di kalem_ml/model_durasi. {kategori, jumlah_unit, menit,
        # energi, date}
        "focus_records": [],
        # Hasil Pecah Tugas yang sukses -- bahan retrieval di
        # kalem_ml/model_pecah, biar tugas mirip nggak perlu manggil AI lagi.
        # {title, description, steps, source, date}
        "decompose_records": [],
        # "Kalem nampilin pesan X, user mencet apa nggak" -- SATU-SATUNYA
        # label objektif buat ngelatih pemilihan pesan (calon ML_KALEM).
        # {id, date, kind, action_kind, n_tampil, acted, fitur}
        "decision_records": [],
        # Tanggal terakhir app dibuka. Dipakai buat ngitung berapa hari user
        # menghilang -- lihat `hari_sejak_checkin()`.
        "last_open_date": "",
        # Khusus testing: geseran hari & jam buat tombol dev di Home.
        # Di pemakaian normal dua-duanya selalu 0.
        "dev": {"day_offset": 0, "hour_offset": 0},
    }


def _migrate(state: dict[str, Any]) -> dict[str, Any]:
    """Bawa state lama (schema 1/2) ke bentuk sekarang tanpa buang data."""
    if state.get("schema") == SCHEMA_VERSION:
        return state

    fresh = _default_state()

    # Profil: pertahankan nama & status onboarded yang sudah ada.
    old_profile = state.get("profile", {})
    fresh["profile"]["name"] = old_profile.get("name", "")
    fresh["profile"]["onboarded"] = old_profile.get("onboarded", False)
    for key in ("age_range", "status", "productive_time", "productive_hours",
                "sleep_condition", "on_medication", "custom_triggers", "skipped_detail"):
        if key in old_profile:
            fresh["profile"][key] = old_profile[key]
    fresh["profile"]["overwhelm_triggers"] = old_profile.get("overwhelm_triggers", [])

    fresh["favorites"].update(state.get("favorites", {}))

    for old_task in state.get("tasks", []):
        fresh["tasks"].append(
            {
                "id": old_task.get("id", str(uuid.uuid4())),
                "title": old_task.get("title", "Tugas"),
                "deadline": old_task.get("deadline", clock.today().isoformat()),
                # `urgent` lama sengaja NGGAK dibawa: sekarang dihitung dari
                # deadline lewat is_urgent(). Jam deadline diisi kosong buat
                # tugas lama -- artinya "akhir hari", perilaku yang paling
                # deket sama maksud aslinya.
                "deadline_time": old_task.get("deadline_time", ""),
                "important": old_task.get("important", True),
                "difficulty_est": old_task.get("difficulty_est", 2),
                "steps": old_task.get("steps", []),
                "created_at": old_task.get("created_at", clock.now().isoformat()),
            }
        )

    for old_log in state.get("mood_logs", []):
        fresh["mood_logs"].append(
            {
                "date": old_log.get("date", clock.today().isoformat()),
                "mood": old_log.get("mood", "tenang"),
                "score": old_log.get("score", 4),
                "energy": old_log.get("energy", old_log.get("focus", 3)),
                "diary": old_log.get("diary", ""),
                "tags": old_log.get("tags", []),
                "quick_tags": old_log.get("quick_tags", []),
                "ate_today": old_log.get("ate_today"),
                "rested_enough": old_log.get("rested_enough"),
                "weekday": old_log.get("weekday"),
                "is_weekend": old_log.get("is_weekend"),
            }
        )

    fresh["reset_events"] = state.get("reset_events", [])
    fresh["inbox"] = state.get("inbox", [])
    fresh["last_brief_date"] = state.get("last_brief_date", "")
    fresh["today_energy"] = state.get("today_energy", {"date": "", "level": 0})
    fresh["dev"] = state.get("dev", {"day_offset": 0, "hour_offset": 0})

    med = state.get("medication")
    if med:
        med.setdefault("take_log", [])
        med.setdefault("last_taken", "")
        fresh["medication"] = med

    return fresh


def _normalise_profile(profile: dict[str, Any]) -> bool:
    """Rapikan bentuk field profil yang tipenya pernah berubah.

    Backfill key di `load_state()` cuma nambahin key yang HILANG -- dia nggak
    nolong kalau key-nya udah ada tapi tipenya beda (mis. `status` dulu string,
    sekarang list). Return True kalau ada yang diubah, biar state-nya disimpan.
    """
    changed = False

    # status: string tunggal -> list. Profil lama isinya "mahasiswa".
    status = profile.get("status")
    if isinstance(status, str):
        profile["status"] = [status] if status else []
        changed = True
    elif not isinstance(status, list):
        profile["status"] = []
        changed = True

    # productive_hours: kalau masih kosong tapi user udah pernah milih preset
    # di onboarding, terjemahin presetnya. Jadi user lama langsung punya
    # rentang jam yang bisa diedit, bukan halaman kosong.
    hours = profile.get("productive_hours")
    if not isinstance(hours, list):
        hours = []
        changed = True
    if not hours:
        # `productive_time` cuma BENIH sekali pakai dari onboarding. Begitu
        # rentangnya pernah ditulis (lewat save_profile/set_productive_hours)
        # benihnya dikosongin -- kalau nggak, user yang sengaja ngosongin
        # semua rentang bakal dapet presetnya balik lagi tiap buka app.
        preset = PRODUCTIVE_PRESETS.get(profile.get("productive_time", ""))
        if preset:
            hours = [[preset[0], preset[1]]]
            changed = True
    # Buang rentang yang bentuknya rusak, jangan sampai bikin engine meledak.
    clean: list[list[int]] = []
    for entry in hours:
        try:
            start, end = int(entry[0]), int(entry[1])
        except (TypeError, ValueError, IndexError, KeyError):
            changed = True
            continue
        if HOUR_MIN <= start < end <= HOUR_MAX:
            clean.append([start, end])
        else:
            changed = True
    if clean != hours:
        changed = True
    profile["productive_hours"] = clean

    if not isinstance(profile.get("custom_triggers"), list):
        profile["custom_triggers"] = []
        changed = True
    if not isinstance(profile.get("overwhelm_triggers"), list):
        profile["overwhelm_triggers"] = []
        changed = True

    return changed


def all_triggers(profile: Optional[dict] = None) -> list[str]:
    """Pemicu kewalahan preset + yang diketik user, jadi satu daftar."""
    profile = profile if profile is not None else get_profile()
    return list(profile.get("overwhelm_triggers", [])) + list(profile.get("custom_triggers", []))


# CATATAN: `trigger_label()` dulu ada di sini buat nerjemahin key trigger jadi
# label tampilan. Nggak ada pemanggil -- onboarding.py & settings.py dua-duanya
# baca `TRIGGER_OPTIONS` langsung. Dihapus.


def in_productive_hours(profile: Optional[dict] = None, hour: Optional[int] = None) -> Optional[bool]:
    """True/False kalau user udah nentuin jam produktifnya, None kalau belum.

    None itu jawaban yang sah dan penting: kalau user belum ngisi, Kalem
    nggak boleh nebak-nebak jam produktif orang.
    """
    profile = profile if profile is not None else get_profile()
    ranges = profile.get("productive_hours") or []
    if not ranges:
        return None
    hour = clock.now().hour if hour is None else hour
    for start, end in ranges:
        # `hour + 24` nangkep rentang yang nyeberang tengah malam, mis.
        # [20, 25] harus kena juga pas jam 00.00.
        if start <= hour < end or start <= hour + 24 < end:
            return True
    return False


def fmt_hour(hour: int) -> str:
    """18 -> '18:00', 25 -> '01:00' (jam yang udah lewat tengah malam)."""
    return f"{hour % 24:02d}:00"


def fmt_range(start: int, end: int) -> str:
    tail = " besok" if end > 24 else ""
    return f"{fmt_hour(start)} – {fmt_hour(end)}{tail}"


def set_productive_hours(ranges: list[list[int]]) -> None:
    state = load_state()
    state["profile"]["productive_hours"] = [[int(a), int(b)] for a, b in ranges]
    # Benih preset dipadamkan -- lihat catatan di _normalise_profile().
    state["profile"]["productive_time"] = ""
    save_state(state)


def load_state() -> dict[str, Any]:
    data_dir, data_file, backup_file = _paths()
    data_dir.mkdir(parents=True, exist_ok=True)
    if not data_file.exists():
        state = _default_state()
        save_state(state)
        return state
    recovered_from_backup = False
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        # Penulisan normal bersifat atomik, tapi backup tetap penting buat
        # kasus storage/OS mati di waktu yang paling nggak enak. Jangan
        # diam-diam nampilin app kosong kalau salinan terakhir masih sehat.
        try:
            with open(backup_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            recovered_from_backup = True
        except (json.JSONDecodeError, OSError):
            return _default_state()

    # JSON yang valid belum tentu state aplikasi yang valid. Jangan izinkan
    # file manual/rusak membuat `.get()` di bawah meledak saat app dibuka.
    if not isinstance(state, dict):
        state = _default_state()
        recovered_from_backup = True

    migrated = _migrate(state)
    changed = migrated is not state or recovered_from_backup
    # Isi key root yang belum ada TANPA naikin schema. Perlu karena _migrate()
    # berhenti lebih awal kalau schema-nya udah sama -- jadi field baru yang
    # ditambahin ke _default_state() nggak akan pernah nyampe ke file lama.
    for key, value in _default_state().items():
        if key not in migrated:
            migrated[key] = deepcopy(value)
            changed = True

    # Bentuk root yang salah sama berbahayanya dengan key yang hilang: schema
    # bisa tetap "terbaru" sementara `tasks` berubah jadi string akibat edit
    # manual atau write yang rusak. Normalisasi hanya mengganti field rusak,
    # tidak membuang field valid lain.
    for key in ("profile", "favorites", "today_energy", "subscription", "usage", "dev"):
        if not isinstance(migrated.get(key), dict):
            migrated[key] = deepcopy(_default_state()[key])
            changed = True
    for key in (
        "tasks", "mood_logs", "reset_events", "inbox", "focus_records",
        "decompose_records", "decision_records",
    ):
        if not isinstance(migrated.get(key), list):
            migrated[key] = []
            changed = True

    # Isi juga kolom favorit baru. Nggak cukup ngandelin backfill root di
    # atas: `favorites` udah ada sejak dulu, yang nambah itu ISI-nya.
    favorites = migrated.setdefault("favorites", {})
    for key in FAVORITE_FIELDS:
        if key not in favorites:
            favorites[key] = ""
            changed = True

    # Profil juga, alasan yang sama.
    profile = migrated.setdefault("profile", _default_profile())
    for key, value in _default_profile().items():
        if key not in profile:
            profile[key] = value
            changed = True
    if _normalise_profile(profile):
        changed = True
    if changed:
        save_state(migrated)
    # Samain jam aplikasi dengan offset yang tersimpan, biar "hari" (dan jam)
    # hasil tombol dev tetap sama setelah app di-restart.
    dev = migrated.get("dev", {})
    clock.set_offset(dev.get("day_offset", 0))
    clock.set_hour_offset(dev.get("hour_offset", 0))
    return migrated


def save_state(state: dict[str, Any]) -> None:
    data_dir, data_file, backup_file = _paths()
    data_dir.mkdir(parents=True, exist_ok=True)
    temporary = data_file.with_suffix(".json.tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False, default=str)
        f.flush()
        os.fsync(f.fileno())
    # Backup adalah salinan state VALID sebelum diganti; kegagalannya nggak
    # boleh menghalangi simpan utama kalau filesystem menolak metadata backup.
    if data_file.exists():
        try:
            # Jangan menimpa backup sehat dengan primary yang korup saat
            # recovery. Copy hanya kalau JSON primary bisa dibaca sebagai
            # object state yang masuk akal.
            with open(data_file, "r", encoding="utf-8") as current:
                valid_primary = isinstance(json.load(current), dict)
            if valid_primary:
                shutil.copy2(data_file, backup_file)
        except (json.JSONDecodeError, OSError):
            pass
    os.replace(temporary, data_file)
    hook = _cloud_save_hook()
    if hook is not None:
        try:
            hook(deepcopy(state))
        except Exception:
            # Menyimpan lokal tidak boleh gagal hanya karena internet/cloud.
            pass


def reset_all_data() -> dict[str, Any]:
    """Balikin semua ke kondisi app baru diinstal.

    Dipakai tombol reset di Home buat keperluan testing -- hapus tombolnya
    kalau app udah mau dipakai beneran.
    """
    state = _default_state()
    save_state(state)
    clock.reset_offset()
    # Model yang udah dilatih HARUS dilupain: kalau nggak, dia bakal jawab
    # dari data yang barusan dihapus -- dan itu nggak akan pernah ketahuan
    # dari layar, cuma jawabannya aneh terus.
    try:
        from app import kalem_ml

        kalem_ml.reset_semua()
    except Exception:
        pass
    return state


# --------------------------------------------------------- morning brief


def needs_morning_brief() -> bool:
    """True kalau Morning Brief belum ditampilkan hari ini.

    Sengaja dicek dari tanggal, bukan flag boolean: begitu ganti hari
    (termasuk lewat tombol "Maju 1 hari" di dev menu) brief-nya balik
    muncul tanpa perlu direset manual.
    """
    state = load_state()
    if not state["profile"].get("onboarded"):
        return False
    return state.get("last_brief_date", "") != clock.today().isoformat()


def set_last_brief_date() -> None:
    state = load_state()
    state["last_brief_date"] = clock.today().isoformat()
    save_state(state)


# ------------------------------------------------- hari tanpa check-in
#
# KENAPA INI ADA
# --------------
# Tanpa ini, catatan mood TERAKHIR dipakai terus tanpa batas waktu. Jadi
# kalau catatan terakhir user isinya "capek banget" lalu dia menghilang
# seminggu, pas balik lagi Kalem MASIH nyaranin beban ringan berdasarkan
# perasaan seminggu lalu -- capeknya divalidasi terus-terusan, dan justru
# bikin makin nggak jalan.
#
# Aturan yang dipegang:
#   1. Hari tanpa check-in itu BENAR-BENAR KOSONG. Bukan "hari buruk",
#      bukan "hari baik" -- nggak ada yang dipelajari dari situ.
#   2. Makin lama absen, makin Kalem berhenti nebak dan ganti jadi nyapa.
#   3. Nggak pernah nuduh. Absen bisa berarti lupa, bisa berarti lagi
#      berat beneran -- dua-duanya nggak pantes disalahin.

# Di atas ini, catatan mood terakhir dianggap kedaluwarsa buat nebak
# kondisi HARI INI. 3 hari: cukup lama buat bukan sekadar skip sehari,
# cukup pendek buat nggak kelamaan pakai data basi.
STALE_AFTER_DAYS = 3


def touch_last_open() -> int:
    """Catat app dibuka hari ini. Return berapa hari sejak dibuka terakhir.

    Dipanggil sekali di router pas app start. Return 0 kalau ini pembukaan
    pertama (belum ada data) atau udah dibuka hari ini juga.
    """
    state = load_state()
    hari_ini = clock.today()
    terakhir = state.get("last_open_date") or ""
    state["last_open_date"] = hari_ini.isoformat()
    save_state(state)

    try:
        return max(0, (hari_ini - date.fromisoformat(terakhir)).days)
    except (TypeError, ValueError):
        return 0


def hari_sejak_checkin(logs: Optional[list[dict]] = None) -> Optional[int]:
    """Berapa hari sejak catatan mood TERAKHIR. None kalau belum pernah.

    Beda dari `touch_last_open()`: yang itu ngukur "buka app", yang ini
    ngukur "ngasih data". User bisa buka app tiap hari tanpa check-in --
    dan buat model, yang kedua itu yang penting.
    """
    logs = get_mood_logs() if logs is None else logs
    hari_ini = clock.today()
    tanggal = []
    for log in logs:
        try:
            d = date.fromisoformat(log.get("date", ""))
        except (TypeError, ValueError):
            continue
        if d <= hari_ini:
            tanggal.append(d)
    if not tanggal:
        return None
    return (hari_ini - max(tanggal)).days


def data_mood_basi(logs: Optional[list[dict]] = None) -> bool:
    """True kalau catatan terakhir udah kelewat lama buat nebak hari ini."""
    jarak = hari_sejak_checkin(logs)
    return jarak is not None and jarak > STALE_AFTER_DAYS


# ------------------------------------------------- pertanyaan "udah makan?"
#
# Nanya "udah makan hari ini?" jam 9 pagi itu nggak ada gunanya -- jawabannya
# hampir pasti "belum", dan itu bukan sinyal apa-apa selain hari masih pagi.
# Baru mulai jam 18 jawabannya berarti: kalau sampai malam belum makan, itu
# sinyal beneran buat burnout classifier (lihat neglect_streak).
MEAL_ASK_HOUR = 18


def waktunya_tanya_makan(now: Optional[Any] = None) -> bool:
    """True kalau sekarang udah masuk jam buat nanya soal makan."""
    return (now or clock.now()).hour >= MEAL_ASK_HOUR


def sudah_jawab_makan() -> bool:
    """True kalau pertanyaan makan hari ini udah dijawab (apa pun isinya)."""
    log = today_mood()
    return bool(log) and log.get("ate_today") is not None


def perlu_tanya_makan() -> bool:
    """Gerbang buat popup & tombol: udah lewat jam 18, udah check-in, dan
    pertanyaannya belum dijawab.

    Syarat "udah check-in" penting: jawaban makan disimpan di dalam catatan
    mood hari itu. Kalau belum ada catatannya, nyimpen jawaban makan bakal
    maksa ngarang mood & energi -- dan hari tanpa check-in harus tetap
    BENERAN kosong (lihat catatan di atas soal data basi).
    """
    return waktunya_tanya_makan() and today_mood() is not None and not sudah_jawab_makan()


# ---------------------------------------------------------- subscription
# Batas free tier. Angkanya sengaja di sini (bukan kesebar di view) biar
# gampang diubah pas nyari titik yang pas antara "kerasa cukup" dan
# "kerasa perlu upgrade".
FREE_LIMITS = {
    "decompose": 3,      # Pecah Tugas per hari
    "reco_cards": 1,     # kartu rekomendasi per MINGGU
}


def is_premium() -> bool:
    return bool(load_state().get("subscription", {}).get("is_premium", False))


def set_premium(value: bool) -> None:
    state = load_state()
    state.setdefault("subscription", {})["is_premium"] = bool(value)
    save_state(state)


def _usage_bucket(state: dict[str, Any]) -> dict[str, Any]:
    """Bucket pemakaian hari ini -- otomatis kosong lagi kalau tanggal ganti.

    Sengaja dibandingin ke clock.today(), bukan date.today(): biar tombol
    "Maju 1 hari" di dev menu beneran nge-reset kuota, bukan cuma mindahin
    tampilan tanggal.
    """
    usage = state.setdefault("usage", {"date": ""})
    today = clock.today().isoformat()
    if usage.get("date") != today:
        usage.clear()
        usage["date"] = today
    return usage


def usage_count(feature: str) -> int:
    return int(_usage_bucket(load_state()).get(feature, 0))


def quota_left(feature: str) -> Optional[int]:
    """Sisa kuota hari ini. None = tak terbatas (premium / fitur tanpa batas)."""
    if is_premium():
        return None
    limit = FREE_LIMITS.get(feature)
    if limit is None:
        return None
    return max(0, limit - usage_count(feature))


def can_use(feature: str) -> bool:
    left = quota_left(feature)
    return left is None or left > 0


def record_usage(feature: str) -> int:
    """Catat satu pemakaian. Premium nggak usah dicatat -- nggak ada batasnya."""
    if is_premium():
        return 0
    state = load_state()
    usage = _usage_bucket(state)
    usage[feature] = int(usage.get(feature, 0)) + 1
    save_state(state)
    return usage[feature]


def reco_cards_seen_this_week() -> int:
    """Kartu rekomendasi dibatasi per MINGGU, bukan per hari."""
    entry = load_state().get("usage_week", {})
    week = clock.today().isocalendar()
    key = f"{week[0]}-W{week[1]}"
    return int(entry.get(key, 0))


def record_reco_card() -> None:
    if is_premium():
        return
    state = load_state()
    week = clock.today().isocalendar()
    key = f"{week[0]}-W{week[1]}"
    # Cuma simpen minggu berjalan -- nggak perlu numpuk riwayat kuota.
    state["usage_week"] = {key: int(state.get("usage_week", {}).get(key, 0)) + 1}
    save_state(state)


def can_see_reco_card() -> bool:
    return is_premium() or reco_cards_seen_this_week() < FREE_LIMITS["reco_cards"]


def set_today_energy(level: int) -> None:
    """Kunci level energi buat HARI INI.

    Dipakai dua arah: Morning Brief nyimpen angka yang disaranin (pas user
    mencet "Sesuai"), dan chip energi di Tracker nyimpen koreksi manual.
    Disimpan per-tanggal, bukan sekali-pakai lewat nav.set_intent(): niat
    sekali-pakai bakal keburu kehapus begitu ada set_intent() lain (mis.
    tombol FOKUS di Home), padahal ramalannya harusnya berlaku sehari penuh.
    """
    state = load_state()
    state["today_energy"] = {"date": clock.today().isoformat(), "level": int(level)}
    save_state(state)


def today_energy() -> Optional[int]:
    """Level energi yang udah dikunci hari ini, atau None kalau belum ada."""
    entry = load_state().get("today_energy") or {}
    if entry.get("date") == clock.today().isoformat():
        return entry.get("level")
    return None


# ------------------------------------------------------------------- dev
# Dipakai tombol "next day" di Home buat nyimulasiin pemakaian beberapa
# hari dalam satu sesi testing. Hapus bareng tombolnya kalau app udah
# mau dipakai beneran.


def advance_day(days: int = 1) -> int:
    state = load_state()
    dev = state.setdefault("dev", {"day_offset": 0})
    dev["day_offset"] = dev.get("day_offset", 0) + days
    save_state(state)
    clock.set_offset(dev["day_offset"])
    return dev["day_offset"]


def day_offset() -> int:
    return load_state().get("dev", {}).get("day_offset", 0)


def jump_to_hour(target_hour: int) -> int:
    """Majuin jam aplikasi sampai `now()` lewat `target_hour`.

    Dipakai tombol demo "Lompat ke malam": fitur yang gerbangnya jam (mis.
    pertanyaan "udah makan?") mustahil ditunjukin kalau demonya siang, dan
    tombol "Maju 1 hari" nggak nolong -- dia cuma geser tanggal.
    """
    state = load_state()
    dev = state.setdefault("dev", {"day_offset": 0, "hour_offset": 0})
    dev["hour_offset"] = dev.get("hour_offset", 0) + clock.hours_until(target_hour)
    save_state(state)
    clock.set_hour_offset(dev["hour_offset"])
    return dev["hour_offset"]


def hour_offset() -> int:
    return load_state().get("dev", {}).get("hour_offset", 0)


def clear_hour_offset() -> None:
    """Balikin jam aplikasi ke jam asli, TANPA ngutak-atik geseran hari.

    Kepisah dari `clear_day_offset()` (yang nge-nol-in dua-duanya) supaya
    tombol "lompat ke malam" bisa dimatiin sendiri -- demo sering perlu tetap
    di hari yang udah dimajuin, cuma jamnya balik normal.
    """
    effective_day = clock.today()
    state = load_state()
    dev = state.setdefault("dev", {})
    dev["hour_offset"] = 0
    clock.set_hour_offset(0)
    # Kalau offset jam sebelumnya melewati tengah malam, menghapusnya bisa
    # membuat tanggal demo mundur satu hari. Pindahkan selisih itu ke offset
    # hari agar tombol ini benar-benar cuma mengubah JAM.
    day_adjustment = (effective_day - clock.today()).days
    if day_adjustment:
        dev["day_offset"] = int(dev.get("day_offset", 0)) + day_adjustment
        clock.set_offset(dev["day_offset"])
    save_state(state)


def clear_last_brief_date() -> None:
    """Lupain 'brief hari ini udah tampil'. Khusus tombol demo 'buka app lagi'.

    Kebalikan `set_last_brief_date()`. Tanpa ini, tombol buka-app-lagi nyaris
    nggak kelihatan efeknya: Morning Brief cuma nongol sekali per tanggal,
    jadi pembukaan kedua dan seterusnya langsung mendarat di Beranda.
    """
    state = load_state()
    state["last_brief_date"] = ""
    save_state(state)


def clear_day_offset() -> None:
    state = load_state()
    dev = state.setdefault("dev", {})
    dev["day_offset"] = 0
    dev["hour_offset"] = 0
    save_state(state)
    clock.reset_offset()


# ---------------------------------------------------------------- profile


def get_profile() -> dict:
    return load_state()["profile"]


# CATATAN: `set_user_name()` dulu ada di sini -- jalan pintas buat nyimpen
# nama doang. Nggak ada pemanggil: onboarding.py & settings.py dua-duanya
# lewat `save_profile({"name": ...})`, yang bisa nyimpen field lain sekalian.
# Dihapus.


def save_profile(answers: dict[str, Any]) -> dict:
    """Simpan hasil onboarding / editan Settings.

    Field yang nggak disebut di `answers` nggak disentuh -- jadi Settings
    boleh nyimpen sebagian profil tanpa ngehapus sisanya.
    """
    state = load_state()
    profile = state["profile"]
    for key, value in answers.items():
        if key in profile:
            profile[key] = value
    # Begitu rentang jam ditulis eksplisit, benih preset dipadamkan.
    # Tanpa ini, ngosongin semua rentang bakal ke-undo pas load berikutnya.
    if "productive_hours" in answers:
        profile["productive_time"] = ""
    profile["onboarded"] = True
    _normalise_profile(profile)
    save_state(state)
    return profile


def display_name() -> str:
    return get_profile().get("name") or "Teman"


# -------------------------------------------------------------- favorites


def get_favorites() -> dict[str, str]:
    return load_state().get("favorites", {})


def set_favorite(key: str, value: str) -> None:
    state = load_state()
    state.setdefault("favorites", {})[key] = value.strip()
    save_state(state)


def favorites_filled() -> int:
    return sum(1 for v in get_favorites().values() if v)


def favorite_color_hex() -> Optional[str]:
    """Hex warna favorit user, atau None kalau belum milih."""
    entry = FAVORITE_COLORS.get(get_favorites().get("warna", ""))
    return entry[1] if entry else None


def in_tired_window(now: Optional[Any] = None) -> bool:
    """True kalau sekarang lagi di jam yang user bilang paling capek.

    False juga kalau user belum ngisi -- jangan nebak-nebak jam capek
    orang, itu beda-beda banget.
    """
    entry = FAVORITE_TIRED_HOURS.get(get_favorites().get("jam_capek", ""))
    if not entry:
        return False
    start, end = entry[1]
    hour = (now or clock.now()).hour
    return start <= hour < end


# ------------------------------------------------------------------ tasks


# --- Mendesak dihitung sistem, bukan ditanya ke user ---
#
# Dulu user disuruh nyentang "Mendesak (deadline dekat)" sendiri. Dua
# masalahnya: (1) itu nanyain hal yang app-nya SUDAH TAU dari tanggal
# deadline, dan (2) "mendesak" itu berubah tiap hari -- centang yang diisi
# minggu lalu jadi bohong hari ini, tapi nggak ada yang ngupdate.
#
# Sekarang user cuma ngisi KAPAN (tanggal + jam opsional), dan mendesak/
# nggaknya dihitung ulang tiap kali dibaca. Selalu akurat, nol usaha user.
URGENT_WITHIN_HOURS = 24


def deadline_at(task: dict) -> Optional[datetime]:
    """Deadline ter-normalisasi untuk satu tugas, atau ``None`` bila tidak ada.

    Satu parser dipakai oleh label kuadran dan penilaian urutan urgensi agar
    tugas dengan deadline yang sama tidak bisa dibaca berbeda di dua tempat.
    Jam kosong tetap berarti akhir hari, sesuai kontrak lama.
    """
    try:
        d = date.fromisoformat(task.get("deadline", ""))
    except (TypeError, ValueError):
        return None

    jam = (task.get("deadline_time") or "").strip()
    if jam:
        try:
            h, m = (int(x) for x in jam.split(":")[:2])
        except (ValueError, TypeError):
            h, m = 23, 59
    else:
        h, m = 23, 59
    return datetime(d.year, d.month, d.day, min(h, 23), min(m, 59))


def is_urgent(task: dict, now: Optional[Any] = None) -> bool:
    """Mendesak = deadline tinggal <= 24 jam lagi (atau udah lewat).

    Kalau jam deadline nggak diisi, dianggap akhir hari (23:59) -- biar
    tugas "hari ini" tanpa jam nggak langsung kehitung lewat pas pagi.
    """
    now = now or clock.now()
    batas = deadline_at(task)
    if batas is None:
        return False
    sisa_jam = (batas - now).total_seconds() / 3600
    return sisa_jam <= URGENT_WITHIN_HOURS


def add_task(
    title: str,
    deadline: str,
    important: bool = True,
    steps: Optional[list[dict]] = None,
    difficulty_est: int = 2,
    kategori: str = "",
    jumlah_unit: float = 0,
    menit_est: int = 0,
    deadline_time: str = "",
    description: str = "",
    repeat: str = "none",
    custom_steps: Optional[list[str]] = None,
) -> dict:
    state = load_state()
    task = {
        "id": str(uuid.uuid4()),
        "title": title,
        "deadline": deadline,
        # Jam deadline, format "HH:MM". Kosong = nggak ditentuin jamnya.
        # `urgent` SENGAJA nggak disimpan -- dihitung ulang lewat is_urgent()
        # biar nggak pernah basi.
        "deadline_time": deadline_time,
        "important": important,
        # 1 = gampang, 2 = sedang, 3 = berat. Dipakai engine buat milih
        # next-action yang paling gampang dimulai.
        "difficulty_est": difficulty_est,
        # Jenis & ukuran tugas -- dasar prediksi durasi. Semuanya OPSIONAL:
        # tugas tanpa kategori tetap jalan penuh, cuma nggak dapet perkiraan
        # waktu. Maksa user ngisi ini bakal nambah gesekan justru di titik
        # yang paling rawan bikin orang ADHD berhenti: nambahin tugas.
        "kategori": kategori,
        "jumlah_unit": float(jumlah_unit),
        "menit_est": int(menit_est),
        # Konteks bebas OPSIONAL. Kalau diisi, Pecah Tugas mecah dari ISI
        # INI (bukan cuma judul) -- lihat decomposer_logic.py. Judul tugas
        # sering cuma 3-5 kata ("Bikin proposal hackathon"), nggak cukup
        # buat AI ngerti APA yang mau dikerjain; deskripsi itu konteksnya.
        "description": description,
        # Langkah yang ditulis user sendiri saat Pecah Tugas. Disimpan agar
        # penyusunan ulang berikutnya tidak menghapus konteks personalnya.
        "custom_steps": [str(step).strip() for step in (custom_steps or []) if str(step).strip()],
        # Tugas berulang adalah satu template, bukan ratusan duplikat.
        # Status checklist per tanggal disimpan terpisah di `occurrences`.
        "repeat": repeat if repeat in {"none", "daily", "weekly", "monthly"} else "none",
        "occurrences": {},
        "steps": steps or [],
        "created_at": clock.now().isoformat(),
    }
    state["tasks"].append(task)
    save_state(state)
    return task


def get_tasks() -> list[dict]:
    return load_state()["tasks"]


def tasks_for(day: str) -> list[dict]:
    """Tugas yang tampil pada satu hari, termasuk occurrence berulang.

    Untuk tugas berulang, object hasil adalah salinan bertanda
    `_occurrence_date`; mutasi checklist harus lewat `set_step_done()` agar
    hanya occurrence itu yang berubah, bukan semua minggu berikutnya.
    """
    try:
        target = date.fromisoformat(day)
    except (TypeError, ValueError):
        return []

    tampil: list[dict] = []
    for task in get_tasks():
        try:
            mulai = date.fromisoformat(task["deadline"])
        except (KeyError, TypeError, ValueError):
            continue
        repeat = task.get("repeat", "none")
        cocok = (
            target == mulai
            or (repeat == "daily" and target >= mulai)
            or (repeat == "weekly" and target >= mulai and target.weekday() == mulai.weekday())
            or (repeat == "monthly" and target >= mulai and target.day == mulai.day)
        )
        if not cocok:
            continue
        shown = dict(task)
        if repeat != "none":
            saved_steps = task.get("occurrences", {}).get(day, task.get("steps", []))
            shown["steps"] = [dict(step) for step in saved_steps]
            shown["_occurrence_date"] = day
        tampil.append(shown)
    return tampil


def tasks_today() -> list[dict]:
    return tasks_for(clock.today().isoformat())


def tasks_actionable_today() -> list[dict]:
    """Occurrence hari ini plus tugas sekali jalan yang sudah terlambat.

    Deadline yang terlewat tetap perlu ditriage, bukan hilang dari Beranda.
    Tugas berulang tidak dibawa dari occurrence lama karena setiap tanggal
    punya checklistnya sendiri dan akan muncul lagi sesuai jadwalnya.
    """
    today = clock.today()
    current = tasks_for(today.isoformat())
    overdue = []
    for task in get_tasks():
        if task.get("repeat", "none") != "none" or task_is_done(task):
            continue
        try:
            if date.fromisoformat(task["deadline"]) < today:
                overdue.append(task)
        except (KeyError, TypeError, ValueError):
            continue
    return current + overdue


def delete_task(task_id: str) -> None:
    state = load_state()
    state["tasks"] = [t for t in state["tasks"] if t["id"] != task_id]
    save_state(state)


def set_task_steps(task_id: str, steps: list[dict], occurrence_date: Optional[str] = None) -> None:
    """Timpa langkah tugas, TAPI centang yang teksnya sama tetap kejaga.

    Tanpa penjagaan ini, mencet "Pecah Tugas" buat kedua kalinya bakal
    ngehapus progres yang udah dicentang -- kerugian diam-diam yang paling
    bikin ilfeel: user ngerasa dihukum gara-gara mencet tombol.
    """
    state = load_state()
    for task in state["tasks"]:
        if task["id"] == task_id:
            old_steps = task.get("steps", [])
            if occurrence_date and task.get("repeat", "none") != "none":
                old_steps = task.get("occurrences", {}).get(occurrence_date, old_steps)
            done_texts = {
                s.get("text") for s in old_steps if s.get("done")
            }
            new_steps = [
                {**s, "done": s.get("done", False) or s.get("text") in done_texts}
                for s in steps
            ]
            # Template baru dipakai occurrence berikutnya. Occurrence yang
            # sedang dikerjakan juga di-update tanpa menghapus centang lama.
            task["steps"] = new_steps
            if occurrence_date and task.get("repeat", "none") != "none":
                task.setdefault("occurrences", {})[occurrence_date] = [dict(s) for s in new_steps]
            break
    save_state(state)


def set_task_custom_steps(task_id: str, steps: list[str]) -> None:
    """Simpan langkah tambahan user sebagai bagian permanen dari tugas."""
    state = load_state()
    clean = [str(step).strip() for step in steps if str(step).strip()]
    for task in state["tasks"]:
        if task["id"] == task_id:
            task["custom_steps"] = clean
            break
    save_state(state)


def set_step_done(
    task_id: str, step_index: int, done: bool, occurrence_date: Optional[str] = None
) -> None:
    state = load_state()
    for task in state["tasks"]:
        if task["id"] != task_id:
            continue
        if occurrence_date and task.get("repeat", "none") != "none":
            steps = task.setdefault("occurrences", {}).setdefault(
                occurrence_date, [dict(step) for step in task.get("steps", [])]
            )
        else:
            steps = task.get("steps", [])
        if 0 <= step_index < len(steps):
            steps[step_index]["done"] = done
            break
    save_state(state)


def task_is_done(task: dict) -> bool:
    return bool(task["steps"]) and all(s.get("done") for s in task["steps"])


def quadrant_of(task: dict, now: Optional[Any] = None) -> str:
    """Kuadran Eisenhower. Sumbu "mendesak" DIHITUNG dari deadline.

    Dulu ini baca `task["urgent"]` -- centang yang diisi user waktu bikin
    tugas. Masalahnya centang itu beku: tugas yang dibikin minggu lalu dan
    dicentang "nggak mendesak" tetap ngaku nggak mendesak walau deadline-nya
    besok. Sekarang dihitung ulang tiap dibaca, jadi selalu jujur.
    """
    urgent = is_urgent(task, now=now)
    penting = task.get("important", True)
    if urgent and penting:
        return "lakukan"      # penting + mendesak
    if not urgent and penting:
        return "jadwalkan"    # penting, nggak mendesak
    if urgent and not penting:
        return "delegasikan"  # mendesak, nggak penting
    return "nanti"            # nggak dua-duanya


def eisenhower_summary(day: Optional[str] = None) -> dict[str, list[dict]]:
    day = day or clock.today().isoformat()
    buckets: dict[str, list[dict]] = {
        "lakukan": [],
        "jadwalkan": [],
        "delegasikan": [],
        "nanti": [],
    }
    for task in tasks_for(day):
        if not task_is_done(task):
            buckets[quadrant_of(task)].append(task)
    return buckets


# CATATAN: `easiest_undone_step()` dulu ada di sini buat halaman Reset --
# ngambil langkah tugas yang belum selesai biar bisa ditawarin pas user lagi
# kewalahan. Dibuang bareng opsi "Satu tugas 60 detik": halaman jeda nggak
# boleh nyodorin kerjaan. Nggak ada pemanggil lain, jadi ikut dihapus.


# ------------------------------------------------- riwayat sesi fokus
# Bahan mentah buat rata-rata kecepatan personal di kalem_ml/model_durasi.
# Cuma sesi yang BENERAN dikerjain yang dicatat -- lihat MIN_RECORD_MINUTES.


# Di bawah 3 menit kemungkinan besar salah pencet, bukan kerja beneran.
# Nyatet itu bakal ngerusak rata-rata personal dengan angka yang bohong.
MIN_RECORD_MINUTES = 3


def add_focus_record(
    kategori: str,
    jumlah_unit: float,
    menit: float,
    energi: int = 4,
    task_title: str = "",
    menit_est: int = 0,
    selesai: bool = False,
) -> Optional[dict]:
    """Catat satu sesi fokus. Return None kalau nggak layak dicatat.

    `menit_est` disimpan bareng `menit` supaya bisa dihitung KALIBRASI WAKTU
    user -- seberapa jauh perkiraan meleset dari kenyataan. Itu ukuran time
    blindness paling langsung yang bisa diambil app ini.

    `selesai` bedain sesi yang beneran habis dari yang disudahi di tengah.
    Dua-duanya berguna, tapi artinya beda: yang kedua sinyal kesulitan
    bertahan, bukan sinyal kecepatan.
    """
    if float(menit) < MIN_RECORD_MINUTES:
        return None
    state = load_state()
    record = {
        "kategori": kategori,
        "jumlah_unit": float(jumlah_unit),
        "menit": round(float(menit), 1),
        "menit_est": int(menit_est),
        "selesai": bool(selesai),
        "energi": int(energi),
        "task_title": task_title,
        "date": clock.today().isoformat(),
    }
    state.setdefault("focus_records", []).insert(0, record)
    # Dibatasi 200 entri: lebih dari itu nggak nambah akurasi rata-rata, dan
    # bikin file data numpuk terus tanpa guna.
    state["focus_records"] = state["focus_records"][:200]
    save_state(state)
    return record


def get_focus_records() -> list[dict]:
    return load_state().get("focus_records", [])


# CATATAN: `focus_records_for()` dulu ada di sini buat nyaring record per
# kategori. Nggak ada pemanggil -- `kalem_ml/fitur.py` & `model_durasi.py`
# nyaring sendiri inline dari `get_focus_records()`. Dihapus.


# ------------------------------------------- riwayat pecah tugas (retrieval)
#
# KENAPA INI ADA
# --------------
# Tiap Pecah Tugas yang sukses disimpen di sini, biar tugas MIRIP berikutnya
# bisa mungut hasil lama -- nol panggilan AI. Makin lama app dipakai, makin
# sering ketemu yang mirip, makin jarang API kepanggil. Itu satu-satunya cara
# "makin dipakai makin murah" yang realistis buat output berupa KALIMAT:
# model lokal bisa NEBAK ANGKA (lihat model_durasi) tapi nggak bisa NGARANG
# kalimat baru tanpa fine-tune LLM -- di luar skala project ini.
#
# Yang disimpen sengaja judul+deskripsi MENTAH: pencocokannya di
# `kalem_ml/model_pecah.py` pakai TF-IDF n-gram huruf, jadi butuh teks asli,
# bukan hasil olahan.

# Batas entri. Lebih dari ini nggak nambah peluang ketemu yang mirip secara
# berarti, tapi bikin file data numpuk & pencocokan makin lambat.
MAX_DECOMPOSE_RECORDS = 300


def add_decompose_record(
    title: str,
    description: str,
    steps: list[str],
    source: str = "ai",
    language: str = "id",
) -> Optional[dict]:
    """Catat satu hasil Pecah Tugas yang sukses. Return None kalau nggak layak.

    `source`: "ai" (dari LLM) | "manual" (deskripsi terstruktur user sendiri)
    | "dataset" (pola bawaan dari DATASET/).

    `language`: penanda bahasa. Retrieval cuma mungut pola SEBAHASA biar user
    Indonesia nggak pernah dapet langkah berbahasa Inggris -- lihat
    `kalem_ml/model_pecah.cari()`.
    """
    steps = [s.strip() for s in steps if (s or "").strip()]
    if not (title or "").strip() or not steps:
        return None

    state = load_state()
    record = {
        "title": title.strip(),
        "description": (description or "").strip(),
        "steps": steps,
        "source": source,
        "language": language,
        "date": clock.today().isoformat(),
    }
    daftar = state.setdefault("decompose_records", [])
    # Judul+deskripsi yang sama persis ditimpa, bukan numpuk -- mecah ulang
    # tugas yang sama harusnya ngoreksi catatan lama, bukan bikin duplikat
    # yang nanti rebutan pas dicocokin.
    kunci = (record["title"].lower(), record["description"].lower())
    state["decompose_records"] = [
        r for r in daftar
        if (r.get("title", "").lower(), r.get("description", "").lower()) != kunci
    ]
    state["decompose_records"].insert(0, record)
    state["decompose_records"] = state["decompose_records"][:MAX_DECOMPOSE_RECORDS]
    save_state(state)
    return record


def get_decompose_records() -> list[dict]:
    return load_state().get("decompose_records", [])


# ------------------------------------------- label keputusan (bahan ML_KALEM)
#
# KENAPA INI ADA
# --------------
# Semua model lain punya label yang OBJEKTIF & gratis: model_mood belajar dari
# skor besok, model_overwhelm dari "user mencet SOS apa nggak". Tapi buat
# pertanyaan "pesan mana yang sebaiknya Kalem tampilkan sekarang" -- nggak ada
# jawaban benar yang bisa dikarang dari data yang ada.
#
# Satu-satunya label jujur: USER NGAPAIN sesudah dikasih pesan itu. Dipencet
# tombol aksinya, atau didiemin? Itu yang dicatat di sini, dan itu satu-satunya
# bahan yang bisa bikin ML_KALEM belajar milih.
#
# TIGA HAL YANG SENGAJA DIPEGANG
# ------------------------------
# 1. NGGAK ADA PENILAIAN. "Didiemin" itu data, bukan kegagalan user. Angka ini
#    nggak pernah dipajang sebagai skor kepatuhan -- itu bakal ngubah app jadi
#    alat yang bikin merasa bersalah, kebalikan dari tujuannya.
# 2. LOKAL. Sama kayak data lain di app ini, nggak ke mana-mana.
# 3. DITAMPILIN BERULANG ITU SINYAL. Kalau pesan yang sama muncul 5x dan nggak
#    pernah dipencet, itu jauh lebih informatif daripada 1x nggak dipencet --
#    makanya yang dicatat `n_tampil`, bukan bikin baris baru tiap render.

MAX_DECISION_RECORDS = 500


def _fitur_ringkas(f: Optional[Any]) -> dict[str, float]:
    """Ambil SEBAGIAN fitur aja buat disimpen bareng keputusan.

    Bukan semua ~43 kolom: yang disimpen cuma yang masuk akal ngaruh ke
    "pesan ini kepencet apa nggak". Nyimpen semuanya bikin file data
    membengkak tanpa nambah apa-apa yang kepakai.
    """
    if f is None:
        return {}
    kolom = (
        "skor_3h", "energi_terakhir", "streak_abai", "n_sos_7h",
        "n_belum_selesai", "n_mendesak", "beban_menit", "rasio_selesai_7h",
        "di_jam_produktif", "di_jam_capek", "jam", "weekday", "is_weekend",
        "obat_kelewat", "hari_sejak_checkin",
    )
    keluar: dict[str, float] = {}
    for k in kolom:
        try:
            keluar[k] = round(float(f[k]), 3)
        except (KeyError, TypeError, ValueError):
            continue
    return keluar


def record_decision_shown(
    kind: str,
    action_kind: str,
    fitur: Optional[Any] = None,
    label: str = "",
) -> Optional[str]:
    """Catat "Kalem nampilin keputusan X". Return id catatannya.

    Kalau keputusan yang SAMA (kind+action_kind) hari ini udah kecatat dan
    belum dipencet, yang ada tinggal ditambah `n_tampil` -- bukan bikin baris
    baru. `build()` halaman Beranda kepanggil tiap kali user balik ke sana,
    dan tanpa penggabungan ini satu keputusan bisa kecatat puluhan kali.
    """
    if not kind:
        return None
    state = load_state()
    daftar = state.setdefault("decision_records", [])
    hari_ini = clock.today().isoformat()

    for r in daftar:
        if (
            r.get("date") == hari_ini
            and r.get("kind") == kind
            and r.get("action_kind") == action_kind
            and not r.get("acted")
        ):
            r["n_tampil"] = int(r.get("n_tampil", 1)) + 1
            r["terakhir_tampil"] = clock.now().isoformat()
            save_state(state)
            return r.get("id")

    catatan = {
        "id": str(uuid.uuid4()),
        "date": hari_ini,
        "timestamp": clock.now().isoformat(),
        "terakhir_tampil": clock.now().isoformat(),
        "kind": kind,                 # med | pre_escalate | next_action | calm
        "action_kind": action_kind,   # med_taken | reset | focus | add_task
        "label": label,               # teks tombolnya, buat dibaca manusia
        "n_tampil": 1,
        "acted": False,
        "acted_at": "",
        "fitur": _fitur_ringkas(fitur),
    }
    daftar.insert(0, catatan)
    state["decision_records"] = daftar[:MAX_DECISION_RECORDS]
    save_state(state)
    return catatan["id"]


def record_decision_acted(kind: str, action_kind: str) -> bool:
    """Tandai keputusan hari ini yang cocok sebagai DIPENCET. Return True
    kalau ada yang ketandai."""
    state = load_state()
    hari_ini = clock.today().isoformat()
    for r in state.get("decision_records", []):
        if (
            r.get("date") == hari_ini
            and r.get("kind") == kind
            and r.get("action_kind") == action_kind
            and not r.get("acted")
        ):
            r["acted"] = True
            r["acted_at"] = clock.now().isoformat()
            save_state(state)
            return True
    return False


def get_decision_records() -> list[dict]:
    return load_state().get("decision_records", [])


# ---------------------------------------------------------- quick capture


def add_inbox_note(text: str) -> dict:
    """Brain dump: simpan mentah dulu, dirapikan jadi tugas belakangan."""
    state = load_state()
    note = {
        "id": str(uuid.uuid4()),
        "text": text.strip(),
        "created_at": clock.now().isoformat(),
    }
    state.setdefault("inbox", []).insert(0, note)
    save_state(state)
    return note


def get_inbox() -> list[dict]:
    return load_state().get("inbox", [])


def delete_inbox_note(note_id: str) -> None:
    state = load_state()
    state["inbox"] = [n for n in state.get("inbox", []) if n["id"] != note_id]
    save_state(state)


# -------------------------------------------------------------- mood/diary


def add_mood_log(
    mood: str,
    score: int,
    energy: int,
    diary: str = "",
    tags: Optional[list[str]] = None,
    quick_tags: Optional[list[str]] = None,
    ate_today: Optional[bool] = None,
    rested_enough: Optional[bool] = None,
) -> dict:
    """Satu entri per hari -- entri baru menimpa entri hari yang sama.

    ate_today/rested_enough sengaja Optional[bool] (bukan default False):
    None = belum dijawab (opsional, boleh dilewat), beda makna sama "Belum".
    """
    state = load_state()
    today = clock.today()
    # Check-in, pertanyaan care, dan Diary bisa disimpan dari halaman berbeda
    # di hari yang sama. Field yang tidak dikirim pemanggil harus mewarisi
    # jawaban sebelumnya, bukan berubah jadi kosong/None.
    previous = next(
        (entry for entry in state["mood_logs"] if entry.get("date") == today.isoformat()),
        {},
    )
    log = {
        "date": today.isoformat(),
        "mood": mood,
        "score": score,
        "energy": energy,
        "diary": diary if diary else previous.get("diary", ""),
        "tags": tags if tags is not None else previous.get("tags", []),
        "quick_tags": quick_tags if quick_tags is not None else previous.get("quick_tags", []),
        "ate_today": ate_today if ate_today is not None else previous.get("ate_today"),
        "rested_enough": rested_enough if rested_enough is not None else previous.get("rested_enough"),
        "weekday": today.weekday(),
        "is_weekend": today.weekday() >= 5,
    }
    state["mood_logs"] = [entry for entry in state["mood_logs"] if entry["date"] != log["date"]]
    state["mood_logs"].insert(0, log)
    save_state(state)
    return log


def get_mood_logs() -> list[dict]:
    return load_state()["mood_logs"]


def latest_mood() -> Optional[dict]:
    logs = get_mood_logs()
    return logs[0] if logs else None


def today_mood() -> Optional[dict]:
    latest = latest_mood()
    return latest if latest and latest["date"] == clock.today().isoformat() else None


def diary_entries() -> list[dict]:
    return [entry for entry in get_mood_logs() if entry.get("diary")]


# ------------------------------------------------------------ reset events


def add_reset_event(choice: str) -> dict:
    """Catat opsi penenang yang dipilih user (dasar personalisasi frekuensi)."""
    state = load_state()
    latest = state["mood_logs"][0] if state["mood_logs"] else None
    event = {
        "timestamp": clock.now().isoformat(),
        "date": clock.today().isoformat(),
        "choice": choice,
        "mood_score": latest["score"] if latest else None,
    }
    state["reset_events"].insert(0, event)
    save_state(state)
    return event


def get_reset_events(within_days: Optional[int] = None) -> list[dict]:
    events = load_state()["reset_events"]
    if within_days is None:
        return events
    cutoff = clock.today() - timedelta(days=within_days)
    return [e for e in events if date.fromisoformat(e["date"]) >= cutoff]


# ------------------------------------------------------------- medication


def set_medication(name: str, pills_left: int, pills_per_day: float) -> dict:
    state = load_state()
    existing = state.get("medication") or {}
    same_drug = (existing.get("name") or "").strip().lower() == name.strip().lower()
    state["medication"] = {
        "name": name,
        "pills_left": pills_left,
        "pills_per_day": pills_per_day,
        # start_date dipertahanin kalau obatnya sama -- ini titik awal buat
        # ngitung dosis kelewat, dan nge-reset tiap user ngubah stok bakal
        # ngehapus riwayat yang sah.
        "start_date": existing.get("start_date") if same_drug and existing.get("start_date")
        else clock.today().isoformat(),
        "enabled": True,
        # Absen obat: stok cuma turun kalau user konfirmasi udah minum.
        "last_taken": existing.get("last_taken", ""),
        "take_log": existing.get("take_log", []),
        # Hasil pencocokan registri BPOM -- dibuang kalau obatnya ganti, biar
        # nggak nampilin validasi obat lama di bawah nama obat baru.
        "bpom": existing.get("bpom") if same_drug else None,
    }
    save_state(state)
    return state["medication"]


def set_medication_registry(entry: dict) -> None:
    """Simpan hasil pencocokan registri BPOM (nama resmi, NIE, golongan).

    Dipisah dari `info` (penjelasan dari Gemini): yang ini data resmi yang
    nggak berubah dan nggak butuh jaringan, yang itu teks yang bisa keliru.
    """
    state = load_state()
    if state.get("medication"):
        state["medication"]["bpom"] = entry
        save_state(state)


# CATATAN: `get_medication_registry()` dulu ada di sini buat baca balik hasil
# BPOM yang tersimpan. Nggak ada pemanggil -- med_setup.py nge-lookup ULANG
# tiap halaman dibuka (`check_name()`, live & offline, ~10ms), jadi nilai
# yang tersimpan nggak pernah dibaca balik. Dihapus.
#
# `set_medication_info()`/`get_medication_info()` juga dihapus bareng field
# `"info"` di `set_medication()` di bawah -- itu sisa dari lapisan lookup
# obat lewat Gemini yang UDAH DIBUANG total dan digantiin registri BPOM
# offline (lihat docstring `core/bpom.py`). Nggak ada yang nulis atau baca
# field itu lagi.
#
# `medication_taken_today()` juga dihapus -- `medication_model.check_status()`
# ngitung `taken_today` sendiri inline dari field yang sama, jadi ini duplikat
# yang nggak pernah dipanggil.


def get_medication() -> Optional[dict]:
    return load_state()["medication"]


def take_medication() -> Optional[dict]:
    """Absen obat: stok berkurang otomatis sebesar dosis harian.

    Ini yang bikin user nggak perlu input stok ulang -- form cuma diisi
    sekali di awal. Sengaja idempotent per hari: mencet dua kali di hari
    yang sama nggak ngurangin stok dua kali.

    Kalau stok udah 0, absen ditolak (return None) -- jangan nyatet "udah
    minum" buat obat yang secara fisik udah abis, itu bikin log & pengingat
    bohong.
    """
    state = load_state()
    med = state.get("medication")
    if not med or not med.get("enabled", True):
        return None
    if float(med.get("pills_left", 0)) <= 0:
        return None

    today_iso = clock.today().isoformat()
    if med.get("last_taken") == today_iso:
        return med

    rate = float(med.get("pills_per_day", 1))
    med["pills_left"] = max(float(med.get("pills_left", 0)) - rate, 0)
    med["last_taken"] = today_iso
    med.setdefault("take_log", []).insert(0, today_iso)
    save_state(state)
    return med


def disable_medication() -> None:
    state = load_state()
    if state["medication"]:
        state["medication"]["enabled"] = False
        save_state(state)
