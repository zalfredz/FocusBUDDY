"""SettingDemo -- data demo siap pakai buat "Auto Feel".

=============================================================================
FILE INI BUAT KAMU ISI SENDIRI. Nggak ada logika app di sini, cuma data
(plus beberapa generator kecil buat mbangun data itu -- lihat catatan di
bawah soal kenapa nggak semuanya ditulis manual).
=============================================================================

MASALAH YANG DISELESAIN
-----------------------
Model di FocusBuddy (mood pattern, energy/burnout classifier, Morning Brief)
baru kelihatan pinter kalau UDAH ADA HISTORI. Kalau demo pakai akun kosong,
semua fitur bakal jawab "Kalem masih belajar pola kamu" -- jujur, tapi
nggak nunjukkin apa-apa ke juri.

KENAPA ADA GENERATOR, BUKAN CUMA DICT LITERAL
----------------------------------------------
Sebagian skenario di bawah butuh riwayat 90 hari (3 bulan). Nulis 90 baris
mood_history manual per skenario nggak kepraktisan dan gampang salah hitung
tanggal/hari. Jadi `_riwayat_semester()` dan `_obat_take_log()` di bawah
nge-generate riwayat itu dari seed acak yang TETAP (`random.Random(seed)`),
biar tetap ke-reproduce sama tiap kali dipanggil di hari yang sama.

JADWAL KULIAH 1 SEMESTER
-------------------------
Ada satu kendala yang HARUS kepenuhi di semua skenario: jadwal kuliah
(lihat `JADWAL_KULIAH`) dan tugas mingguan yang ngikut jadwal itu (quiz
Kalkulus & MatDis tiap Kamis/Jumat, tugas Kombistek deadline Kamis, diskusi
Manbis mingguan). Ini nggak ditulis ulang di tiap skenario -- `apply_scenario()`
otomatis nambahin tugas kelas HARI INI lewat `_tugas_kelas_hari_ini()`, dan
skenario yang punya beban kuliah aktif tinggal manggil `_tugas_mingguan_kuliah()`.

CARA PAKAI
----------
1. Edit / tambah skenario di SCENARIOS bawah ini.
2. Buka app -> Beranda -> ikon tongkat sihir (Auto Feel) di pojok kanan atas.
3. Pilih skenario -> data langsung kepasang, model langsung punya bahan.

Bisa juga dari terminal:

    python SettingDemo.py                  # lihat daftar skenario
    python SettingDemo.py krisis_sos        # pasang skenario "krisis_sos"

CATATAN PENTING
---------------
- Auto Feel MENIMPA data yang ada. Ini alat demo, bukan buat dipakai harian.
- Skor mood: 1 = paling berat, 5 = paling enak. Energi: 1-6.
- Tiap entri `mood_history` WAJIB punya key `"offset"` (berapa hari lalu,
  0 = hari ini). Dulu ini dihitung dari posisi index di list (harus
  berurutan tanpa bolong); sekarang eksplisit supaya skenario yang jarang
  check-in (ada hari BOLONG, bukan cuma nilainya rendah) bisa dibikin.
- Butuh minimal 5 catatan biar model berani ngomongin pola
  (MIN_LOGS_FOR_PATTERN), dan 10 catatan biar Decision Tree kepakai
  (MIN_LOGS_FOR_MODEL). Skenario di bawah udah ngikutin itu.

DAFTAR 10 KONDISI (nomor ngikutin urutan diskusi, bukan urutan penting)
------------------------------------------------------------------------
  0  "baru"              - user baru banget, belum ada histori sama sekali
  2  "kuliah_2minggu"    - 2 minggu, SUBS OFF, 1 dari 2 minggu berat (Kamis-Jumat numpuk)
  3  "sebulan_off"       - 1 bulan, SUBS OFF, 2-3 dari 4 minggu berat (acak)
  4  "sebulan_on"        - sama seperti di atas, SUBS ON
  5  "3bulan_jenuh_off"  - 3 bulan aktif, SUBS OFF, event senang:jenuh = 1:2
  6  "3bulan_senang_off" - 3 bulan aktif, SUBS OFF, event senang:jenuh = 2:1
  7  "3bulan_jenuh_on"   - sama seperti kondisi 5, SUBS ON
  8  "3bulan_senang_on"  - sama seperti kondisi 6, SUBS ON
  9  "krisis_sos"        - 3 bulan, SOS >5x, kepatuhan obat jelek, kronis berat
  10 "jarang_checkin"    - 1 bulan, cuma 15-20 hari ke-checkin, SOS malah sering
"""
from __future__ import annotations

import random
from datetime import date, timedelta

# =============================================================================
# JADWAL KULIAH -- konstanta bersama, dipakai di SEGALA kondisi demo.
# =============================================================================
# weekday: 0=Senin ... 6=Minggu. Tiap entri: (jam_mulai, jam_selesai, matkul).
JADWAL_KULIAH: dict[int, list[tuple[str, str, str]]] = {
    0: [  # Senin
        ("08:00", "09:40", "Agama Kristen Protestan"),
        ("10:00", "11:40", "Manajemen Bisnis B"),
        ("13:00", "14:40", "Dasar-Dasar Pemrograman 1 (DDP 1) F"),
    ],
    1: [  # Selasa
        ("08:00", "09:40", "Kombinatorika & Statistika (Kombistek) A"),
        ("10:00", "11:40", "Matematika Diskrit 1 (MatDis 1) C"),
        ("13:00", "14:40", "Kalkulus 1 F"),
        ("16:00", "16:50", "Kalkulus 1 F"),
    ],
    2: [  # Rabu
        ("11:00", "11:50", "Manajemen Bisnis B"),
        ("14:00", "15:40", "Dasar-Dasar Pemrograman 1 (DDP 1) F"),
    ],
    3: [  # Kamis
        ("08:00", "08:50", "Kombinatorika & Statistika (Kombistek) A"),
        ("10:00", "10:50", "Matematika Diskrit 1 (MatDis 1) C"),
        ("11:00", "11:50", "Kalkulus 1 F"),
        ("15:00", "16:40", "Dasar-Dasar Pemrograman 1 (DDP 1) F"),
    ],
    4: [  # Jumat
        ("08:00", "08:50", "Matematika Diskrit 1 (MatDis 1) C"),
    ],
    5: [],  # Sabtu
    6: [],  # Minggu
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
    """Tanggal kejadian weekday berikutnya (hari ini kalau kebetulan sama).

    Dipakai buat ngasih deadline tugas mingguan (quiz, dsb) tanggal yang
    masuk akal apa pun hari sebenernya pas demo ini dijalanin.
    """
    today = date.today()
    delta = (target_wd - today.weekday()) % 7
    return today + timedelta(days=delta)


def _tugas_mingguan_kuliah() -> list[dict]:
    """4 tugas rutin yang emang beneran ada tiap minggu di semester ini.

    Dipakai di hampir semua kondisi (kecuali user baru yang belum kejar
    beban ini) biar konsisten sama constraint: jadwal & tugas mingguan
    harus kerasa nyata di semua skenario, bukan cuma yang eksplisit
    nyebut "berat".
    """
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


# =============================================================================
# GENERATOR RIWAYAT -- ganti nulis manual ratusan baris jadi seed + aturan.
# =============================================================================

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
    """Bangun mood_history n_hari ke belakang dari hari ini.

    minggu_berat -> indeks minggu (offset // 7, 0 = minggu ini) yang
                    Kamis-Jumat-nya dibikin berat (quiz/deadline numpuk;
                    ikut aturan umum: hari berat -> kurang tidur & makan
                    sedikit).
    hari_event    -> {offset: "senang"|"jenuh"}, nimpa hari itu SEPENUHNYA.
                    Dipakai buat event acak yang lepas dari rutinitas kuliah.
    hanya_offset  -> kalau diisi, cuma offset di list ini yang dapet
                    catatan (buat skenario yang jarang check-in -- hari
                    yang nggak disebut di sini BENERAN nggak ada log-nya,
                    bukan cuma nilainya netral).
    """
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
            else:  # "jenuh"
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


def _obat_take_log(
    rng: random.Random,
    minggu_berat: frozenset[int] = frozenset(),
    hari_event: dict[int, str] | None = None,
    hanya_offset: list[int] | None = None,
    n_hari: int = 90,
    adherence: float = 0.9,
) -> list[str]:
    """Tanggal obat diminum (terbaru dulu). Skip pas hari berat/jenuh --
    itu representasi "telat/kelewat minum obat" sesuai aturan umum, karena
    skema `take_log` cuma nyimpen TANGGAL (bukan jam), jadi "telat" paling
    jujur diterjemahin jadi "hari itu nggak keabsen"."""
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


# =============================================================================
# SKENARIO DEMO -- 10 kondisi. Tiap fungsi return satu dict skenario;
# SCENARIOS di bawah cuma manggil & ngasih nama.
# =============================================================================


def _kondisi_baru() -> dict:
    """Kondisi 0: user baru banget, belum ada histori sama sekali."""
    return {
        "label": "0 — User baru",
        "description": "Belum ada histori sama sekali. Nunjukin Kalem jujur pas datanya kosong.",
        "premium": False,
        "profile": {
            "name": "Alfredo",
            "age_range": "18-24",
            "status": ["mahasiswa"],
            "productive_hours": [[19, 23]],
            "sleep_condition": "cukup",
            "on_medication": "tidak",
            "overwhelm_triggers": ["deadline"],
            "custom_triggers": [],
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


def _kondisi_2minggu_berat() -> dict:
    """Kondisi 2: dipakai 2 minggu, SUBS OFF, 1 dari 2 minggu berat.

    Minggu ini (offset 0-6, termasuk hari ini) sengaja yang berat -- biar
    Morning Brief demo langsung nunjukin respons ke pola aktif, bukan cuma
    pola yang udah lewat. Minggu lalu (offset 7-13) normal.
    """
    rng = random.Random(2002)
    minggu_berat = frozenset({0})
    riwayat = _riwayat_semester(14, rng, minggu_berat=minggu_berat)

    return {
        "label": "2 — Dipakai 2 minggu, jadwal kuliah berat",
        "description": "14 catatan ngikutin jadwal semester. Kamis-Jumat minggu ini berat "
                        "(quiz + deadline numpuk), minggu lalu normal.",
        "premium": False,
        "profile": {
            "name": "Alfredo",
            "age_range": "18-24",
            "status": ["mahasiswa"],
            "productive_hours": [[19, 23]],
            "sleep_condition": "begadang",
            "on_medication": "tidak",
            "overwhelm_triggers": ["tugas_numpuk", "deadline"],
            "custom_triggers": ["kelas numpuk hari kamis"],
        },
        "favorites": {
            "musik": "lo-fi hujan",
            "snack": "indomie telor",
            "penyemangat": "satu-satu aja, nggak usah buru-buru",
            "warna": "biru",
            "jam_capek": "sore",
        },
        "mood_history": riwayat,
        "tasks": _tugas_mingguan_kuliah(),
        "inbox": ["cari referensi buat tugas DDP1", "email dosen kalkulus soal remedial"],
        "medication": None,
        "sos_days_ago": [1],
        "show_brief_today": True,
    }


def _kondisi_sebulan_random(seed: int, premium: bool, nomor: str) -> dict:
    """Kondisi 3/4: sebulan (30 hari), acak 2-3 dari 4 minggu jadi 'berat'.

    Kondisi 4 = kondisi 3 tapi SUBS ON -- pakai seed beda biar polanya
    nggak identik, cuma strukturnya yang sama.
    """
    rng = random.Random(seed)
    k = rng.choice([2, 3])
    minggu_berat = frozenset(rng.sample(range(4), k))
    riwayat = _riwayat_semester(30, rng, minggu_berat=minggu_berat)
    obat = _obat_take_log(random.Random(seed + 1), minggu_berat=minggu_berat, n_hari=30)

    berat_kamis_jumat = [
        o for o in range(30)
        if (date.today() - timedelta(days=o)).weekday() in (3, 4) and (o // 7) in minggu_berat
    ]
    sos_offset = berat_kamis_jumat[0] if berat_kamis_jumat else 5

    label_subs = "SUBS ON" if premium else "SUBS OFF"
    return {
        "label": f"{nomor} — Sebulan aktif, {len(minggu_berat)} dari 4 minggu berat ({label_subs})",
        "description": f"30 catatan penuh, minggu berat dipilih acak (minggu {sorted(w + 1 for w in minggu_berat)}). "
                        + ("Langganan aktif -- semua fitur premium kebuka." if premium else "Belum langganan."),
        "premium": premium,
        "profile": {
            "name": "Alfredo",
            "age_range": "18-24",
            "status": ["mahasiswa"],
            "productive_hours": [[19, 23]],
            "sleep_condition": "begadang",
            "on_medication": "ya",
            "overwhelm_triggers": ["tugas_numpuk", "deadline", "kurang_tidur"],
            "custom_triggers": ["kelas numpuk hari kamis"],
        },
        "favorites": {
            "musik": "lo-fi hujan",
            "snack": "indomie telor",
            "hobi": "main gitar",
            "penyemangat": "satu-satu aja, nggak usah buru-buru",
            "warna": "lavender" if premium else "sage",
            "gerak": "jalan keliling kos",
            "jam_capek": "sore",
        },
        "mood_history": riwayat,
        "tasks": _tugas_mingguan_kuliah(),
        "inbox": ["cari referensi tugas DDP1"],
        "medication": {
            "name": "Concerta 18mg", "pills_left": 18, "per_day": 1,
            "start_date": (date.today() - timedelta(days=30)).isoformat(),
            "take_log": obat,
        },
        "sos_days_ago": [sos_offset],
        "show_brief_today": True,
    }


def _kondisi_3bulan_event(seed: int, premium: bool, dominan: str, nomor: str) -> dict:
    """Kondisi 5/6/7/8: 3 bulan (90 hari) aktif penuh + event acak
    senang/jenuh yang LEPAS dari rutinitas kuliah biasa.

    dominan="jenuh"  -> rasio senang:jenuh = 1:2 (kondisi 5 & 7)
    dominan="senang" -> rasio senang:jenuh = 2:1 (kondisi 6 & 8)
    Total hari event selalu 12 (< 15, sesuai batas yang diminta).
    """
    rng = random.Random(seed)
    total_event = 12
    if dominan == "jenuh":
        n_senang, n_jenuh = total_event // 3, total_event * 2 // 3  # 4, 8
    else:
        n_senang, n_jenuh = total_event * 2 // 3, total_event // 3  # 8, 4

    offsets = rng.sample(range(90), total_event)
    rng.shuffle(offsets)
    hari_event = {o: "senang" for o in offsets[:n_senang]}
    hari_event.update({o: "jenuh" for o in offsets[n_senang:n_senang + n_jenuh]})

    riwayat = _riwayat_semester(90, rng, hari_event=hari_event)
    obat = _obat_take_log(random.Random(seed + 1), hari_event=hari_event, n_hari=90)
    sos_offsets = sorted(o for o, jenis in hari_event.items() if jenis == "jenuh")[:2]

    label_subs = "SUBS ON" if premium else "SUBS OFF"
    label_rasio = "1:2 (lebih banyak jenuh)" if dominan == "jenuh" else "2:1 (lebih banyak senang)"
    return {
        "label": f"{nomor} — 3 bulan aktif, event {label_rasio} ({label_subs})",
        "description": f"90 catatan penuh, {n_senang} hari senang & {n_jenuh} hari jenuh/overwhelmed "
                        f"tersebar acak ({total_event} total, sisanya stabil). "
                        + ("Langganan aktif." if premium else "Belum langganan."),
        "premium": premium,
        "profile": {
            "name": "Alfredo",
            "age_range": "18-24",
            "status": ["mahasiswa", "freelance"] if premium else ["mahasiswa"],
            "productive_hours": [[16, 18], [20, 24]],
            "sleep_condition": "cukup",
            "on_medication": "ya",
            "overwhelm_triggers": ["deadline", "gagal_fokus"],
            "custom_triggers": [],
        },
        "favorites": {
            "musik": "lo-fi hujan",
            "snack": "es kopi susu",
            "hobi": "masak-masak simpel",
            "tempat": "balkon kos",
            "penyemangat": "pelan-pelan juga tetep jalan",
            "warna": "peach" if dominan == "jenuh" else "sage",
            "orang": "Rani",
            "gerak": "jalan keliling kos",
            "jam_capek": "sore",
        },
        "mood_history": riwayat,
        "tasks": _tugas_mingguan_kuliah(),
        "inbox": ["cari referensi jurnal", "daftar seminar"],
        "medication": {
            "name": "Concerta 18mg", "pills_left": 15, "per_day": 1,
            "start_date": (date.today() - timedelta(days=90)).isoformat(),
            "take_log": obat,
        },
        "sos_days_ago": sos_offsets,
        "show_brief_today": True,
    }


def _kondisi_krisis_sos() -> dict:
    """Kondisi 9: SOS ditekan >5x dalam 3 bulan, kepatuhan obat jelek,
    hampir tiap minggu berat -- beneran udah overwhelmed banget."""
    rng = random.Random(9009)
    minggu_berat = frozenset(range(13))  # semua ~13 minggu dalam 90 hari
    extra_jenuh = rng.sample(range(90), 8)
    senang_days = rng.sample([o for o in range(90) if o not in extra_jenuh], 2)
    hari_event = {o: "jenuh" for o in extra_jenuh}
    hari_event.update({o: "senang" for o in senang_days})

    riwayat = _riwayat_semester(90, rng, minggu_berat=minggu_berat, hari_event=hari_event)
    obat = _obat_take_log(random.Random(9010), minggu_berat=minggu_berat, hari_event=hari_event,
                           n_hari=90, adherence=0.5)  # jarang/suka telat minum obat
    sos_offsets = sorted(extra_jenuh)[:7]  # > 5 kali dalam 3 bulan

    return {
        "label": "9 — Krisis: SOS berulang + obat sering telat",
        "description": "3 bulan, hampir tiap minggu berat, SOS ditekan 7x, kepatuhan obat "
                        "cuma sekitar 50%. Buat nunjukin eskalasi & rujukan.",
        "premium": False,
        "profile": {
            "name": "Alfredo",
            "age_range": "18-24",
            "status": ["mahasiswa"],
            "productive_hours": [[6, 9]],
            "sleep_condition": "susah_tidur",
            "on_medication": "ya",
            "overwhelm_triggers": ["tugas_numpuk", "deadline", "kurang_tidur", "mulai_susah"],
            "custom_triggers": ["takut ketinggalan quiz", "dosen killer"],
        },
        "favorites": {
            "musik": "lo-fi hujan",
            "penyemangat": "nggak apa-apa pelan, yang penting nggak berhenti",
            "warna": "peach",
            "orang": "Rani",
            "gerak": "stretching leher",
            "jam_capek": "sore",
        },
        "mood_history": riwayat,
        "tasks": _tugas_mingguan_kuliah() + [
            {"title": "Kejar 2 minggu tugas Kombistek yang numpuk", "important": True,
             "difficulty": 3, "steps": ["List semua yang ketinggalan", "Mulai dari yang paling gampang"],
             "deadline_date": _hari_depan(3), "deadline_time": "23:59"},
        ],
        "inbox": ["telepon klinik buat kontrol", "minta perpanjangan deadline ke dosen"],
        "medication": {
            "name": "Concerta 18mg", "pills_left": 4, "per_day": 1,
            "start_date": (date.today() - timedelta(days=90)).isoformat(),
            "take_log": obat,
        },
        "sos_days_ago": sos_offsets,
        "show_brief_today": True,
    }


def _kondisi_jarang_checkin() -> dict:
    """Kondisi 10: sebulan, cuma 15-20 dari 30 hari ke-checkin (hari bebas
    acak), diary nyaris kosong, belum isi Favorite -- tapi SOS malah
    sering, termasuk di hari yang SAMA SEKALI nggak ada catatan mood.
    Itu pola "buka app cuma buat pencet Overwhelmed", bukan buat check-in.
    """
    rng = random.Random(10010)
    n_checkin = rng.randint(15, 20)
    offsets_checkin = sorted(rng.sample(range(30), n_checkin))

    # Persona beneran keteteran -- condong jenuh, bukan random rata.
    hari_event = {o: "jenuh" for o in rng.sample(offsets_checkin, max(1, n_checkin * 2 // 3))}
    riwayat = _riwayat_semester(30, rng, hari_event=hari_event, hanya_offset=offsets_checkin)

    # Jarang nulis diary: cuma ~25% hari yang ke-checkin yang ada teksnya.
    tulis_diary = set(rng.sample(offsets_checkin, max(1, len(offsets_checkin) // 4)))
    for entry in riwayat:
        if entry["offset"] not in tulis_diary:
            entry["diary"] = ""

    # SOS lebih sering dari checkin, dan sebagian di hari TANPA mood log.
    sisa_hari = [o for o in range(30) if o not in offsets_checkin]
    sos_dari_checkin = rng.sample(offsets_checkin, min(4, len(offsets_checkin)))
    sos_tanpa_checkin = rng.sample(sisa_hari, min(4, len(sisa_hari)))
    sos_offsets = sorted(set(sos_dari_checkin + sos_tanpa_checkin))

    obat = _obat_take_log(random.Random(10011), hanya_offset=offsets_checkin,
                           hari_event=hari_event, adherence=0.4)

    return {
        "label": "10 — Jarang check-in, sering pencet Overwhelmed",
        "description": f"Cuma {n_checkin}/30 hari ada catatan mood, diary nyaris kosong, "
                        f"Favorite belum diisi -- tapi SOS ({len(sos_offsets)}x) termasuk "
                        "di hari TANPA check-in.",
        "premium": False,
        "profile": {
            "name": "Alfredo",
            "age_range": "18-24",
            "status": ["mahasiswa"],
            "productive_hours": [],
            "sleep_condition": "berantakan",
            "on_medication": "ya",
            "overwhelm_triggers": ["tugas_numpuk", "deadline"],
            "custom_triggers": [],
        },
        "favorites": {},
        "mood_history": riwayat,
        "tasks": _tugas_mingguan_kuliah(),
        "inbox": ["banyak yang ketinggalan, bingung mulai dari mana"],
        "medication": {
            "name": "Concerta 18mg", "pills_left": 6, "per_day": 1,
            "start_date": (date.today() - timedelta(days=30)).isoformat(),
            "take_log": obat,
        },
        "sos_days_ago": sos_offsets,
        "show_brief_today": True,
    }


SCENARIOS: dict[str, dict] = {
    "baru": _kondisi_baru(),
    "kuliah_2minggu": _kondisi_2minggu_berat(),
    "sebulan_off": _kondisi_sebulan_random(3003, False, "3"),
    "sebulan_on": _kondisi_sebulan_random(4004, True, "4"),
    "3bulan_jenuh_off": _kondisi_3bulan_event(5005, False, "jenuh", "5"),
    "3bulan_senang_off": _kondisi_3bulan_event(6006, False, "senang", "6"),
    "3bulan_jenuh_on": _kondisi_3bulan_event(7007, True, "jenuh", "7"),
    "3bulan_senang_on": _kondisi_3bulan_event(8008, True, "senang", "8"),
    "krisis_sos": _kondisi_krisis_sos(),
    "jarang_checkin": _kondisi_jarang_checkin(),
}


# =============================================================================
# Di bawah ini mesinnya -- nggak perlu diubah kecuali mau nambah jenis data.
# =============================================================================


def _tugas_kelas_hari_ini() -> list[dict]:
    """Kelas hari ini jadi tugas -- ini yang bikin jadwal kuliah kepakai
    di SEGALA kondisi demo, bukan cuma yang eksplisit manggil
    `_tugas_mingguan_kuliah()`."""
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
    """Pasang satu skenario ke storage. Return label yang kepasang."""
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

    # --- mood: tiap entri bawa offset-nya sendiri (boleh bolong) ---
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

    # --- SOS ---
    state["reset_events"] = [
        {
            # Bentuknya disamain persis sama storage.add_reset_event().
            "timestamp": (today - _td(days=d)).isoformat(),
            "date": (today - _td(days=d)).isoformat(),
            "choice": "napas",
            "mood_score": None,
        }
        for d in (scenario.get("sos_days_ago") or [])
    ]

    # --- langganan & brief ---
    state["subscription"] = {"is_premium": bool(scenario.get("premium"))}
    state["last_brief_date"] = "" if scenario.get("show_brief_today", True) else today.isoformat()

    storage.save_state(state)

    # --- tugas ---
    # Jadwal kelas HARI INI selalu ditambahin (lihat _tugas_kelas_hari_ini),
    # di atas tugas spesifik skenario. `deadline_date` opsional per tugas
    # (default hari ini); `deadline_time` opsional juga (default akhir
    # hari, atau translasi `urgent: bool` lama kalau ada -- lihat storage.is_urgent).
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
        )

    # --- inbox ---
    for note in scenario.get("inbox") or []:
        storage.add_inbox_note(note)

    # --- lupain model lama ---
    # Auto Feel nimpa seluruh riwayat, jadi model yang udah dilatih dari data
    # sebelumnya harus dibuang. Tanpa ini, skenario "user baru" bisa jawab
    # pakai pola dari skenario sebelumnya yang barusan dipasang.
    try:
        from app import kalem_ml

        kalem_ml.reset_semua()
    except Exception:
        pass

    # --- obat ---
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
            # start_date digeser ke belakang tanpa ngisi take_log: itu persis
            # bentuk "kedaftar sekian hari lalu tapi nggak pernah diabsen".
            missed = int(med["missed_days"])
            st["medication"]["start_date"] = (today - _td(days=missed)).isoformat()
            st["medication"]["take_log"] = []
            st["medication"]["last_taken"] = ""
            storage.save_state(st)

    return scenario.get("label", key)


def _mood_for_score(score: int) -> str:
    # Harus ngikutin buddy.MOOD_SCORE (cemas=1, sedih=2, lelah=3, tenang=4,
    # semangat=5) -- ini kebalikannya.
    return {1: "cemas", 2: "sedih", 3: "lelah", 4: "tenang", 5: "semangat"}.get(score, "tenang")


def list_scenarios() -> list[tuple[str, str, str]]:
    """(key, label, description) buat ditampilin di UI Auto Feel."""
    return [
        (key, s.get("label", key), s.get("description", ""))
        for key, s in SCENARIOS.items()
    ]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Skenario yang tersedia:\n")
        for key, label, desc in list_scenarios():
            print(f"  {key:<20} {label}")
            print(f"  {'':<20} {desc}\n")
        print("Pakai: python SettingDemo.py <nama_skenario>")
    else:
        name = sys.argv[1]
        if name not in SCENARIOS:
            print(f"Skenario '{name}' nggak ada. Pilihan: {', '.join(SCENARIOS)}")
            sys.exit(1)
        print(f"Kepasang: {apply_scenario(name)}")
