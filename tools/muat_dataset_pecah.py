"""Intip pola pecah tugas dari DATASET/ -- BUKAN loader produksi.

STATUS SEKARANG: TOOL INI NORMALNYA NGGAK PERLU DIJALANIN
-----------------------------------------------------------
Dulu tool ini yang ngisi cold-start: nulis 212 pola dataset ke storage user
biar tugas baru pun langsung kena pungutan tanpa nelpon API. Sekarang
`model_pecah._pola_bawaan()` udah nyuntikin dataset itu OTOMATIS saat
retrieval (`cari()`), langsung dari CSV, TANPA nulis apa pun ke storage.
Itu jalur yang beneran dipakai app -- fresh install udah kepungut dari
pola dataset sejak baris kode pertama jalan, nggak butuh langkah manual.

Jadi default tool ini sekarang cuma buat INTIP ISI DATASET (`--lihat`),
bukan buat dijalanin rutin. Lihat PERINGATAN di bawah soal mode tulis.

PERINGATAN -- MODE TULIS (`--tulis-ke-storage`) BUKAN BUAT PRODUKSI
----------------------------------------------------------------------
Mode ini nulis 212 pola dataset ke `decompose_records` MILIK USER beneran,
lewat `storage.add_decompose_record()`. Itu:

  1. DUPLIKAT sia-sia -- pola yang sama udah kepungut otomatis lewat
     `_pola_bawaan()` tanpa nulis storage sama sekali.
  2. MAKAN 212 dari 300 slot (`storage.MAX_DECOMPOSE_RECORDS`) -- nyisain
     cuma ~88 slot buat pecahan personal/AI yang beneran baru sebelum
     catatan lama mulai kegusur.

Cuma jalanin mode ini kalau kamu SENGAJA lagi eksperimen/debug dan paham
konsekuensinya (misalnya mau lihat pola dataset beneran nangkring di
`storage.get_decompose_records()`). Bukan langkah setup normal.

CUMA BAHASA INDONESIA YANG DIMUAT
----------------------------------
`DEFAULT` di bawah nunjuk ke dataset Indonesia. Dataset Inggris
(`focusbuddy_task_decomposition_dataset_extended.csv`) SENGAJA NGGAK dimuat
ke produksi: app-nya berbahasa Indonesia, dan user yang nulis "beresin kamar"
nggak boleh dapet langkah "Open the notes for the target lecture" cuma gara-
gara maknanya kebetulan deket. File itu disimpan sebagai bahan terjemahan,
bukan sumber langsung.

Penyaringan bahasanya dua lapis: kolom `language` di CSV ikut kesimpen ke
tiap catatan, dan `model_pecah.cari()` cuma mungut catatan sebahasa.

JALANIN:
    python tools/muat_dataset_pecah.py                    # default: intip doang (= --lihat)
    python tools/muat_dataset_pecah.py --lihat             # intip isinya doang
    python tools/muat_dataset_pecah.py --tulis-ke-storage  # PERINGATAN: baca di atas dulu
    python tools/muat_dataset_pecah.py <file.csv>           # ganti sumber, tetap intip doang

FORMAT CSV:
    judul      -- judul tugas, apa adanya kayak user nulis
    deskripsi  -- konteks bebas. BOLEH KOSONG.
    langkah    -- langkah-langkahnya, dipisah tanda "|"
    kategori   -- Akademik | Kerja | Rumah | Administrasi | Digital |
                  Komunikasi | Personal | Perawatan diri
    language   -- "id" | "en". Yang nggak "id" nggak akan kepungut di app.
    sumber     -- kurasi | terjemahan

NAMBAH DATA: tinggal tambah baris. Yang paling berguna itu pola tugas yang
SERING BERULANG di banyak orang -- bukan tugas super spesifik ke satu orang,
itu nggak akan pernah kena cocok buat orang lain. Langkah pertama WAJIB
konkret & ringan (prinsip low-friction initiation): "Buka dokumen skripsi
dan baca bagian terakhir" bukan "Kerjakan skripsi".
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT = ROOT / "DATASET" / "focusbuddy_dekomposisi_id.csv"


def baca(path: Path = DEFAULT) -> list[dict]:
    """Baris CSV -> dict siap simpen. Baris rusak dilewat, bukan bikin mati.

    `utf-8-sig`, bukan `utf-8`: file CSV yang lewat Excel/Sheets sering bawa
    BOM di awal, dan itu bikin nama kolom pertama kebaca sebagai
    '\\ufeffjudul' -- gagal senyap yang susah dilacak.
    """
    if not path.exists():
        return []
    keluar: list[dict] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            judul = (row.get("judul") or "").strip()
            langkah = [s.strip() for s in (row.get("langkah") or "").split("|") if s.strip()]
            if not judul or not langkah:
                continue
            keluar.append({
                "title": judul,
                "description": (row.get("deskripsi") or "").strip(),
                "steps": langkah,
                "language": (row.get("language") or "id").strip(),
                "kategori": (row.get("kategori") or "").strip(),
                "source": "dataset",
            })
    return keluar


def _tampilkan(baris: list[dict]) -> None:
    for r in baris[:15]:
        print(f"\n[{r['kategori']}] {r['title']}")
        for s in r["steps"]:
            print(f"   - {s}")
    sisa = len(baris) - 15
    print(f"\n... dan {sisa} pola lagi." if sisa > 0 else "")
    print(f"{len(baris)} pola total.")


def _tulis_ke_storage(baris: list[dict], path: Path) -> None:
    print(
        "\n"
        "!!! PERINGATAN -- mode tulis BUKAN buat produksi !!!\n"
        f"Ini bakal nulis {len(baris)} pola ke storage user beneran, makan\n"
        "slot dari MAX_DECOMPOSE_RECORDS=300 -- padahal pola ini SUDAH\n"
        "kepungut otomatis lewat model_pecah._pola_bawaan() tanpa nulis\n"
        "storage sama sekali. Cuma lanjut kalau ini eksperimen/debug yang\n"
        "kamu sengaja mau lakuin. Baca docstring di atas kalau belum yakin.\n"
    )
    jawab = input("Ketik 'ya' buat lanjut nulis ke storage: ").strip().lower()
    if jawab != "ya":
        print("Dibatalkan -- nggak ada yang ditulis.")
        return

    from app import storage

    sebelum = len(storage.get_decompose_records())
    dilewat = 0
    for r in baris:
        if r["language"] != "id":
            # Dijaga di sini JUGA, bukan cuma pas retrieval -- biar pola
            # bahasa lain nggak numpuk di storage user tanpa guna.
            dilewat += 1
            continue
        storage.add_decompose_record(
            r["title"], r["description"], r["steps"], r["source"], r["language"]
        )
    sesudah = len(storage.get_decompose_records())

    print(f"\ndataset : {path.name} ({len(baris)} pola)")
    if dilewat:
        print(f"dilewat : {dilewat} pola non-Indonesia (nggak dipakai di app)")
    print(f"catatan : {sebelum} -> {sesudah}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else DEFAULT
    if not path.is_absolute():
        path = ROOT / path

    baris = baca(path)
    if not baris:
        raise SystemExit(f"Dataset kosong / nggak ketemu di {path}")

    if "--tulis-ke-storage" in sys.argv:
        _tulis_ke_storage(baris, path)
        return

    # Default = intip doang, sama kayak --lihat eksplisit. Dataset ini udah
    # kepungut otomatis di runtime app (lihat docstring), jadi nggak ada
    # alasan default-nya nulis ke storage siapa pun.
    _tampilkan(baris)


if __name__ == "__main__":
    main()
