"""Bikin & jalanin uji akurasi retrieval `model_pecah`.

KENAPA PERLU ALAT SENDIRI
-------------------------
Ambang kemiripan (`model_pecah.AMBANG_MIRIP`) itu satu angka yang nentuin
dua hal yang saling tarik-menarik:

    ambang ketinggian -> banyak tugas yang sebenernya cocok jadi DITOLAK,
                         dan tiap penolakan = satu panggilan API yang
                         sebenernya nggak perlu (biaya).
    ambang kerendahan -> tugas yang NGGAK nyambung ikut kepungut, dan user
                         dapet langkah yang salah tanpa dikasih tau. Ini
                         yang lebih bahaya: gagal senyap.

Nyetel angka itu pakai perasaan gampang meleset. Skrip ini yang bikin
angkanya bisa DIUKUR.

DUA JENIS QUERY, DUA GUNA BEDA
-------------------------------
1. MUDAH  -- variasi awalan ("kerjain X", "mau X"). Ngukur cakupan dasar.
2. SUSAH  -- parafrase yang HAMPIR NGGAK BERBAGI KATA sama judulnya, mis.
             "kamar gue berantakan banget" -> "Beresin kamar". Ini yang
             mirip cara user beneran nulis, dan ini yang paling jujur
             nunjukkin batas kemampuan pencocokan huruf (TF-IDF n-gram).
3. NEGATIF -- tugas yang JELAS nggak ada di dataset. Harus DITOLAK. Tanpa
             ini, sweep ambang bakal bilang "makin rendah makin bagus",
             padahal itu cuma artefak test set yang isinya positif semua.

JALANIN:
    python tools/bikin_query_uji.py           # ukur di ambang sekarang
    python tools/bikin_query_uji.py --sweep   # coba beberapa ambang
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.muat_dataset_pecah import baca  # noqa: E402

AWALAN = ["", "kerjain ", "mulai ", "mau ", "harus ", "lagi mau ", "belum "]

# Parafrase SUSAH: sengaja dipilih yang nyaris nggak berbagi kata sama
# judulnya, karena itu yang paling sering kejadian di dunia nyata -- user
# nulis keluhannya, bukan nama tugasnya.
SUSAH: list[tuple[str, str]] = [
    ("kamar gue berantakan banget", "Beresin kamar"),
    ("baju numpuk belum dicuci", "Cuci baju"),
    ("piring kotor numpuk di wastafel", "Cuci piring"),
    ("besok ada ujian belum belajar", "Belajar buat ujian"),
    ("dosen minta revisi", "Revisi dari dosen"),
    ("inbox penuh belum dibales", "Beresin inbox email"),
    ("laptop penuh file nggak jelas", "Bersihin file laptop"),
    ("hp penuh memori abis", "Kosongin memori HP"),
    ("harus presentasi minggu depan", "Bikin presentasi"),
    ("belum bayar listrik sama air", "Bayar tagihan"),
    ("stnk mau mati", "Perpanjang STNK"),
    ("kulkas kosong perlu belanja", "Belanja bulanan"),
    ("capek banget pengen berhenti dulu", "Tenangin diri setelah kewalahan"),
    ("udah lama nunda tugas ini", "Mulai lagi setelah nunda"),
    ("besok mau ngapain aja ya", "Rencanain besok"),
    ("skripsi belum kesentuh", "Skripsi bab"),
    ("nyari jurnal buat referensi", "Cari referensi"),
    ("belum bales chat temen", "Balas pesan teman"),
    ("mau minta tambahan waktu ke dosen", "Minta perpanjangan tenggat"),
    ("meja belajar penuh barang", "Beresin meja"),
    ("password gue kayaknya gampang ditebak", "Ganti password"),
    ("tab browser kebuka puluhan", "Rapikan tab browser"),
    ("mau lamar kerja tapi cv lama", "Update CV"),
    ("belum olahraga seminggu", "Olahraga"),
    ("badan kaku duduk terus", "Peregangan"),
    ("susah tidur tiap malem", "Tenangin diri sebelum tidur"),
    ("mau mulai kebiasaan bangun pagi", "Mulai kebiasaan baru"),
    ("duit abis nggak jelas kemana", "Bikin anggaran bulanan"),
    ("mau kirim barang ke temen", "Kirim paket"),
    ("motor udah lama nggak diservis", "Servis kendaraan"),
]

# Tugas yang JELAS nggak ada di dataset -> harus ditolak.
NEGATIF = [
    "ngecat pagar rumah", "latihan gitar lagu baru", "jemput adek di stasiun",
    "bikin kue ulang tahun", "pasang rak dinding", "nyari kos semester depan",
    "daftar lomba futsal", "benerin keran bocor", "ngajarin adek matematika",
    "bikin konten tiktok", "vaksin kucing ke dokter hewan", "latihan drama pentas seni",
    "nanam bunga di halaman", "fitting baju wisuda", "nyari partner badminton",
    "potong rambut ke barbershop", "donor darah di pmi", "ganti ban bocor",
    "bikin origami buat pajangan", "belajar main skateboard",
]


def _uji(rec, queries, ambang):
    from app.kalem_ml import model_pecah as mp

    benar = salah = ditolak = 0
    contoh = []
    for q, target in queries:
        h = mp.cari(q, "", rec, ambang=ambang)
        if not h.ketemu:
            ditolak += 1
            if len(contoh) < 4:
                contoh.append(("DITOLAK", q, target, h.dari_judul, h.skor))
        elif h.dari_judul == target:
            benar += 1
        else:
            salah += 1
            if len(contoh) < 4:
                contoh.append(("SALAH", q, target, h.dari_judul, h.skor))
    return benar, salah, ditolak, contoh


def main() -> None:
    from app.kalem_ml import model_pecah as mp

    rec = [r for r in baca() if r["language"] == "id"]
    if not rec:
        raise SystemExit("Dataset Indonesia kosong.")

    mudah = [(a + r["title"].lower(), r["title"]) for r in rec for a in AWALAN]
    judul_ada = {r["title"] for r in rec}
    susah = [(q, t) for q, t in SUSAH if t in judul_ada]
    hilang = [t for _, t in SUSAH if t not in judul_ada]

    print(f"pola     : {len(rec)}")
    print(f"query    : {len(mudah)} mudah, {len(susah)} susah, {len(NEGATIF)} negatif")
    if hilang:
        print(f"  ! target parafrase nggak ketemu di dataset: {hilang}")
    print()

    if "--sweep" in sys.argv:
        print(f"{'ambang':>7} {'mudah%':>7} {'susah%':>7} {'SALAH':>6} {'neg lolos':>10}")
        print("-" * 42)
        for amb in (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.72, 0.75):
            bm, sm, _, _ = _uji(rec, mudah, amb)
            bs, ss, _, _ = _uji(rec, susah, amb)
            lolos = sum(1 for q in NEGATIF if mp.cari(q, "", rec, ambang=amb).ketemu)
            tanda = " <- skrg" if abs(amb - mp.AMBANG_MIRIP) < 1e-9 else ""
            print(f"{amb:>7.2f} {bm/len(mudah)*100:>6.1f}% {bs/len(susah)*100:>6.1f}% "
                  f"{sm+ss:>6} {lolos:>10}{tanda}")
        return

    t0 = time.time()
    bm, sm, dm, _ = _uji(rec, mudah, mp.AMBANG_MIRIP)
    bs, ss, ds, contoh = _uji(rec, susah, mp.AMBANG_MIRIP)
    lolos = sum(1 for q in NEGATIF if mp.cari(q, "", rec, ambang=mp.AMBANG_MIRIP).ketemu)
    lama = time.time() - t0

    print(f"ambang   : {mp.AMBANG_MIRIP}")
    print(f"MUDAH    : {bm}/{len(mudah)} benar ({bm/len(mudah)*100:.1f}%), "
          f"{sm} salah, {dm} ditolak")
    print(f"SUSAH    : {bs}/{len(susah)} benar ({bs/len(susah)*100:.1f}%), "
          f"{ss} salah, {ds} ditolak")
    print(f"NEGATIF  : {lolos}/{len(NEGATIF)} lolos (harusnya 0)")
    print(f"kecepatan: {lama/(len(mudah)+len(susah))*1000:.1f} ms/query")
    if contoh:
        print("\ncontoh yang meleset di query susah:")
        for jenis, q, target, got, skor in contoh:
            print(f"  [{jenis}] {q!r}")
            print(f"      harusnya {target!r}, dapet {got or '(nol)'!r} (skor {skor:.3f})")


if __name__ == "__main__":
    main()
