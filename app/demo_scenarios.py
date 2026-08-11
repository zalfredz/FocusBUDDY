"""Kumpulan skenario demo dan validator kualitas keputusan KALEM."""
from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from typing import Any, Callable, Optional

JADWAL_KULIAH: dict[int, list[tuple[str, str, str]]] = {
    0: [
        ("08:00", "09:40", "Agama Kristen Protestan"),
        ("10:00", "11:40", "Manajemen Bisnis B"),
        ("13:00", "14:40", "Dasar-Dasar Pemrograman 1 (DDP 1) F"),
    ],
    1: [
        ("08:00", "09:40", "Kombinatorika & Statistika (Kombistek) A"),
        ("10:00", "11:40", "Matematika Diskrit 1 (MatDis 1) C"),
        ("13:00", "14:40", "Kalkulus 1 F"),
        ("16:00", "16:50", "Kalkulus 1 F"),
    ],
    2: [
        ("11:00", "11:50", "Manajemen Bisnis B"),
        ("14:00", "15:40", "Dasar-Dasar Pemrograman 1 (DDP 1) F"),
    ],
    3: [
        ("08:00", "08:50", "Kombinatorika & Statistika (Kombistek) A"),
        ("10:00", "10:50", "Matematika Diskrit 1 (MatDis 1) C"),
        ("11:00", "11:50", "Kalkulus 1 F"),
        ("15:00", "16:40", "Dasar-Dasar Pemrograman 1 (DDP 1) F"),
    ],
    4: [
        ("08:00", "08:50", "Matematika Diskrit 1 (MatDis 1) C"),
    ],
    5: [],
    6: [],
}

MATKUL_TAG = {
    "Agama Kristen Protestan": "agama",
    "Manajemen Bisnis B": "manbis",
    "Dasar-Dasar Pemrograman 1 (DDP 1) F": "ddp1",
    "Kombinatorika & Statistika (Kombistek) A": "kombistek",
    "Matematika Diskrit 1 (MatDis 1) C": "matdis",
    "Kalkulus 1 F": "kalkulus",
}


def _hari_depan(target_wd: int) -> date:
    today = date.today()
    delta = (target_wd - today.weekday()) % 7
    return today + timedelta(days=delta)


def _tugas_mingguan_kuliah() -> list[dict]:
    return [
        {"title": "Quiz Kalkulus 1", "important": True, "difficulty": 3,
         "steps": ["Latihan soal integral", "Review catatan kelas"],
         "deadline_date": _hari_depan(3), "deadline_time": "10:50"},
        {"title": "Quiz Matematika Diskrit 1", "important": True, "difficulty": 3,
         "steps": ["Baca ulang materi kombinatorik", "Latihan soal minggu lalu"],
         "deadline_date": _hari_depan(4), "deadline_time": "08:50"},
        {"title": "Tugas Kombistek mingguan", "important": True, "difficulty": 2,
         "steps": ["Selesaiin soal nomor 1-5", "Submit ke portal"],
         "deadline_date": _hari_depan(3), "deadline_time": "23:59"},
        {"title": "Diskusi kelompok Manajemen Bisnis", "important": False, "difficulty": 1,
         "steps": ["Baca studi kasus", "Tulis poin diskusi"],
         "deadline_date": _hari_depan(0), "deadline_time": "10:00"},
    ]


DIARY_NORMAL = [
    "Kelas lumayan lancar hari ini.",
    "Sempet ngantuk pas kelas tapi masih bisa ngikutin.",
    "Nyicil tugas dikit-dikit, lumayan progres.",
    "Biasa aja, jalanin rutinitas kuliah.",
    "Ada waktu senggang buat istirahat bentar.",
    "Ngerjain PR sambil dengerin musik, santai aja.",
]
DIARY_WEEKEND = [
    "Libur, akhirnya bisa napas.",
    "Ngerjain hal santai, nggak mikirin kuliah dulu.",
    "Ketemu temen, refreshing dikit.",
    "Tidur lebih lama dari biasanya.",
    "Beres-beres kos, lumayan lega rasanya.",
]
DIARY_BERAT_KAMIS = [
    "Kombistek deadline hari ini plus kelas numpuk dari pagi, capek banget.",
    "Ngoding tugas Kombistek sampe mepet, plus kelas 4 sesi. Berat.",
    "Kamis paling padet minggu ini, deadline Kombistek bikin panik.",
    "Dari pagi ke kelas terus, sore masih harus submit Kombistek.",
]
DIARY_BERAT_JUMAT = [
    "Quiz MatDis hari ini, belum siap-siap banget rasanya.",
    "Abis begadang belajar quiz MatDis, badan capek.",
    "Jumat cuma 1 kelas tapi mental abis gara-gara quiz.",
    "Deg-degan nunggu quiz MatDis dari semalem.",
]
DIARY_SENANG = [
    "Hari yang bagus banget, ada kabar baik!",
    "Ketemu temen lama, seneng banget rasanya.",
    "Nilai keluar bagus, mood langsung naik.",
    "Jalan-jalan sama keluarga, refreshing total.",
    "Dapet kabar baik dari rumah, semangat lagi.",
]
DIARY_JENUH = [
    "Rasanya capek banget, pengen nyerah aja.",
    "Overwhelmed banget hari ini, semua numpuk bareng.",
    "Susah fokus, kepala penuh terus.",
    "Ngerasa nggak sanggup, pengen istirahat total tapi nggak bisa.",
    "Berat banget, pengen ngilang sebentar aja.",
]
DIARY_LELAH_RINGAN = [
    "Beberapa hari ini kurang tidur, badan agak lemes.",
    "Masih bisa jalan, cuma energinya emang lagi nggak penuh.",
    "Ngantuk terus dari kemarin, tapi nggak ada yang parah kejadian.",
    "Capek biasa aja, bukan yang bikin panik.",
]
DIARY_STABIL_BAGUS = [
    "Beberapa hari ini lancar, ritme kerasa pas.",
    "Tidur cukup, badan enak, kerjaan jalan sesuai rencana.",
    "Mood stabil, nggak ada drama, enak buat lanjut ngerjain.",
    "Rasanya lagi on track, semua kekontrol.",
]


def _log(score: int, energy: int, tags: list[str], diary: str = "",
         ate: bool = True, rested: bool = True) -> dict:
    return {"score": score, "energy": energy, "tags": tags, "diary": diary,
            "ate": ate, "rested": rested}


def _riwayat_semester(
    n_hari: int,
    rng: random.Random,
    minggu_berat: frozenset[int] = frozenset(),
    hari_event: dict[int, str] | None = None,
    hanya_offset: list[int] | None = None,
) -> list[dict]:
    hari_event = hari_event or {}
    today = date.today()
    offsets = hanya_offset if hanya_offset is not None else range(n_hari)
    hasil: list[dict] = []
    for offset in offsets:
        d = today - timedelta(days=offset)
        wd = d.weekday()
        minggu = offset // 7

        if offset in hari_event:
            jenis = hari_event[offset]
            if jenis == "senang":
                entry = _log(5, rng.choice([5, 6]), ["senang"],
                             rng.choice(DIARY_SENANG), True, True)
            else:
                entry = _log(1, rng.choice([1, 2]), ["overwhelmed"],
                             rng.choice(DIARY_JENUH), False, False)
        elif wd in (3, 4) and minggu in minggu_berat:
            if wd == 3:
                entry = _log(rng.choice([1, 2]), rng.choice([1, 2]), ["kuliah", "kombistek"],
                             rng.choice(DIARY_BERAT_KAMIS), False, False)
            else:
                entry = _log(rng.choice([1, 2]), rng.choice([1, 2]), ["kuliah", "matdis"],
                             rng.choice(DIARY_BERAT_JUMAT), False, False)
        elif wd >= 5:
            entry = _log(rng.choice([4, 5]), rng.choice([4, 5, 6]), ["istirahat"],
                         rng.choice(DIARY_WEEKEND), True, True)
        else:
            kelas_hari = JADWAL_KULIAH.get(wd, [])
            tag = MATKUL_TAG.get(kelas_hari[0][2], "kuliah") if kelas_hari else "kuliah"
            entry = _log(rng.choice([3, 4]), rng.choice([3, 4]), ["kuliah", tag],
                         rng.choice(DIARY_NORMAL), True, True)

        entry["offset"] = offset
        hasil.append(entry)
    return hasil


def _riwayat_energi_rendah(n_hari: int, rng: random.Random) -> list[dict]:
    today = date.today()
    hasil = []
    for offset in range(n_hari):
        d = today - timedelta(days=offset)
        rested = rng.random() > 0.6
        entry = _log(3, rng.choice([1, 2]), ["capek", "kurang_tidur"],
                     rng.choice(DIARY_LELAH_RINGAN), True, rested)
        entry["offset"] = offset
        hasil.append(entry)
    return hasil


def _riwayat_stabil_bagus(n_hari: int, rng: random.Random) -> list[dict]:
    today = date.today()
    hasil = []
    for offset in range(n_hari):
        d = today - timedelta(days=offset)
        skor = rng.choice([4, 4, 5])
        energi = rng.choice([4, 5])
        entry = _log(skor, energi, ["stabil"], rng.choice(DIARY_STABIL_BAGUS), True, True)
        entry["offset"] = offset
        hasil.append(entry)
    return hasil


def _obat_take_log(
    rng: random.Random,
    minggu_berat: frozenset[int] = frozenset(),
    hari_event: dict[int, str] | None = None,
    hanya_offset: list[int] | None = None,
    n_hari: int = 90,
    adherence: float = 0.9,
) -> list[str]:
    hari_event = hari_event or {}
    today = date.today()
    offsets = hanya_offset if hanya_offset is not None else range(n_hari)
    taken: list[str] = []
    for offset in offsets:
        d = today - timedelta(days=offset)
        wd = d.weekday()
        minggu = offset // 7
        berat = (wd in (3, 4) and minggu in minggu_berat) or hari_event.get(offset) == "jenuh"
        if berat:
            continue
        if rng.random() < adherence:
            taken.append(d.isoformat())
    taken.sort(reverse=True)
    return taken


def _skenario_baru() -> dict:
    return {
        "label": "0 — User baru",
        "description": "Belum ada histori sama sekali. Nunjukin Kalem jujur pas datanya kosong.",
        "premium": False,
        "profile": {
            "name": "Alfredo", "age_range": "18-24", "status": ["mahasiswa"],
            "productive_hours": [[19, 23]], "sleep_condition": "cukup",
            "on_medication": "tidak", "overwhelm_triggers": ["deadline"], "custom_triggers": [],
        },
        "favorites": {},
        "mood_history": [],
        "tasks": [
            {"title": "Kenalan sama jadwal kuliah minggu ini", "important": True,
             "difficulty": 1, "steps": ["Cek jadwal lengkap"]},
        ],
        "inbox": [],
        "medication": None,
        "sos_days_ago": [],
        "show_brief_today": True,
    }


def _skenario_deadline_stack() -> dict:
    rng = random.Random(11001)
    riwayat = _riwayat_semester(7, rng)
    return {
        "label": "Deadline stack — 3 tugas konflik, ~30 menit tersedia",
        "description": "7 catatan biasa (bukan fokus skenario ini). 3 tugas hari ini "
                        "sengaja tarik-menarik: besar+penting+deadline malam, kecil+penting+"
                        "deadline sore, kecil+nggak penting+deadline paling deket.",
        "premium": False,
        "available_minutes_hint": 30,
        "profile": {
            "name": "Alfredo", "age_range": "18-24", "status": ["mahasiswa"],
            "productive_hours": [[19, 23]], "sleep_condition": "cukup",
            "on_medication": "tidak", "overwhelm_triggers": ["deadline"], "custom_triggers": [],
        },
        "favorites": {"penyemangat": "satu-satu aja, nggak usah buru-buru"},
        "mood_history": riwayat,
        "tasks": [
            {"title": "Tulis laporan praktikum", "important": True, "difficulty": 3,
             "estimated_minutes": 90, "deadline_time": "23:59",
             "steps": ["Buka data hasil praktikum", "Tulis bagian metode", "Tulis pembahasan"]},
            {"title": "Latihan 5 soal Kalkulus", "important": True, "difficulty": 1,
             "estimated_minutes": 15, "deadline_time": "18:00",
             "steps": ["Buka buku soal", "Kerjain 5 soal"]},
            {"title": "Balas email dosen", "important": False, "difficulty": 1,
             "estimated_minutes": 5, "deadline_time": "17:00",
             "steps": ["Buka email dosen", "Balas singkat"]},
        ],
        "inbox": [],
        "medication": None,
        "sos_days_ago": [],
        "show_brief_today": True,
    }


def _skenario_low_energy() -> dict:
    rng = random.Random(12002)
    riwayat = _riwayat_energi_rendah(8, rng)
    return {
        "label": "Energi rendah, TANPA pola SOS/overwhelm",
        "description": "8 hari energi 1-2 (kurang tidur), tapi skor mood tetap 3 dan "
                        "TIDAK ADA SOS -- beda dari overwhelm beneran.",
        "premium": False,
        "profile": {
            "name": "Alfredo", "age_range": "18-24", "status": ["mahasiswa"],
            "productive_hours": [[19, 23]], "sleep_condition": "kurang",
            "on_medication": "tidak", "overwhelm_triggers": ["kurang_tidur"], "custom_triggers": [],
        },
        "favorites": {"jam_capek": "sore"},
        "mood_history": riwayat,
        "tasks": [
            {"title": "Baca bab kuliah yang ketinggalan", "important": True, "difficulty": 1,
             "estimated_minutes": 20, "steps": ["Buka bab yang mau dibaca"]},
            {"title": "Kerjain PR kecil DDP1", "important": True, "difficulty": 2,
             "estimated_minutes": 30, "steps": ["Buka editor dan filenya"]},
        ],
        "inbox": [],
        "medication": None,
        "sos_days_ago": [],
        "show_brief_today": True,
    }


def _skenario_overwhelmed() -> dict:
    rng = random.Random(13003)
    hari_event = {0: "jenuh", 1: "jenuh", 3: "jenuh"}
    riwayat = _riwayat_semester(10, rng, hari_event=hari_event)
    return {
        "label": "Overwhelmed — tugas besar numpuk + histori gampang overwhelmed",
        "description": "3 dari 10 hari terakhir 'jenuh' (termasuk hari ini & kemarin), "
                        "SOS 2x dalam 3 hari, plus 2 tugas besar hari ini.",
        "premium": False,
        "profile": {
            "name": "Alfredo", "age_range": "18-24", "status": ["mahasiswa"],
            "productive_hours": [[19, 23]], "sleep_condition": "begadang",
            "on_medication": "tidak",
            "overwhelm_triggers": ["tugas_numpuk", "deadline"], "custom_triggers": [],
        },
        "favorites": {"penyemangat": "nggak apa-apa pelan", "jam_capek": "sore"},
        "mood_history": riwayat,
        "tasks": [
            {"title": "Kejar laporan Kombistek yang numpuk", "important": True, "difficulty": 3,
             "estimated_minutes": 90, "deadline_time": "23:59",
             "steps": ["List semua yang ketinggalan", "Mulai dari yang paling gampang"]},
            {"title": "Bikin presentasi kelompok Manbis", "important": True, "difficulty": 3,
             "estimated_minutes": 60, "deadline_time": "23:59",
             "steps": ["Tulis outline poin per slide"]},
        ],
        "inbox": ["banyak yang ketinggalan, bingung mulai dari mana"],
        "medication": None,
        "sos_days_ago": [0, 1],
        "show_brief_today": True,
    }


def _skenario_productive_streak() -> dict:
    rng = random.Random(14004)
    riwayat = _riwayat_stabil_bagus(14, rng)
    return {
        "label": "Productive streak — kondisi bagus, jangan over-protect",
        "description": "14 hari stabil (mood 4-5, energi 4-5, makan/istirahat selalu "
                        "terjaga), kapasitas waktu cukup, 1 tugas normal.",
        "premium": False,
        "profile": {
            "name": "Alfredo", "age_range": "18-24", "status": ["mahasiswa"],
            "productive_hours": [[19, 23]], "sleep_condition": "cukup",
            "on_medication": "tidak", "overwhelm_triggers": ["deadline"], "custom_triggers": [],
        },
        "favorites": {"penyemangat": "lagi on fire, lanjutin aja"},
        "mood_history": riwayat,
        "tasks": [
            {"title": "Nulis bab 2 laporan penelitian", "important": True, "difficulty": 2,
             "estimated_minutes": 45, "steps": ["Buka data hasil penelitian"]},
        ],
        "inbox": [],
        "medication": None,
        "sos_days_ago": [],
        "show_brief_today": True,
    }


def _skenario_after_reset() -> dict:
    rng = random.Random(15005)
    riwayat = _riwayat_semester(5, rng)
    return {
        "label": "After reset — decide() dipanggil ulang sesudah Reset",
        "description": "5 catatan biasa, SATU tugas besar (90 menit, sulit) sebagai "
                        "next action awal. run_demo() manggil decide() lagi sesudah "
                        "simulasi 1x kunjungan Reset buat dibandingin.",
        "premium": False,
        "profile": {
            "name": "Alfredo", "age_range": "18-24", "status": ["mahasiswa"],
            "productive_hours": [[19, 23]], "sleep_condition": "cukup",
            "on_medication": "tidak", "overwhelm_triggers": ["deadline"], "custom_triggers": [],
        },
        "favorites": {},
        "mood_history": riwayat,
        "tasks": [
            {"title": "Kerjakan laporan praktikum", "important": True, "difficulty": 3,
             "estimated_minutes": 90, "steps": ["Buka data hasil praktikum"]},
        ],
        "inbox": [],
        "medication": None,
        "sos_days_ago": [],
        "show_brief_today": True,
    }


def _riwayat_mood_rendah_tanpa_neglect(n_hari: int, rng: random.Random) -> list[dict]:
    today = date.today()
    hasil = []
    for offset in range(n_hari):
        entry = _log(3, 3, ["capek"], "Mood lagi nggak enak, tapi masih jalan biasa.",
                     True, True)
        entry["offset"] = offset
        hasil.append(entry)
    return hasil


def _skenario_low_mood_low_workload() -> dict:
    rng = random.Random(16006)
    riwayat = _riwayat_mood_rendah_tanpa_neglect(6, rng)
    return {
        "label": "Mood rendah, beban ringan",
        "description": "6 catatan mood 'lelah' (skor 3) yang stabil rendah TAPI makan/"
                        "istirahat tetap terjaga & TIDAK ADA SOS. 1 tugas kecil (~10 menit) hari ini.",
        "premium": False,
        "profile": {
            "name": "Alfredo", "age_range": "18-24", "status": ["mahasiswa"],
            "productive_hours": [[19, 23]], "sleep_condition": "cukup",
            "on_medication": "tidak", "overwhelm_triggers": ["deadline"], "custom_triggers": [],
        },
        "favorites": {},
        "mood_history": riwayat,
        "tasks": [
            {"title": "Rapikan catatan kuliah hari ini", "important": True, "difficulty": 1,
             "estimated_minutes": 10, "steps": ["Buka catatan yang mau dirapikan"]},
        ],
        "inbox": [],
        "medication": None,
        "sos_days_ago": [],
        "show_brief_today": True,
    }


def _skenario_chaotic_workload() -> dict:
    rng = random.Random(17007)
    riwayat = _riwayat_semester(7, rng)
    return {
        "label": "Chaotic workload — kategori campur, semua kerasa mendesak",
        "description": "7 catatan biasa. 4 tugas kategori beda (kuliah/email/organisasi/"
                        "personal), 3 di antaranya penting+mendesak hari ini.",
        "premium": False,
        "profile": {
            "name": "Alfredo", "age_range": "18-24", "status": ["mahasiswa", "organisasi"],
            "productive_hours": [[19, 23]], "sleep_condition": "cukup",
            "on_medication": "tidak", "overwhelm_triggers": ["tugas_numpuk"], "custom_triggers": [],
        },
        "favorites": {},
        "mood_history": riwayat,
        "tasks": [
            {"title": "Kerjain tugas Kombistek", "important": True, "difficulty": 2,
             "estimated_minutes": 45, "deadline_time": "23:59",
             "steps": ["Selesaiin soal nomor 1-5"]},
            {"title": "Balas email dosen soal revisi", "important": True, "difficulty": 1,
             "estimated_minutes": 10, "deadline_time": "20:00",
             "steps": ["Buka email dosen"]},
            {"title": "Siapin laporan pertanggungjawaban organisasi", "important": True,
             "difficulty": 3, "estimated_minutes": 60, "deadline_time": "23:59",
             "steps": ["Kumpulin data kegiatan"]},
            {"title": "Beresin kamar", "important": False, "difficulty": 1,
             "estimated_minutes": 20, "steps": ["Kumpulin baju kotor ke keranjang"]},
        ],
        "inbox": ["bingung mulai dari mana"],
        "medication": None,
        "sos_days_ago": [],
        "show_brief_today": True,
    }


def _skenario_overdue_recovery() -> dict:
    rng = random.Random(18008)
    riwayat = _riwayat_semester(7, rng)
    return {
        "label": "Overdue recovery — beberapa tugas telat, waktu mepet",
        "description": "7 catatan biasa. 3 tugas OVERDUE (1-3 hari telat), waktu "
                        "tersedia cuma ~25 menit sebelum harus pergi.",
        "premium": False,
        "available_minutes_hint": 25,
        "profile": {
            "name": "Alfredo", "age_range": "18-24", "status": ["mahasiswa"],
            "productive_hours": [[19, 23]], "sleep_condition": "cukup",
            "on_medication": "tidak", "overwhelm_triggers": ["deadline"], "custom_triggers": [],
        },
        "favorites": {},
        "mood_history": riwayat,
        "tasks": [
            {"title": "Kumpulin tugas DDP1 yang telat", "important": True, "difficulty": 3,
             "estimated_minutes": 60, "deadline_date": date.today() - timedelta(days=2),
             "steps": ["Buka file dan cek progres terakhir"]},
            {"title": "Isi absen manual yang kelewat", "important": True, "difficulty": 1,
             "estimated_minutes": 5, "deadline_date": date.today() - timedelta(days=3),
             "steps": ["Buka portal absensi"]},
            {"title": "Balas chat grup kelompok yang telat dibales", "important": False,
             "difficulty": 1, "estimated_minutes": 10,
             "deadline_date": date.today() - timedelta(days=1),
             "steps": ["Buka chat grup"]},
        ],
        "inbox": [],
        "medication": None,
        "sos_days_ago": [],
        "show_brief_today": True,
    }


def _skenario_learning_from_history() -> dict:
    rng = random.Random(19009)
    total_event = 12
    n_senang, n_jenuh = total_event * 2 // 3, total_event // 3
    offsets = rng.sample(range(90), total_event)
    rng.shuffle(offsets)
    hari_event = {o: "senang" for o in offsets[:n_senang]}
    hari_event.update({o: "jenuh" for o in offsets[n_senang:n_senang + n_jenuh]})
    riwayat = _riwayat_semester(90, rng, hari_event=hari_event)
    obat = _obat_take_log(random.Random(19010), hari_event=hari_event, n_hari=90)
    sos_offsets = sorted(o for o, jenis in hari_event.items() if jenis == "jenuh")[:2]

    return {
        "label": "Learning from history — 3 bulan aktif, pola cukup konsisten",
        "description": "90 catatan penuh, 8 hari senang & 4 hari jenuh tersebar acak. "
                        "Cukup buat model_mood/model_overwhelm mulai belajar pola personal.",
        "premium": True,
        "profile": {
            "name": "Alfredo", "age_range": "18-24", "status": ["mahasiswa"],
            "productive_hours": [[16, 18], [20, 24]], "sleep_condition": "cukup",
            "on_medication": "ya", "overwhelm_triggers": ["deadline", "gagal_fokus"],
            "custom_triggers": [],
        },
        "favorites": {
            "musik": "lo-fi hujan", "penyemangat": "pelan-pelan juga tetep jalan",
            "orang": "Rani", "jam_capek": "sore",
        },
        "mood_history": riwayat,
        "tasks": _tugas_mingguan_kuliah(),
        "inbox": ["cari referensi jurnal"],
        "medication": {
            "name": "Concerta 18mg", "pills_left": 15, "per_day": 1,
            "start_date": (date.today() - timedelta(days=90)).isoformat(),
            "take_log": obat,
        },
        "sos_days_ago": sos_offsets,
        "show_brief_today": True,
    }


SCENARIOS: dict[str, dict] = {
    "baru": _skenario_baru(),
    "deadline_stack": _skenario_deadline_stack(),
    "low_energy": _skenario_low_energy(),
    "overwhelmed": _skenario_overwhelmed(),
    "productive_streak": _skenario_productive_streak(),
    "after_reset": _skenario_after_reset(),
    "low_mood_low_workload": _skenario_low_mood_low_workload(),
    "chaotic_workload": _skenario_chaotic_workload(),
    "overdue_recovery": _skenario_overdue_recovery(),
    "learning_from_history": _skenario_learning_from_history(),
}


DEMO_OBJECTIVES: dict[str, dict] = {
    "baru": {
        "demo_title": "Kalem Belum Mengenalmu",
        "story": (
            "User baru pertama kali memakai FocusBuddy. "
            "Belum ada cukup histori untuk membuat kesimpulan personal."
        ),
        "tests": ["cold_start", "honest_uncertainty", "safe_default"],
        "expected": {
            "pattern_confidence": "low",
            "should_not_claim_personal_pattern": True,
            "should_still_offer_next_action": True,
        },
        "demo_objective": {
            "primary": "honest_uncertainty",
            "secondary": ["cold_start", "safe_default"],
            "expected_behavior": [
                "do_not_claim_a_personal_pattern_with_zero_history",
                "still_offer_one_concrete_next_action",
            ],
        },
        "wow": "Kalem tetap membantu meskipun belum punya data dan tidak berpura-pura mengenal user.",
    },
    "deadline_stack": {
        "demo_title": "Tiga Deadline, Waktu Cuma 30 Menit",
        "story": (
            "Besok ada quiz. Malam ini ada tugas yang harus dikumpulkan. "
            "User hanya punya sekitar 30 menit untuk fokus."
        ),
        "tests": ["deadline_priority", "capacity_awareness", "duration_estimation"],
        "expected": {
            "respect_available_time": True,
            "use_minutes_est": True,
            "avoid_large_task_when_capacity_is_low": True,
        },
        "demo_objective": {
            "primary": "capacity_awareness",
            "secondary": ["deadline_priority", "duration_estimation"],
            "expected_behavior": [
                "choose_task_that_fits_available_time",
                "prefer_near_deadline_when_feasible",
                "never_choose_impossible_task_only_because_deadline_is_close",
            ],
        },
        "wow": (
            "FocusBuddy tidak sekadar memilih deadline terdekat. "
            "Ia mempertimbangkan apakah task tersebut muat di waktu yang tersedia."
        ),
    },
    "low_energy": {
        "demo_title": "Energi Rendah, Tapi Tidak Overwhelmed",
        "story": (
            "User beberapa hari terakhir kurang tidur dan energinya turun. "
            "Namun tidak ada pola SOS atau overwhelm yang kuat."
        ),
        "tests": ["energy_signal", "no_false_overwhelm", "reasonable_task_selection"],
        "expected": {
            "do_not_trigger_overwhelm_without_evidence": True,
            "prefer_reasonable_duration": True,
        },
        "demo_objective": {
            "primary": "no_false_overwhelm",
            "secondary": ["energy_signal", "reasonable_task_selection"],
            "expected_behavior": [
                "low_energy_alone_does_not_trigger_pre_escalate",
                "session_length_still_shrinks_to_match_energy",
            ],
        },
        "wow": "Energi rendah tidak otomatis dianggap sebagai kondisi krisis.",
    },
    "overwhelmed": {
        "demo_title": "Terlalu Banyak yang Harus Dikerjakan",
        "story": (
            "Beberapa tugas besar menumpuk dan histori menunjukkan "
            "user sedang lebih mudah overwhelmed."
        ),
        "tests": ["overwhelm_short_circuit", "low_friction_action", "reduced_workload"],
        "expected": {
            "overwhelm_short_circuit": True,
            "next_action_should_be_small": True,
            "should_not_force_large_task": True,
        },
        "demo_objective": {
            "primary": "overwhelm_short_circuit",
            "secondary": ["low_friction_action", "reduced_workload"],
            "expected_behavior": [
                "jeda_didahulukan_daripada_tugas_besar",
                "tidak_ada_tugas_besar_yang_dipaksakan",
            ],
        },
        "wow": (
            "Saat kondisi berat, sistem tidak memaksa user menyelesaikan "
            "seluruh task. Sistem mengecilkan langkah berikutnya."
        ),
    },
    "productive_streak": {
        "demo_title": "Sedang Punya Momentum",
        "story": "User beberapa hari terakhir stabil, energinya baik, dan kapasitas waktunya cukup.",
        "tests": ["positive_state", "capacity_usage", "avoid_over_protection"],
        "expected": {
            "should_not_over_reduce_task": True,
            "can_choose_normal_task": True,
        },
        "demo_objective": {
            "primary": "avoid_over_protection",
            "secondary": ["positive_state", "capacity_usage"],
            "expected_behavior": [
                "session_length_is_not_artificially_shrunk",
                "a_normal_difficulty_task_can_still_be_chosen",
            ],
        },
        "wow": (
            "FocusBuddy tidak selalu menyederhanakan tugas. "
            "Ketika kondisi user mendukung, ia membiarkan user maju normal."
        ),
    },
    "after_reset": {
        "demo_title": "Setelah Reset, Langkah Berikutnya Berubah",
        "story": (
            "User sebelumnya mendapat task besar sebagai next action. "
            "Setelah melakukan Reset, sistem harus mengambil keputusan ulang."
        ),
        "tests": ["reset_recovery", "re_decision", "smaller_next_action"],
        "expected": {
            "decide_called_again": True,
            "next_action_can_change": True,
            "next_action_should_be_less_demanding": True,
        },
        "demo_objective": {
            "primary": "re_decision",
            "secondary": ["reset_recovery", "smaller_next_action"],
            "expected_behavior": [
                "decide_is_re_invoked_after_reset",
                "next_action_becomes_lighter_after_reset",
            ],
        },
        "wow": "Reset bukan sekadar tombol berhenti. Reset mengubah keputusan berikutnya.",
    },
    "low_mood_low_workload": {
        "demo_title": "Mood Rendah, Tapi Beban Ringan",
        "story": "Mood user sedang rendah, tetapi hanya ada satu tugas kecil yang membutuhkan sekitar 10 menit.",
        "tests": ["mood_signal", "avoid_overreaction", "small_task"],
        "expected": {
            "should_not_assume_crisis": True,
            "can_offer_small_action": True,
            "should_not_block_productivity_without_reason": True,
        },
        "demo_objective": {
            "primary": "avoid_overreaction",
            "secondary": ["mood_signal", "small_task"],
            "expected_behavior": [
                "low_mood_alone_does_not_trigger_pre_escalate",
                "a_small_task_is_still_offered",
            ],
        },
        "wow": "Mood rendah tidak otomatis berarti semua aktivitas harus dihentikan.",
    },
    "chaotic_workload": {
        "demo_title": "Semua Terasa Mendesak",
        "story": (
            "Ada tugas kuliah, email dosen, pekerjaan organisasi, "
            "dan satu task personal. User bingung mulai dari mana."
        ),
        "tests": ["mixed_categories", "priority_selection", "duration_estimation"],
        "expected": {
            "choose_one_action": True,
            "consider_priority": True,
            "consider_duration": True,
        },
        "demo_objective": {
            "primary": "priority_selection",
            "secondary": ["mixed_categories", "duration_estimation"],
            "expected_behavior": [
                "exactly_one_concrete_action_is_chosen",
                "chosen_action_is_in_the_highest_priority_quadrant_present",
            ],
        },
        "wow": "FocusBuddy menyaring workload yang berantakan menjadi satu langkah yang bisa langsung dikerjakan.",
    },
    "overdue_recovery": {
        "demo_title": "Tugas Sudah Terlambat",
        "story": "Ada beberapa tugas overdue. User hanya punya 20 sampai 30 menit sebelum harus pergi.",
        "tests": ["overdue_priority", "capacity_awareness", "next_action"],
        "expected": {
            "overdue_tasks_are_candidates": True,
            "respect_available_time": True,
            "avoid_impossible_task": True,
        },
        "demo_objective": {
            "primary": "overdue_priority",
            "secondary": ["capacity_awareness", "next_action"],
            "expected_behavior": [
                "overdue_tasks_are_not_silently_dropped",
                "never_choose_impossible_task_only_because_deadline_is_close",
            ],
        },
        "wow": "Tugas overdue tidak otomatis berarti tugas terbesar harus dikerjakan.",
    },
    "learning_from_history": {
        "demo_title": "Kalem Mulai Mengenal Polamu",
        "story": "User sudah menggunakan aplikasi selama beberapa bulan. Histori menunjukkan pola yang cukup konsisten.",
        "tests": ["personal_history", "mood_prediction", "energy_prediction", "overwhelm_pattern"],
        "expected": {
            "personal_model_can_activate": True,
            "pattern_requires_sufficient_history": True,
        },
        "demo_objective": {
            "primary": "personal_history",
            "secondary": ["mood_prediction", "energy_prediction", "overwhelm_pattern"],
            "expected_behavior": [
                "personal_model_only_activates_after_enough_data",
                "prediction_uses_users_own_history_not_a_generic_default",
            ],
        },
        "wow": "Setelah punya histori yang cukup, respons Kalem mulai menggunakan pola personal user.",
    },
}


def _tugas_kelas_hari_ini() -> list[dict]:
    wd = date.today().weekday()
    return [
        {
            "title": f"Kelas: {matkul} ({mulai}-{selesai})",
            "important": True,
            "difficulty": 1,
            "steps": [f"Siap-siap & masuk kelas jam {mulai}"],
            "deadline_time": mulai,
        }
        for mulai, selesai, matkul in JADWAL_KULIAH.get(wd, [])
    ]


def apply_scenario(key: str) -> str:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from app import clock, storage

    scenario = SCENARIOS[key]
    storage.reset_all_data()

    profile = dict(scenario.get("profile") or {})
    profile["onboarded"] = True
    storage.save_profile(profile)

    for fav_key, value in (scenario.get("favorites") or {}).items():
        storage.set_favorite(fav_key, value)

    state = storage.load_state()

    today = clock.today()
    from datetime import timedelta as _td

    logs = []
    for entry in scenario.get("mood_history") or []:
        offset = int(entry.get("offset", 0))
        day = today - _td(days=offset)
        score = int(entry.get("score", 3))
        logs.append(
            {
                "date": day.isoformat(),
                "mood": _mood_for_score(score),
                "score": score,
                "energy": int(entry.get("energy", 3)),
                "diary": entry.get("diary", ""),
                "tags": [],
                "quick_tags": list(entry.get("tags") or []),
                "ate_today": entry.get("ate"),
                "rested_enough": entry.get("rested"),
                "weekday": day.weekday(),
                "is_weekend": day.weekday() >= 5,
            }
        )
    state["mood_logs"] = logs

    state["reset_events"] = [
        {
            "timestamp": (today - _td(days=d)).isoformat(),
            "date": (today - _td(days=d)).isoformat(),
            "choice": "napas",
            "mood_score": None,
        }
        for d in (scenario.get("sos_days_ago") or [])
    ]

    state["subscription"] = {"is_premium": bool(scenario.get("premium"))}
    state["last_brief_date"] = "" if scenario.get("show_brief_today", True) else today.isoformat()

    storage.save_state(state)

    for task in (scenario.get("tasks") or []) + _tugas_kelas_hari_ini():
        deadline_time = task.get("deadline_time")
        if deadline_time is None:
            deadline_time = "09:00" if task.get("urgent") else ""
        deadline_date = task.get("deadline_date")
        if deadline_date is None:
            deadline_iso = today.isoformat()
        elif hasattr(deadline_date, "isoformat"):
            deadline_iso = deadline_date.isoformat()
        else:
            deadline_iso = str(deadline_date)
        storage.add_task(
            task["title"],
            deadline_iso,
            task.get("important", True),
            steps=[{"text": s, "done": False} for s in (task.get("steps") or [task["title"]])],
            difficulty_est=int(task.get("difficulty", 2)),
            deadline_time=deadline_time,
            menit_est=int(task.get("estimated_minutes", task.get("menit_est", 0)) or 0),
            kategori=task.get("kategori", ""),
            jumlah_unit=task.get("jumlah_unit", 0),
        )

    for note in scenario.get("inbox") or []:
        storage.add_inbox_note(note)

    try:
        import models as kalem_models

        kalem_models.reset_semua()
    except Exception:
        pass

    med = scenario.get("medication")
    if med:
        storage.set_medication(med["name"], med["pills_left"], med.get("per_day", 1))
        st = storage.load_state()
        if "take_log" in med:
            take_log = list(med["take_log"])
            st["medication"]["take_log"] = take_log
            st["medication"]["last_taken"] = take_log[0] if take_log else ""
            st["medication"]["start_date"] = med.get(
                "start_date", (today - _td(days=len(take_log) or 1)).isoformat()
            )
            storage.save_state(st)
        elif med.get("missed_days"):
            missed = int(med["missed_days"])
            st["medication"]["start_date"] = (today - _td(days=missed)).isoformat()
            st["medication"]["take_log"] = []
            st["medication"]["last_taken"] = ""
            storage.save_state(st)

    return scenario.get("label", key)


_DEMO_MARKER = "_demo_generated"
_DEMO_META_KEY = "demo_overlay"
_DEMO_COLLECTIONS = ("mood_logs", "reset_events", "tasks", "inbox")


def _without_demo_entries(state: dict) -> None:
    for collection in _DEMO_COLLECTIONS:
        state[collection] = [
            item
            for item in state.get(collection, [])
            if not (isinstance(item, dict) and item.get(_DEMO_MARKER) is True)
        ]


def _reset_models() -> None:
    try:
        import models as kalem_models

        kalem_models.reset_semua()
    except Exception:
        pass


def demo_overlay_active() -> bool:
    from app import storage

    return isinstance(storage.load_state().get(_DEMO_META_KEY), dict)


def clear_demo_overlay() -> bool:
    from app import storage

    state = storage.load_state()
    metadata = state.get(_DEMO_META_KEY)
    had_overlay = isinstance(metadata, dict)
    before_counts = tuple(len(state.get(key, [])) for key in _DEMO_COLLECTIONS)
    _without_demo_entries(state)
    after_counts = tuple(len(state.get(key, [])) for key in _DEMO_COLLECTIONS)

    if had_overlay:
        state["last_brief_date"] = metadata.get(
            "original_last_brief_date", state.get("last_brief_date", "")
        )
        state.pop(_DEMO_META_KEY, None)

    changed = had_overlay or before_counts != after_counts
    if changed:
        storage.save_state(state)
        _reset_models()
    return changed


def apply_scenario_overlay(key: str) -> str:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from app import clock, storage

    scenario = SCENARIOS[key]
    state = storage.load_state()
    previous_meta = state.get(_DEMO_META_KEY)
    original_last_brief = (
        previous_meta.get("original_last_brief_date", state.get("last_brief_date", ""))
        if isinstance(previous_meta, dict)
        else state.get("last_brief_date", "")
    )

    _without_demo_entries(state)

    today = clock.today()
    from datetime import timedelta as _td

    occupied_dates = {
        str(log.get("date"))
        for log in state.get("mood_logs", [])
        if isinstance(log, dict) and log.get("date")
    }
    demo_logs: list[dict] = []
    for entry in scenario.get("mood_history") or []:
        offset = int(entry.get("offset", 0))
        day = today - _td(days=offset)
        if day.isoformat() in occupied_dates:
            continue
        score = int(entry.get("score", 3))
        demo_logs.append(
            {
                "date": day.isoformat(),
                "mood": _mood_for_score(score),
                "score": score,
                "energy": int(entry.get("energy", 3)),
                "diary": entry.get("diary", ""),
                "tags": [],
                "quick_tags": list(entry.get("tags") or []),
                "ate_today": entry.get("ate"),
                "rested_enough": entry.get("rested"),
                "weekday": day.weekday(),
                "is_weekend": day.weekday() >= 5,
                _DEMO_MARKER: True,
                "_demo_scenario": key,
            }
        )
    state["mood_logs"] = sorted(
        state.get("mood_logs", []) + demo_logs,
        key=lambda log: str(log.get("date", "")),
        reverse=True,
    )

    demo_resets = [
        {
            "timestamp": (today - _td(days=d)).isoformat(),
            "date": (today - _td(days=d)).isoformat(),
            "choice": "napas",
            "mood_score": None,
            _DEMO_MARKER: True,
            "_demo_scenario": key,
        }
        for d in (scenario.get("sos_days_ago") or [])
    ]
    state["reset_events"] = sorted(
        state.get("reset_events", []) + demo_resets,
        key=lambda event: str(event.get("timestamp", event.get("date", ""))),
        reverse=True,
    )

    for task in (scenario.get("tasks") or []) + _tugas_kelas_hari_ini():
        deadline_time = task.get("deadline_time")
        if deadline_time is None:
            deadline_time = "09:00" if task.get("urgent") else ""
        deadline_date = task.get("deadline_date")
        if deadline_date is None:
            deadline_iso = today.isoformat()
        elif hasattr(deadline_date, "isoformat"):
            deadline_iso = deadline_date.isoformat()
        else:
            deadline_iso = str(deadline_date)
        state.setdefault("tasks", []).append(
            {
                "id": str(uuid.uuid4()),
                "title": task["title"],
                "deadline": deadline_iso,
                "deadline_time": deadline_time,
                "important": task.get("important", True),
                "difficulty_est": int(task.get("difficulty", 2)),
                "kategori": task.get("kategori", ""),
                "jumlah_unit": float(task.get("jumlah_unit", 0)),
                "menit_est": int(
                    task.get("estimated_minutes", task.get("menit_est", 0)) or 0
                ),
                "description": "",
                "custom_steps": [],
                "repeat": "none",
                "occurrences": {},
                "steps": [
                    {"text": step, "done": False}
                    for step in (task.get("steps") or [task["title"]])
                ],
                "created_at": clock.now().isoformat(),
                _DEMO_MARKER: True,
                "_demo_scenario": key,
            }
        )

    for note in reversed(scenario.get("inbox") or []):
        state.setdefault("inbox", []).insert(
            0,
            {
                "id": str(uuid.uuid4()),
                "text": str(note).strip(),
                "created_at": clock.now().isoformat(),
                _DEMO_MARKER: True,
                "_demo_scenario": key,
            },
        )

    state["last_brief_date"] = (
        "" if scenario.get("show_brief_today", True) else today.isoformat()
    )
    state[_DEMO_META_KEY] = {
        "scenario": key,
        "applied_at": clock.now().isoformat(),
        "original_last_brief_date": original_last_brief,
    }
    storage.save_state(state)
    _reset_models()
    return scenario.get("label", key)


def _mood_for_score(score: int) -> str:
    return {1: "cemas", 2: "sedih", 3: "lelah", 4: "tenang", 5: "semangat"}.get(score, "tenang")


def list_scenarios() -> list[tuple[str, str, str, str, str]]:
    return [
        (
            key,
            scenario.get("label", key),
            scenario.get("description", ""),
            DEMO_OBJECTIVES.get(key, {}).get("demo_title", scenario.get("label", key)),
            DEMO_OBJECTIVES.get(key, {}).get("wow", ""),
        )
        for key, scenario in SCENARIOS.items()
    ]


def _cek_pattern_confidence(decision: Any, **ctx: Any) -> Optional[str]:
    from models import model_mood, model_overwhelm

    mood_siap = model_mood.status()["siap_model"]
    overwhelm_siap = model_overwhelm.status()["siap"]
    if not mood_siap and not overwhelm_siap:
        return "low"
    if mood_siap and overwhelm_siap:
        return "high"
    return "medium"


def _cek_tidak_klaim_pola_personal(decision: Any, **ctx: Any) -> bool:
    from models import fitur as F
    from models import model_mood

    ramalan = model_mood.ramal(F.bangun_fitur())
    return not ramalan.siap


def _cek_tetap_ada_next_action(decision: Any, **ctx: Any) -> bool:
    return bool(decision.action_label) and decision.kind in (
        "next_action", "med", "calm", "pre_escalate",
    )


def _cek_hormati_waktu_tersedia(decision: Any, **ctx: Any) -> Optional[bool]:
    tersedia = ctx.get("available_minutes")
    if tersedia is None or decision.task is None:
        return None
    return int(decision.task.get("menit_est", 0) or 0) <= tersedia


def _cek_pakai_menit_est(decision: Any, **ctx: Any) -> Optional[bool]:
    if decision.task is None:
        return None
    return int(decision.task.get("menit_est", 0) or 0) > 0


def _cek_hindari_tugas_besar_saat_kapasitas_kecil(decision: Any, **ctx: Any) -> Optional[bool]:
    from app.core.decision_quality import assess_capacity

    tersedia = ctx.get("available_minutes")
    if tersedia is None or decision.task is None:
        return None
    return assess_capacity([decision.task], tersedia).fits


def _cek_tidak_overwhelm_tanpa_bukti(decision: Any, **ctx: Any) -> bool:
    return decision.kind != "pre_escalate"


def _cek_durasi_masuk_akal(decision: Any, **ctx: Any) -> bool:
    return decision.focus_minutes <= 15


def _cek_overwhelm_short_circuit(decision: Any, **ctx: Any) -> bool:
    return decision.kind == "pre_escalate" and decision.action_kind == "reset"


def _cek_next_action_kecil(decision: Any, **ctx: Any) -> bool:
    return decision.action_kind != "focus" or decision.focus_minutes <= 15


def _cek_tidak_paksa_tugas_besar(decision: Any, **ctx: Any) -> bool:
    if decision.action_kind != "focus" or decision.task is None:
        return True
    return int(decision.task.get("menit_est", 0) or 0) <= 45


def _cek_tidak_terlalu_diringankan(decision: Any, **ctx: Any) -> bool:
    return decision.focus_minutes >= 15


def _cek_bisa_pilih_tugas_normal(decision: Any, **ctx: Any) -> bool:
    return decision.kind == "next_action" and decision.action_kind == "focus"


def _cek_decide_dipanggil_lagi(decision: Any, **ctx: Any) -> bool:
    return ctx.get("decision_before") is not None and decision is not None


def _cek_next_action_bisa_berubah(decision: Any, **ctx: Any) -> Optional[bool]:
    sebelum = ctx.get("decision_before")
    if sebelum is None or sebelum.task is None or decision.task is None:
        return None
    return sebelum.task.get("id") != decision.task.get("id")


def _cek_next_action_lebih_ringan(decision: Any, **ctx: Any) -> Optional[bool]:
    sebelum = ctx.get("decision_before")
    if sebelum is None:
        return None
    return decision.focus_minutes < sebelum.focus_minutes


def _cek_bisa_tawarkan_aksi_kecil(decision: Any, **ctx: Any) -> bool:
    return decision.kind == "next_action" and decision.task is not None


def _cek_tidak_blokir_tanpa_alasan(decision: Any, **ctx: Any) -> bool:
    return decision.action_kind == "focus"


def _cek_pilih_satu_aksi(decision: Any, **ctx: Any) -> bool:
    return decision.task is not None and decision.action_kind == "focus"


def _cek_pertimbangkan_prioritas(decision: Any, **ctx: Any) -> Optional[bool]:
    from app import storage
    from app.core.kalem_engine import QUADRANT_PRIORITY

    if decision.task is None:
        return None
    tugas_hari_ini = [t for t in storage.tasks_actionable_today() if not storage.task_is_done(t)]
    if not tugas_hari_ini:
        return None
    ranks = [
        QUADRANT_PRIORITY.index(storage.quadrant_of(t))
        for t in tugas_hari_ini if storage.quadrant_of(t) in QUADRANT_PRIORITY
    ]
    if not ranks:
        return None
    kuadran_terbaik = min(ranks)
    kuadran_dipilih = QUADRANT_PRIORITY.index(storage.quadrant_of(decision.task)) \
        if storage.quadrant_of(decision.task) in QUADRANT_PRIORITY else 99
    return kuadran_dipilih == kuadran_terbaik


def _cek_pertimbangkan_durasi(decision: Any, **ctx: Any) -> Optional[bool]:
    from app import storage

    if decision.task is None:
        return None
    sekuadran = [
        t for t in storage.tasks_actionable_today()
        if not storage.task_is_done(t) and storage.quadrant_of(t) == storage.quadrant_of(decision.task)
    ]
    if len(sekuadran) < 2:
        return None
    difficulty_terendah = min(t.get("difficulty_est", 2) for t in sekuadran)
    return decision.task.get("difficulty_est", 2) == difficulty_terendah


def _cek_overdue_jadi_kandidat(decision: Any, **ctx: Any) -> bool:
    from app import storage

    hari_ini = storage.clock.today().isoformat()
    return any(
        t.get("deadline", hari_ini) < hari_ini
        for t in storage.tasks_actionable_today() if not storage.task_is_done(t)
    )


def _cek_hindari_tugas_mustahil(decision: Any, **ctx: Any) -> Optional[bool]:
    from app.core.decision_quality import assess_capacity

    tersedia = ctx.get("available_minutes")
    if tersedia is None or decision.task is None:
        return None
    return assess_capacity([decision.task], tersedia).fits


def _cek_model_personal_bisa_aktif(decision: Any, **ctx: Any) -> bool:
    from models import model_mood, model_overwhelm

    return bool(model_mood.status()["siap_model"] or model_overwhelm.status()["siap"])


def _cek_butuh_histori_cukup(decision: Any, **ctx: Any) -> bool:
    from models import model_mood

    return model_mood.status()["n_catatan"] >= model_mood.MIN_POLA


_PEMERIKSA: dict[str, Callable[..., Any]] = {
    "pattern_confidence": _cek_pattern_confidence,
    "should_not_claim_personal_pattern": _cek_tidak_klaim_pola_personal,
    "should_still_offer_next_action": _cek_tetap_ada_next_action,
    "respect_available_time": _cek_hormati_waktu_tersedia,
    "use_minutes_est": _cek_pakai_menit_est,
    "avoid_large_task_when_capacity_is_low": _cek_hindari_tugas_besar_saat_kapasitas_kecil,
    "do_not_trigger_overwhelm_without_evidence": _cek_tidak_overwhelm_tanpa_bukti,
    "prefer_reasonable_duration": _cek_durasi_masuk_akal,
    "overwhelm_short_circuit": _cek_overwhelm_short_circuit,
    "next_action_should_be_small": _cek_next_action_kecil,
    "should_not_force_large_task": _cek_tidak_paksa_tugas_besar,
    "should_not_over_reduce_task": _cek_tidak_terlalu_diringankan,
    "can_choose_normal_task": _cek_bisa_pilih_tugas_normal,
    "decide_called_again": _cek_decide_dipanggil_lagi,
    "next_action_can_change": _cek_next_action_bisa_berubah,
    "next_action_should_be_less_demanding": _cek_next_action_lebih_ringan,
    "should_not_assume_crisis": _cek_tidak_overwhelm_tanpa_bukti,
    "can_offer_small_action": _cek_bisa_tawarkan_aksi_kecil,
    "should_not_block_productivity_without_reason": _cek_tidak_blokir_tanpa_alasan,
    "choose_one_action": _cek_pilih_satu_aksi,
    "consider_priority": _cek_pertimbangkan_prioritas,
    "consider_duration": _cek_pertimbangkan_durasi,
    "overdue_tasks_are_candidates": _cek_overdue_jadi_kandidat,
    "avoid_impossible_task": _cek_hindari_tugas_mustahil,
    "personal_model_can_activate": _cek_model_personal_bisa_aktif,
    "pattern_requires_sufficient_history": _cek_butuh_histori_cukup,
}


def evaluate_demo_result(
    key: str,
    decision: Any,
    *,
    decision_before: Optional[Any] = None,
    available_minutes: Optional[int] = None,
) -> dict:
    objective = DEMO_OBJECTIVES[key]
    expected = objective.get("expected", {})
    ctx = {"decision_before": decision_before, "available_minutes": available_minutes}

    result: dict = {
        "scenario": key,
        "title": objective.get("demo_title", key),
        "passed": True,
        "checks": [],
    }

    def catat(name: str, actual: Any, expected_value: Any) -> None:
        if actual is None:
            result["checks"].append({
                "name": name, "expected": expected_value,
                "actual": "(tidak dievaluasi -- konteks kurang)", "passed": None,
            })
            return
        lulus = actual == expected_value
        result["checks"].append({
            "name": name, "expected": expected_value, "actual": actual, "passed": lulus,
        })
        if not lulus:
            result["passed"] = False

    for nama, nilai_diharapkan in expected.items():
        pemeriksa = _PEMERIKSA.get(nama)
        if pemeriksa is None:
            result["checks"].append({
                "name": nama, "expected": nilai_diharapkan,
                "actual": "(belum ada pemeriksa)", "passed": None,
            })
            continue
        aktual = pemeriksa(decision, **ctx)
        catat(nama, aktual, nilai_diharapkan)

    return result


def run_demo(key: str) -> dict:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from app import storage
    from app.core import kalem_engine

    apply_scenario(key)
    available_minutes = SCENARIOS[key].get("available_minutes_hint")

    profile, day = kalem_engine.snapshot()
    day.available_minutes = available_minutes
    decision = kalem_engine.decide(profile, day)
    decision_before = None

    if key == "after_reset":
        decision_before = decision
        storage.add_reset_event("napas")
        profile, day = kalem_engine.snapshot()
        day.available_minutes = available_minutes
        decision = kalem_engine.decide(profile, day)

    hasil = evaluate_demo_result(
        key, decision, decision_before=decision_before, available_minutes=available_minutes,
    )
    hasil["decision"] = {
        "kind": decision.kind,
        "action_kind": decision.action_kind,
        "detail": decision.detail,
        "step_text": decision.step_text,
        "focus_minutes": decision.focus_minutes,
        "task_id": decision.task.get("id") if decision.task else None,
        "task_title": decision.task.get("title") if decision.task else None,
    }
    return hasil


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Skenario yang tersedia:\n")
        for key, label, desc, judul, wow in list_scenarios():
            print(f"  {key:<22} {judul}")
            print(f"  {'':<22} {desc}")
            print(f"  {'':<22} demo point: {wow}\n")
        print("Pakai:")
        print("  python -m app.demo_scenarios <nama_skenario>")
        print("  python -m app.demo_scenarios <nama_skenario> --evaluasi")
    else:
        name = sys.argv[1]
        if name not in SCENARIOS:
            print(f"Skenario '{name}' nggak ada. Pilihan: {', '.join(SCENARIOS)}")
            sys.exit(1)
        if "--evaluasi" in sys.argv:
            hasil = run_demo(name)
            print(f"=== {hasil['title']} ===")
            print(f"decision: {hasil['decision']}\n")
            for c in hasil["checks"]:
                tanda = "?" if c["passed"] is None else ("OK" if c["passed"] else "GAGAL")
                print(f"  [{tanda}] {c['name']}: expected={c['expected']!r} actual={c['actual']!r}")
            print(f"\n{'LULUS' if hasil['passed'] else 'ADA YANG GAGAL'}")
        else:
            print(f"Kepasang: {apply_scenario(name)}")
