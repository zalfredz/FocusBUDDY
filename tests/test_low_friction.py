"""Evaluasi apakah langkah pertama cukup kecil dan konkret."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATASET = ROOT / "DATASET" / "focusbuddy_dekomposisi_id.csv"
TARGET_RATA = 1.8

SKOR_MANUAL: list[tuple[str, str, int, str]] = [
    ("Baca catatan kuliah", "Buka catatan mata kuliah yang mau dibaca", 2, ""),
    ("Belajar buat ujian", "Buka silabus atau grup kelas dan tulis daftar topik yang bakal diujiin", 2, ""),
    ("Belajar satu bab", "Buka bab yang mau dipelajari", 2, ""),
    ("Bikin flashcard", "Buka catatan kuliah dan tandai 5 istilah pertama yang mau dihafal", 2, ""),
    ("Latihan soal matematika", "Buka buku atau lembar soalnya", 2, ""),
    ("Latihan koding", "Buka editor dan file yang mau dikerjain", 2, ""),
    ("Debug kode tugas", "Jalanin kodenya dan baca pesan errornya", 2, ""),
    ("Baca jurnal", "Buka jurnalnya dan baca abstraknya", 2, ""),
    ("Cari referensi", "Tulis kata kunci pencarian", 2, ""),
    ("Bikin daftar pustaka",
     "Buka draf tulisan dan salin 3 sumber pertama yang udah dikutip ke dokumen baru", 2, ""),
    ("Nulis tinjauan pustaka",
     "Buka folder referensi dan salin 3 judul sumber pertama ke dokumen kerja", 2, ""),
    ("Nentuin topik skripsi", "Tulis 3 bidang yang kamu minati", 2, ""),
    ("Siapin bimbingan", "Buka progres terakhir yang udah dikerjain", 2, ""),
    ("Bikin rencana penelitian",
     "Buka draf proposal dan tulis satu kalimat soal masalah utama yang mau kamu jawab", 2, ""),
    ("Nulis abstrak", "Buka bagian pendahuluan dan kesimpulan", 2, ""),
    ("Nulis pendahuluan", "Buka dokumen dan tulis judul babnya", 2, ""),
    ("Nulis pembahasan", "Buka data hasil penelitian", 2, ""),
    ("Rapikan format tugas", "Baca ketentuan format yang diminta", 2, ""),
    ("Kumpulin tugas", "Cek lagi file yang mau dikumpulin", 2, ""),
    ("Kejar kelas yang bolong",
     "Buka chat kelas dan kirim pesan ke satu teman buat minta catatan hari itu", 2, ""),
    ("Rapikan file kuliah", "Buat folder per mata kuliah", 2, ""),
    ("Siapin tugas kelompok", "Buka grup dan baca pembagian tugasnya", 2, ""),
    ("Latihan presentasi", "Buka slide yang udah jadi", 2, ""),
    ("Bikin jadwal belajar", "Tulis materi apa aja yang perlu dipelajari", 2, ""),
    ("Baca masukan dosen", "Baca semua catatan revisi sekali dulu", 2, ""),
    ("Rencanain kerjaan minggu ini", "Buka kalender dan lihat jadwal yang udah ada", 2, ""),
    ("Siapin rapat", "Baca undangan dan agendanya", 2, ""),
    ("Nulis notulen rapat", "Buka catatan mentah yang tadi ditulis", 2, ""),
    ("Tindak lanjut rapat", "Buka notulen rapatnya", 2, ""),
    ("Beresin inbox email", "Buka inbox dan urutin dari yang terbaru", 2, ""),
    ("Nulis email kerja", "Tulis tujuan emailnya dalam 1 kalimat", 2, ""),
    ("Bikin rencana proyek",
     "Buka dokumen proyek dan tulis satu kalimat soal hasil akhir yang mau dicapai", 2, ""),
    ("Pantau progres proyek", "Buka rencana proyek yang udah dibuat", 2, ""),
    ("Bikin laporan status",
     "Buka file progres terakhir dan salin angka atau status paling baru ke draf laporan", 2, ""),
    ("Review draf kontrak", "Baca sekali dari awal tanpa nyatet", 2, ""),
    ("Bikin presentasi", "Buka slide kosong dan tulis judul buat 3 slide pertama", 2, ""),
    ("Siapin wawancara kerja", "Baca lagi deskripsi pekerjaannya", 2, ""),
    ("Update portofolio", "Buka portofolio yang lama", 2, ""),
    ("Update CV", "Buka CV yang lama", 2, ""),
    ("Lamar kerja", "Baca lagi syarat lowongannya", 2, ""),
    ("Bikin laporan",
     "Buka folder kerja dan salin file data paling baru ke satu folder laporan", 2, ""),
    ("Rapikan spreadsheet", "Buka file dan lihat kolom apa aja yang ada", 2, ""),
    ("Analisis spreadsheet",
     "Buka spreadsheet dan cek baris 1 sampai 10, tandai yang kosong atau salah format", 2, ""),
    ("Siapin workshop", "Buka dokumen workshop dan tulis siapa target pesertanya", 2, ""),
    ("Delegasikan tugas",
     "Buka daftar tugas dan tandai satu tugas yang paling gampang dikerjain orang lain", 2, ""),
    ("Review kerjaan tim", "Buka hasil kerjaan yang mau direview", 2, ""),
    ("Rencanain kerjaan hari ini", "Lihat kalender hari ini", 2, ""),
    ("Siapin telepon klien", "Baca riwayat komunikasi terakhir", 2, ""),
    ("Nulis proposal",
     "Buka dokumen proposal dan tulis satu kalimat soal masalah yang melatarbelakangi idemu", 2, ""),
    ("Rapikan file kerja", "Buat folder per proyek", 2, ""),
]


def _baca_dataset() -> dict[str, str]:
    with DATASET.open(encoding="utf-8-sig", newline="") as f:
        keluar = {}
        for row in csv.DictReader(f):
            judul = (row.get("judul") or "").strip()
            langkah = [s.strip() for s in (row.get("langkah") or "").split("|") if s.strip()]
            if judul and langkah:
                keluar[judul] = langkah[0]
    return keluar


def main() -> int:
    print(f"=== Rubric low-friction first action ({len(SKOR_MANUAL)} entri dinilai manual) ===\n")
    asli = _baca_dataset()

    basi = []
    for judul, langkah_dinilai, skor, catatan in SKOR_MANUAL:
        aktual = asli.get(judul)
        if aktual != langkah_dinilai:
            basi.append((judul, langkah_dinilai, aktual))

    if basi:
        print("[GAGAL] Dataset udah berubah sejak dinilai -- skor ini BASI, perlu dinilai ulang:")
        for judul, lama, aktual in basi:
            print(f"  - [{judul}] dinilai: {lama!r}")
            print(f"    {'sekarang':>8}: {aktual!r}")
        return 1

    for judul, langkah, skor, catatan in SKOR_MANUAL:
        tanda = {0: "[ABSTRAK]", 1: "[ actionable ]", 2: "[ KONKRET ]"}[skor]
        baris = f"  {tanda} ({skor}) [{judul}] {langkah}"
        if catatan:
            baris += f"\n           -- {catatan}"
        print(baris)

    total = sum(skor for _, _, skor, _ in SKOR_MANUAL)
    rata = total / len(SKOR_MANUAL)
    n0 = sum(1 for _, _, skor, _ in SKOR_MANUAL if skor == 0)
    n1 = sum(1 for _, _, skor, _ in SKOR_MANUAL if skor == 1)
    n2 = sum(1 for _, _, skor, _ in SKOR_MANUAL if skor == 2)

    print(f"\nDistribusi: {n2}x skor 2, {n1}x skor 1, {n0}x skor 0 (dari {len(SKOR_MANUAL)})")
    print(f"Rata-rata : {rata:.2f} (target >= {TARGET_RATA})")

    if rata >= TARGET_RATA:
        print("\nLULUS")
        return 0

    print(f"\n[GAGAL] Rata-rata {rata:.2f} di bawah target {TARGET_RATA}. Ini TEMUAN ASLI soal kualitas "
          "dataset, bukan bug skrip ini -- lihat baris berlabel [ actionable ] dan [ABSTRAK] di atas "
          "buat kandidat yang perlu ditulis ulang jadi lebih konkret.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
