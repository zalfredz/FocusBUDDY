"""KALEM ML -- kumpulan model yang bikin Kalem makin kenal user.

PETA MODUL
----------
    fitur.py            LAPISAN FITUR. Satu-satunya tempat sinyal user
                        diubah jadi angka. Semua model baca dari sini.
    riwayat.py          Rekonstruksi fitur per HARI LAMPAU buat melatih --
                        dipisah karena gampang bocor kalau digabung.

    model_durasi.py     Judul tugas -> rentang menit. Dilatih dari
                        DATASET/task_duration_dataset_id_lengkap.csv (499
                        baris) + kecepatan asli user.
    model_mood.py       Ramalan skor mood hari ini, dari data user sendiri.
    model_energi.py     Beban kerja + burnout. Prior sintetis, dikalibrasi
                        pakai rasio penyelesaian user.
    model_overwhelm.py  Risiko kewalahan hari ini. Belajar dari hari-hari
                        user beneran mencet SOS.
    model_penenang.py   Opsi jeda mana yang beneran nolong user ini --
                        diukur dari perubahan mood sesudahnya.
    model_pecah.py      Pungut pecahan tugas lama yang MIRIP -> nol panggilan
                        API. Retrieval, bukan generation (lihat docstring-nya
                        soal kenapa nggak bisa "dilatih" kayak model_durasi).

    ../core/bpom.py     BUKAN model: pencarian ke registri obat BPOM.

ATURAN YANG DIPEGANG SEMUA MODEL DI SINI
----------------------------------------
1. JUJUR SOAL TAHAP. Tiap model punya ambang data minimal. Di bawah itu dia
   ngaku "belum kebaca" atau pakai prior yang ditandai jelas. Nggak ada yang
   ngarang pola dari 3 hari.
2. PRIOR DICAMPUR, BUKAN DIGANTI. Model dari 10 hari data digabung sama
   prior dengan bobot yang naik pelan. Tanpa itu, tebakannya ayun-ayunan
   tiap ada satu hari aneh.
3. KOREKSI CUMA NURUNIN TARGET. Salah nyaranin terlalu ringan ruginya kecil;
   salah nyaranin terlalu berat bikin hari gagal, dan rasa gagalnya nempel.
4. ANGKA MENTAH NGGAK DIPAJANG. Skor risiko, probabilitas, dan faktor
   kalibrasi dipakai buat NGATUR NADA, bukan ditunjukin sebagai nilai rapor.

CARA NAMBAH MODEL BARU
----------------------
Tambah fiturnya di `fitur.bangun_fitur()` (dan `riwayat.KOLOM` kalau butuh
histori), bikin `model_<nama>.py`, ekspor lewat `status()` biar kelihatan di
halaman Pengaturan.
"""
from __future__ import annotations

from app.kalem_ml import (  # noqa: F401
    fitur,
    model_durasi,
    model_energi,
    model_kalem,
    model_mood,
    model_overwhelm,
    model_pecah,
    model_penenang,
    riwayat,
)

__all__ = [
    "fitur",
    "riwayat",
    "model_durasi",
    "model_mood",
    "model_energi",
    "model_kalem",
    "model_overwhelm",
    "model_penenang",
    "model_pecah",
    "status_semua",
    "reset_semua",
]


def status_semua() -> dict:
    """Ringkasan semua model -- dipakai halaman Pengaturan & tes."""
    return {
        "durasi": model_durasi.status(),
        "mood": model_mood.status(),
        "energi": model_energi.status(),
        "kalem": model_kalem.status(),
        "overwhelm": model_overwhelm.status(),
        "penenang": model_penenang.status(),
        "pecah": model_pecah.status(),
    }


def reset_semua() -> None:
    """Lupa semua model yang udah dilatih.

    Wajib dipanggil sesudah data user berubah drastis (reset data, Auto
    Feel), kalau nggak model lama bakal ngasih jawaban dari data yang udah
    nggak ada.
    """
    model_durasi.reset_model()
    model_mood.reset_model()
    model_overwhelm.reset_model()
    model_kalem.reset_model()
