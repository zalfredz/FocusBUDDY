"""Tes manual model Kalem -- masukin input custom, lihat tiap model jawab apa.

BUKAN pengganti tests/test_regresi.py (itu tes otomatis, pass/fail). Ini
alat buat NGECEK MANUAL: kamu tentuin sendiri kombinasi angka yang mau
dicoba (skor mood, jumlah SOS, tugas mendesak, dll), lalu lihat langsung
output model_mood / model_energi / model_overwhelm / model_durasi /
model_penenang buat kombinasi itu -- tanpa mesti check-in beneran atau
pasang skenario penuh lewat SettingDemo.py.

STORAGE-INDEPENDENT
--------------------
`fitur_manual()` bikin `Fitur` dari `DayState` + profil yang dioper
eksplisit (bukan None). `kalem_ml/fitur.py::bangun_fitur()` cuma jatuh
balik baca ~/.focusbuddy/data.json kalau `day`/`profil` di-None-in. Jadi
skrip ini GAK PERNAH nyentuh data asli kamu.

CARA PAKAI
----------
    python tools/tes_manual_kalem.py                # semua skenario contoh
    python tools/tes_manual_kalem.py overwhelm       # cuma model_overwhelm
    python tools/tes_manual_kalem.py durasi          # cuma model_durasi

Atau import langsung buat eksplorasi bebas (skrip ini, notebook, python -i):

    from tools.tes_manual_kalem import fitur_manual, riwayat_manual
    from app.kalem_ml import model_overwhelm

    f = fitur_manual(n_sos_7h=3, n_sos_3h=2, skor_3h=1.8, streak_abai=4)
    print(model_overwhelm.nilai(f))

Nambah skenario sendiri: tinggal tambah entri di SKENARIO_* di bawah, atau
panggil fitur_manual()/riwayat_manual() langsung.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.kalem_engine import DayState  # noqa: E402
from app.kalem_ml import fitur as F  # noqa: E402
from app.kalem_ml import (  # noqa: E402
    model_durasi,
    model_energi,
    model_mood,
    model_overwhelm,
    model_penenang,
)

# =============================================================================
# PEMBANGUN INPUT -- nggak nyentuh storage sama sekali
# =============================================================================

_NETRAL: dict[str, float] = {
    "umur_idx": 1.0, "n_status": 1.0, "tidur_jam": 7.0,
    "punya_jam_produktif": 0.0, "di_jam_produktif": 0.0, "jam_produktif_diketahui": 0.0,
    "n_pemicu": 0.0,
    "skor_hari_ini": 0.0, "ada_checkin_hari_ini": 0.0,
    "skor_3h": 3.0, "skor_7h": 3.0, "skor_14h": 3.0, "tren_mood": 0.0,
    "energi_terakhir": 3.0, "hari_sejak_checkin": 0.0, "data_mood_basi": 0.0,
    "streak_checkin": 0.0, "n_catatan": 0.0, "n_diary": 0.0,
    "streak_abai": 0.0, "obat_aktif": 0.0, "obat_kelewat": 0.0, "obat_hari_sisa": 99.0,
    "n_tugas_hari_ini": 0.0, "n_belum_selesai": 0.0, "n_mendesak": 0.0, "beban_menit": 0.0,
    "rasio_selesai_7h": 0.5, "ada_data_tugas_7h": 0.0, "umur_tugas_tertua": 0.0, "n_inbox": 0.0,
    "n_sos_7h": 0.0, "n_sos_3h": 0.0, "hari_sejak_sos": 99.0,
    "n_sesi_7h": 0.0, "rasio_sesi_kelar": 0.5, "kalibrasi_waktu": 1.0,
    "n_favorit": 0.0, "punya_penyemangat": 0.0, "punya_orang": 0.0, "punya_gerak": 0.0,
    "di_jam_capek": 0.0,
    "weekday": 0.0, "is_weekend": 0.0, "jam": 12.0,
}


def fitur_manual(logs: list[dict] | None = None, day: DayState | None = None, **override: float) -> F.Fitur:
    """Fitur custom buat satu tes -- isi cuma kolom yang kamu perluin.

    Kolom yang nggak disebut di `override` dipakai dari _NETRAL di atas.
    `logs`/`day` cuma perlu diisi buat nge-tes jalur model yang BELAJAR dari
    histori -- pakai `riwayat_manual()` di bawah. Buat jalur prior/rule-
    based, cukup override angka ringkasannya langsung.
    """
    nilai = dict(_NETRAL)
    nilai.update(override)
    day = day if day is not None else DayState(mood_logs=logs or [])
    return F.Fitur(
        nilai=nilai,
        tanggal=date.today().isoformat(),
        catatan={"logs": logs or [], "day": day, "log_hari_ini": None},
    )


def riwayat_manual(
    hari: list[tuple[int, int, bool | None, bool | None]],
    sos_hari_ago: list[int] | None = None,
) -> DayState:
    """DayState dari daftar (skor, energi, makan, istirahat) per hari.

    index 0 = HARI INI, mundur ke belakang. Butuh minimal 10-12 hari biar
    model_mood/model_overwhelm keluar dari mode prior dan beneran belajar.
    """
    today = date.today()
    logs = []
    for offset, (skor, energi, makan, istirahat) in enumerate(hari):
        d = today - timedelta(days=offset)
        logs.append({
            "date": d.isoformat(), "mood": "x", "score": skor, "energy": energi,
            "diary": "", "tags": [], "quick_tags": [],
            "ate_today": makan, "rested_enough": istirahat,
            "weekday": d.weekday(), "is_weekend": d.weekday() >= 5,
        })
    reset_events = [
        {"timestamp": "", "date": (today - timedelta(days=d)).isoformat(),
         "choice": "napas", "mood_score": None}
        for d in (sos_hari_ago or [])
    ]
    return DayState(mood_logs=logs, reset_events=reset_events)


# =============================================================================
# CETAK HASIL
# =============================================================================


def _judul(teks: str) -> None:
    print(f"\n--- {teks} ---")


def cetak_mood(f: F.Fitur) -> None:
    hasil = model_mood.ramal(f)
    if not hasil.siap:
        print(f"  siap   : False (n_data={hasil.n_data}, belum cukup buat meramal)")
        return
    print(f"  skor   : {hasil.skor:.2f}  ({hasil.label})")
    print(f"  sumber : {hasil.sumber}  (n_data={hasil.n_data})")
    print(f"  alasan : {hasil.alasan}")


def cetak_energi(f: F.Fitur, skor_mood: float | None = None) -> None:
    hasil = model_energi.nilai(f, skor_mood=skor_mood)
    print(f"  label        : {hasil.label}  (level energi disaranin: {hasil.level_energi})")
    print(f"  burnout_risk : {hasil.burnout}")
    if hasil.dikoreksi:
        print(f"  dikoreksi    : {hasil.alasan_koreksi}")
    print(f"  saran        : {hasil.saran}")
    print(f"  alasan       : {hasil.alasan}")


def cetak_overwhelm(f: F.Fitur) -> None:
    hasil = model_overwhelm.nilai(f)
    print(f"  tingkat : {hasil.tingkat}  (skor={hasil.skor:.2f}, sumber={hasil.sumber}, n_data={hasil.n_data})")
    print(f"  alasan  : {hasil.alasan}")


def cetak_durasi(
    judul: str, tempo_hari: float = 7, penting: float = 5,
    kategori: str = "", jumlah: float = 0,
    records: list[dict] | None = None, energi: int | None = None,
) -> None:
    hasil = model_durasi.perkirakan(
        judul, tempo_hari=tempo_hari, penting=penting,
        kategori=kategori, jumlah=jumlah, records=records or [], energi=energi,
    )
    print(f"  judul   : {judul!r}")
    print(f"  rentang : {hasil.rentang}  (titik tengah {hasil.menit} menit, ~{hasil.sesi} sesi fokus)")
    print(f"  sumber  : {hasil.sumber}  (n_personal={hasil.n_personal})")
    print(f"  catatan : {hasil.catatan}")


def cetak_penenang(events: list[dict], logs: list[dict], pemicu: list[str] | None = None) -> None:
    hasil = model_penenang.peringkat(events, logs, pemicu)
    print(f"  urutan  : {hasil.urutan}  (sumber: {hasil.sumber})")
    if hasil.catatan:
        print(f"  catatan : {hasil.catatan}")
    if hasil.manfaat:
        print(f"  manfaat terukur : {hasil.manfaat}")


# =============================================================================
# SKENARIO CONTOH -- edit/tambah sesuka kamu
# =============================================================================


def skenario_mood() -> None:
    _judul("belum ada histori (harus 'belum siap')")
    cetak_mood(fitur_manual())

    _judul("prior rule-based, 3 hari terakhir berat (avg skor 1.3)")
    day = riwayat_manual(hari=[(1, 1, False, False), (1, 2, False, True), (2, 2, True, False)])
    cetak_mood(fitur_manual(day=day, logs=day.mood_logs, skor_hari_ini=1.0))

    _judul("12 hari histori berat berturut-turut (Random Forest aktif)")
    day = riwayat_manual(hari=[(1, 1, False, False)] * 12, sos_hari_ago=[0, 1, 3])
    cetak_mood(fitur_manual(day=day, logs=day.mood_logs))

    _judul("12 hari histori bagus berturut-turut")
    day = riwayat_manual(hari=[(5, 5, True, True)] * 12)
    cetak_mood(fitur_manual(day=day, logs=day.mood_logs))


def skenario_energi() -> None:
    _judul("kondisi netral (user baru, belum ada data)")
    cetak_energi(fitur_manual())

    _judul("tidur kurang + mood rendah + energi abis (burnout klasik)")
    cetak_energi(fitur_manual(tidur_jam=4.0, energi_terakhir=1.0), skor_mood=1.0)

    _judul("4 hari makan/istirahat kelewat (neglect burnout)")
    cetak_energi(fitur_manual(streak_abai=4.0), skor_mood=3.0)

    _judul("obat kelewat 3 hari (turunin ekspektasi, bukan nyuruh)")
    cetak_energi(fitur_manual(obat_aktif=1.0, obat_kelewat=3.0), skor_mood=3.0)

    _judul("minggu ini rasio selesai tugas kecil (dikoreksi turun)")
    cetak_energi(fitur_manual(ada_data_tugas_7h=1.0, rasio_selesai_7h=0.15), skor_mood=4.0)


def skenario_overwhelm() -> None:
    _judul("kondisi tenang, nggak ada sinyal apa pun")
    cetak_overwhelm(fitur_manual())

    _judul("prior: SOS 2x dalam 3 hari + mood rendah + tugas mendesak numpuk")
    cetak_overwhelm(fitur_manual(n_sos_3h=2.0, n_sos_7h=2.0, skor_3h=2.0, n_mendesak=3.0))

    _judul("12 hari histori SOS sering (Logistic Regression aktif)")
    day = riwayat_manual(hari=[(2, 2, False, False)] * 12, sos_hari_ago=[0, 1, 2, 4, 6])
    cetak_overwhelm(fitur_manual(day=day, logs=day.mood_logs, n_sos_3h=2.0, n_sos_7h=3.0))


def skenario_durasi() -> None:
    _judul("judul pendek, tanpa kategori (murni model umum)")
    cetak_durasi("Bikin Skripsi Bab 1", tempo_hari=7, penting=8)

    _judul("deadline besok (lebih mendesak -> penting dinaikin)")
    cetak_durasi("Quiz Kalkulus 1", tempo_hari=0, penting=8)

    _judul("ada kecepatan personal di kategori 'soal' (4 sesi, konsisten cepat)")
    records = [
        {"kategori": "soal", "jumlah_unit": 10, "menit": 18},
        {"kategori": "soal", "jumlah_unit": 15, "menit": 24},
        {"kategori": "soal", "jumlah_unit": 8, "menit": 15},
        {"kategori": "soal", "jumlah_unit": 12, "menit": 20},
    ]
    cetak_durasi("Ngerjain 20 soal MatDis", kategori="soal", jumlah=20, records=records)

    _judul("energi rendah (kalibrasi dari sesi di pita energi sama)")
    records_energi = [
        {"kategori": "nulis", "jumlah_unit": 500, "menit": 60, "energi": 1},
        {"kategori": "nulis", "jumlah_unit": 500, "menit": 55, "energi": 2},
        {"kategori": "nulis", "jumlah_unit": 500, "menit": 58, "energi": 1},
    ]
    cetak_durasi("Nulis 500 kata bab 2", kategori="nulis", jumlah=500,
                 records=records_energi, energi=1)


def skenario_penenang() -> None:
    _judul("belum ada riwayat, ada pemicu 'deadline' waktu onboarding")
    cetak_penenang(events=[], logs=[], pemicu=["deadline"])

    _judul("5x pakai 'napas', konsisten bikin mood naik sesudahnya")
    today = date.today()
    logs = [
        {"date": (today - timedelta(days=i)).isoformat(), "score": s}
        for i, s in enumerate([4, 2, 4, 2, 4, 2, 4, 2, 4, 2])
    ]
    events = [
        {"date": (today - timedelta(days=d)).isoformat(), "choice": "napas"}
        for d in (1, 3, 5, 7, 9)
    ]
    cetak_penenang(events=events, logs=logs)


SKENARIO = {
    "mood": skenario_mood,
    "energi": skenario_energi,
    "overwhelm": skenario_overwhelm,
    "durasi": skenario_durasi,
    "penenang": skenario_penenang,
}

TENTANG = {
    "mood": "model_mood -- \"hari ini kemungkinan bakal kayak gimana?\" -- ramalan skor mood (1-5) dari pola user SENDIRI",
    "energi": "model_energi -- \"beban kerja segimana yang masuk akal?\" -- label rendah/sedang/tinggi + level energi + burnout",
    "overwhelm": "model_overwhelm -- \"hari ini kayaknya bakal berat, nih\" -- risiko butuh halaman jeda hari ini",
    "durasi": "model_durasi -- \"ini makan waktu berapa lama?\" -- rentang menit dari judul tugas + kecepatan personal",
    "penenang": "model_penenang -- \"opsi jeda mana yang beneran nolong?\" -- diukur dari perubahan mood, bukan frekuensi",
}


if __name__ == "__main__":
    dipilih = sys.argv[1] if len(sys.argv) > 1 else None
    if dipilih and dipilih not in SKENARIO:
        print(f"'{dipilih}' bukan pilihan. Pilihan: {', '.join(SKENARIO)}")
        raise SystemExit(1)

    print("=" * 78)
    print("TES MANUAL MODEL KALEM -- storage-independent, nggak nyentuh data asli")
    print("=" * 78)

    for nama, fn in SKENARIO.items():
        if dipilih and nama != dipilih:
            continue
        print(f"\n{'#' * 78}\n# {TENTANG[nama]}\n{'#' * 78}")
        fn()
    print()
