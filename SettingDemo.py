"""SettingDemo -- data demo siap pakai buat "Auto Feel".

=============================================================================
FILE INI BUAT KAMU ISI SENDIRI. Nggak ada logika app di sini, cuma data.
=============================================================================

MASALAH YANG DISELESAIN
-----------------------
Model di FocusBuddy (mood pattern, energy/burnout classifier, Morning Brief)
baru kelihatan pinter kalau UDAH ADA HISTORI. Kalau demo pakai akun kosong,
semua fitur bakal jawab "Kalem masih belajar pola kamu" -- jujur, tapi
nggak nunjukkin apa-apa ke juri.

Sebelum ada file ini, satu-satunya cara numpuk histori itu: check-in mood
manual -> pencet "Maju 1 hari" -> ulangi 14x. Lama dan gampang salah.

CARA PAKAI
----------
1. Edit / tambah skenario di SCENARIOS bawah ini.
2. Buka app -> Beranda -> ikon tongkat sihir (Auto Feel) di pojok kanan atas.
3. Pilih skenario -> data langsung kepasang, model langsung punya bahan.

Bisa juga dari terminal:

    python SettingDemo.py                  # lihat daftar skenario
    python SettingDemo.py burnout          # pasang skenario "burnout"

CATATAN PENTING
---------------
- Auto Feel MENIMPA data yang ada. Ini alat demo, bukan buat dipakai harian.
- `mood_history` ditulis dari hari TERBARU ke TERLAMA (index 0 = hari ini).
- Skor mood: 1 = paling berat, 5 = paling enak. Energi: 1-6.
- Butuh minimal 5 catatan biar model berani ngomongin pola
  (MIN_LOGS_FOR_PATTERN), dan 10 catatan biar Decision Tree kepakai
  (MIN_LOGS_FOR_MODEL). Skenario di bawah udah ngikutin itu.
"""
from __future__ import annotations

# =============================================================================
# SKENARIO DEMO -- silakan tambah/ubah sesuka kamu
# =============================================================================
#
# Field yang bisa diisi per skenario:
#
#   label            : nama yang muncul di daftar Auto Feel
#   description      : penjelasan singkat, muncul di bawah label
#   premium          : True/False -- status langganan
#   profile          : jawaban onboarding
#                      status         -> list, boleh lebih dari satu pekerjaan
#                      productive_hours -> list rentang jam [[mulai, selesai]],
#                                        jam > 24 artinya lewat tengah malam
#                                        (mis. [20, 25] = 20.00-01.00)
#                      sleep_condition -> cukup | begadang | susah_tidur | berantakan
#                      custom_triggers -> pemicu kewalahan yang diketik sendiri
#   favorites        : isi menu Favorite (lihat storage.FAVORITE_FIELDS)
#   mood_history     : list catatan mood, index 0 = HARI INI, mundur ke belakang
#                      {"score": 1-5, "energy": 1-6, "tags": [...],
#                       "diary": "...", "ate": True/False/None,
#                       "rested": True/False/None}
#   tasks            : tugas hari ini
#                      {"title": ..., "urgent": bool, "important": bool,
#                       "difficulty": 1-3, "steps": ["...", ...]}
#   inbox            : catatan quick capture yang belum jadi tugas
#   medication       : {"name": ..., "pills_left": n, "per_day": n} atau None
#                      opsional "missed_days": n -> obatnya udah kedaftar n hari
#                      lalu tapi NGGAK PERNAH diabsen. Kalem nganggapnya nggak
#                      diminum, jadi ekspektasi hari itu diturunin.
#   sos_days_ago     : list "berapa hari lalu" tombol OVERWHELMED dipencet,
#                      mis. [0, 1, 3] -> hari ini, kemarin, 3 hari lalu
#   show_brief_today : True kalau Morning Brief mau langsung muncul

SCENARIOS: dict[str, dict] = {
    # -------------------------------------------------------------------
    "baru": {
        "label": "User baru",
        "description": "Belum ada histori. Buat nunjukin Kalem jujur pas datanya kurang.",
        "premium": False,
        "profile": {
            "name": "Alfredo",
            "age_range": "18-24",
            "status": ["mahasiswa"],
            "productive_hours": [[19, 24]],
            "sleep_condition": "cukup",
            "on_medication": "tidak",
            "overwhelm_triggers": ["deadline"],
            "custom_triggers": [],
        },
        "favorites": {},
        "mood_history": [],
        "tasks": [
            {"title": "Baca materi kuliah", "urgent": False, "important": True,
             "difficulty": 2, "steps": ["Buka slide minggu ini"]},
        ],
        "inbox": [],
        "medication": None,
        "sos_days_ago": [],
        "show_brief_today": True,
    },

    # -------------------------------------------------------------------
    "stabil": {
        "label": "Dipakai 2 minggu — pola stabil",
        "description": "14 catatan, mood naik-turun wajar. Model udah bisa baca pola mingguan.",
        "premium": False,
        "profile": {
            "name": "Alfredo",
            "age_range": "18-24",
            # Kuliah sambil kerja part-time -- status sekarang boleh lebih dari satu.
            "status": ["mahasiswa", "freelance"],
            # Dua rentang: sore abis kelas, dan malam sampai lewat tengah malam.
            "productive_hours": [[16, 18], [20, 25]],
            "sleep_condition": "cukup",
            "on_medication": "tidak",
            "overwhelm_triggers": ["deadline", "tugas_numpuk"],
            "custom_triggers": ["revisi dosen"],
        },
        "favorites": {
            "musik": "lo-fi hujan",
            "snack": "es kopi susu",
            "hobi": "main gitar",
            "tempat": "balkon kos",
            "penyemangat": "pelan-pelan juga tetep jalan",
            "warna": "sage",
            "gerak": "jalan keliling kos",
            "jam_capek": "sore",
        },
        # 14 hari: weekend (index 5,6,12,13) sengaja lebih tinggi
        "mood_history": [
            {"score": 4, "energy": 4, "tags": ["kuliah"], "ate": True, "rested": True},
            {"score": 3, "energy": 3, "tags": ["kuliah", "kelompok"], "ate": True, "rested": False},
            {"score": 4, "energy": 5, "tags": ["kuliah"], "ate": True, "rested": True},
            {"score": 2, "energy": 2, "tags": ["kelompok"], "diary": "kerja kelompok bikin capek",
             "ate": False, "rested": False},
            {"score": 3, "energy": 3, "tags": ["kuliah"], "ate": True, "rested": True},
            {"score": 5, "energy": 5, "tags": ["istirahat"], "ate": True, "rested": True},
            {"score": 5, "energy": 6, "tags": ["olahraga"], "ate": True, "rested": True},
            {"score": 3, "energy": 3, "tags": ["kuliah"], "ate": True, "rested": True},
            {"score": 4, "energy": 4, "tags": ["kuliah"], "ate": True, "rested": True},
            {"score": 2, "energy": 2, "tags": ["kelompok"], "diary": "presentasi kelompok molor",
             "ate": True, "rested": False},
            {"score": 3, "energy": 4, "tags": ["kuliah"], "ate": True, "rested": True},
            {"score": 4, "energy": 4, "tags": ["kuliah"], "ate": True, "rested": True},
            {"score": 5, "energy": 5, "tags": ["istirahat", "keluarga"], "ate": True, "rested": True},
            {"score": 4, "energy": 5, "tags": ["istirahat"], "ate": True, "rested": True},
        ],
        "tasks": [
            {"title": "Bikin Skripsi Bab 1", "urgent": True, "important": True,
             "difficulty": 3, "steps": ["Buka dokumen skripsi", "Tulis 2 kalimat latar belakang"]},
            {"title": "Balas email dosen", "urgent": False, "important": True,
             "difficulty": 1, "steps": ["Buka inbox"]},
        ],
        "inbox": ["cek jadwal sidang", "beli kado ulang tahun adek"],
        "medication": None,
        "sos_days_ago": [4],
        "show_brief_today": True,
    },

    # -------------------------------------------------------------------
    "burnout": {
        "label": "Pola burnout — SOS berulang",
        "description": "Mood rendah + kurang tidur + SOS sering. Buat nunjukin eskalasi & rujukan.",
        "premium": False,
        "profile": {
            "name": "Alfredo",
            "age_range": "18-24",
            "status": ["kerja"],
            "productive_hours": [[6, 11]],
            # Opsi baru: insomnia beda dari begadang -- begadang itu pilihan.
            "sleep_condition": "susah_tidur",
            "on_medication": "ya",
            "overwhelm_triggers": ["tugas_numpuk", "kurang_tidur", "mulai_susah"],
            "custom_triggers": ["atasan japri malem"],
        },
        "favorites": {
            "musik": "lo-fi hujan",
            "penyemangat": "nggak apa-apa pelan, yang penting nggak berhenti",
            "warna": "peach",
            "orang": "Rani",
            "gerak": "stretching leher",
            "jam_capek": "sore",
        },
        "mood_history": [
            {"score": 1, "energy": 1, "tags": ["kerja"], "diary": "capek banget, deadline numpuk",
             "ate": False, "rested": False},
            {"score": 2, "energy": 2, "tags": ["kerja"], "ate": False, "rested": False},
            {"score": 1, "energy": 1, "tags": ["kerja", "sendirian"], "diary": "cemas terus",
             "ate": False, "rested": False},
            {"score": 2, "energy": 2, "tags": ["kerja"], "ate": True, "rested": False},
            {"score": 1, "energy": 1, "tags": ["kerja"], "ate": False, "rested": False},
            {"score": 2, "energy": 2, "tags": ["kerja"], "ate": True, "rested": False},
            {"score": 2, "energy": 3, "tags": ["istirahat"], "ate": True, "rested": True},
            {"score": 1, "energy": 1, "tags": ["kerja"], "ate": False, "rested": False},
            {"score": 2, "energy": 2, "tags": ["kerja"], "ate": True, "rested": False},
            {"score": 1, "energy": 2, "tags": ["kerja"], "ate": False, "rested": False},
        ],
        "tasks": [
            {"title": "Laporan bulanan", "urgent": True, "important": True,
             "difficulty": 3, "steps": ["Buka file laporan"]},
            {"title": "Balas 20 email", "urgent": True, "important": False,
             "difficulty": 2, "steps": ["Buka inbox", "Balas 3 yang paling penting"]},
            {"title": "Revisi deck presentasi", "urgent": False, "important": True,
             "difficulty": 3, "steps": ["Buka deck"]},
        ],
        "inbox": ["telepon klinik buat kontrol", "bayar listrik"],
        # 4 hari kedaftar, nol absen -> Kalem nurunin ekspektasi & nyebut
        # alasannya di Morning Brief.
        "medication": {"name": "Concerta 18mg", "pills_left": 5, "per_day": 1,
                       "missed_days": 4},
        "sos_days_ago": [0, 1, 2, 4],
        "show_brief_today": True,
    },

    # -------------------------------------------------------------------
    "premium": {
        "label": "Premium — histori 1 bulan",
        "description": "30 catatan + SUBS ON. Buat nunjukin semua fitur premium kebuka.",
        "premium": True,
        "profile": {
            "name": "Alfredo",
            "age_range": "18-24",
            "status": ["mahasiswa", "kerja"],
            "productive_hours": [[6, 9], [20, 25]],
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
            "warna": "lavender",
            "orang": "Rani",
            "gerak": "jalan keliling kos",
            "jam_capek": "sore",
        },
        # 30 hari. Index 2/9/16/23 sengaja rendah -- jaraknya 7 hari, jadi
        # SELALU jatuh di weekday yang sama berapa pun hari ini. (Dulu komentarnya
        # nyebut "Selasa", padahal index 0 = hari ini, jadi namanya ikut geser.)
        "mood_history": [
            {"score": s, "energy": e, "tags": t, "ate": True, "rested": True}
            for s, e, t in [
                (4, 4, ["kuliah"]), (3, 3, ["kuliah"]), (2, 2, ["kelompok"]),
                (4, 4, ["kuliah"]), (3, 4, ["kuliah"]), (5, 5, ["istirahat"]),
                (5, 6, ["olahraga"]), (4, 4, ["kuliah"]), (3, 3, ["kuliah"]),
                (2, 2, ["kelompok"]), (4, 4, ["kuliah"]), (3, 3, ["kuliah"]),
                (5, 5, ["istirahat"]), (4, 5, ["keluarga"]), (4, 4, ["kuliah"]),
                (3, 3, ["kuliah"]), (2, 2, ["kelompok"]), (3, 4, ["kuliah"]),
                (4, 4, ["kuliah"]), (5, 5, ["istirahat"]), (5, 5, ["olahraga"]),
                (3, 3, ["kuliah"]), (4, 4, ["kuliah"]), (2, 2, ["kelompok"]),
                (3, 3, ["kuliah"]), (4, 4, ["kuliah"]), (5, 5, ["istirahat"]),
                (4, 4, ["keluarga"]), (3, 3, ["kuliah"]), (4, 4, ["kuliah"]),
            ]
        ],
        "tasks": [
            {"title": "Bikin Skripsi Bab 2", "urgent": True, "important": True,
             "difficulty": 3, "steps": ["Buka dokumen skripsi", "Baca catatan bimbingan"]},
            {"title": "Beresin kamar", "urgent": False, "important": False,
             "difficulty": 1, "steps": ["Ambil 1 baju kotor"]},
        ],
        "inbox": ["cari referensi jurnal", "daftar seminar"],
        "medication": {"name": "Concerta 18mg", "pills_left": 24, "per_day": 1},
        "sos_days_ago": [3],
        "show_brief_today": True,
    },
}


# =============================================================================
# Di bawah ini mesinnya -- nggak perlu diubah kecuali mau nambah jenis data.
# =============================================================================


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

    # --- mood: index 0 = hari ini, mundur ke belakang ---
    today = clock.today()
    from datetime import timedelta

    logs = []
    for offset, entry in enumerate(scenario.get("mood_history") or []):
        day = today - timedelta(days=offset)
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
            # Dulu di sini pakai kunci "at" yang nggak ada di mana-mana, dan
            # "mikro" yang opsinya udah nggak ada di halaman jeda.
            "timestamp": (today - timedelta(days=d)).isoformat(),
            "date": (today - timedelta(days=d)).isoformat(),
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
    for task in scenario.get("tasks") or []:
        storage.add_task(
            task["title"],
            today.isoformat(),
            task.get("urgent", False),
            task.get("important", True),
            steps=[{"text": s, "done": False} for s in (task.get("steps") or [task["title"]])],
            difficulty_est=int(task.get("difficulty", 2)),
        )

    # --- inbox ---
    for note in scenario.get("inbox") or []:
        storage.add_inbox_note(note)

    # --- lupain model lama ---
    # Auto Feel nimpa seluruh riwayat, jadi model yang udah dilatih dari data
    # sebelumnya harus dibuang. Tanpa ini, skenario "user baru" bisa jawab
    # pakai pola dari skenario "premium" yang barusan dipasang.
    try:
        from app import kalem_ml

        kalem_ml.reset_semua()
    except Exception:
        pass

    # --- obat ---
    med = scenario.get("medication")
    if med:
        storage.set_medication(med["name"], med["pills_left"], med.get("per_day", 1))
        missed = int(med.get("missed_days", 0))
        if missed:
            # start_date digeser ke belakang tanpa ngisi take_log: itu persis
            # bentuk "kedaftar sekian hari lalu tapi nggak pernah diabsen".
            st = storage.load_state()
            st["medication"]["start_date"] = (today - timedelta(days=missed)).isoformat()
            st["medication"]["take_log"] = []
            st["medication"]["last_taken"] = ""
            storage.save_state(st)

    return scenario.get("label", key)


def _mood_for_score(score: int) -> str:
    return {1: "sedih", 2: "lelah", 3: "cemas", 4: "tenang", 5: "semangat"}.get(score, "tenang")


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
            print(f"  {key:<10} {label}")
            print(f"  {'':<10} {desc}\n")
        print("Pakai: python SettingDemo.py <nama_skenario>")
    else:
        name = sys.argv[1]
        if name not in SCENARIOS:
            print(f"Skenario '{name}' nggak ada. Pilihan: {', '.join(SCENARIOS)}")
            sys.exit(1)
        print(f"Kepasang: {apply_scenario(name)}")
