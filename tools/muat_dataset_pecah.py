"""Inspeksi dataset pecah tugas; penulisan ke storage bukan untuk produksi dan wajib flag eksplisit."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT = ROOT / "DATASET" / "focusbuddy_dekomposisi_id.csv"


def baca(path: Path = DEFAULT) -> list[dict]:
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

    _tampilkan(baris)


if __name__ == "__main__":
    main()
