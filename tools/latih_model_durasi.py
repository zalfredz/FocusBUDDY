"""Latih model durasi tugas sekali, simpen hasilnya.

KENAPA DIPRA-LATIH
------------------
Latih dari nol makan ~1 detik. Kedengeran kecil, tapi itu jeda yang muncul
persis pas user lagi nambah tugas -- momen paling rawan bikin orang ADHD
kehilangan momentum. Jadi dilatih sekali di sini, runtime tinggal muat.

JALANIN (cuma perlu diulang kalau datasetnya di-update):

    python tools/latih_model_durasi.py

Kalau file hasilnya nggak ada, app tetap jalan normal -- dia bakal latih
sendiri saat pertama dipakai.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import joblib  # noqa: E402

from app.kalem_ml import model_durasi  # noqa: E402


def main() -> None:
    print(f"dataset : {model_durasi.DATASET.name}")
    t0 = time.time()
    vec, hutan, n = model_durasi.latih_dari_dataset()
    if hutan is None:
        raise SystemExit(
            f"Dataset nggak ketemu atau kekecilan (<50 baris).\n"
            f"Taruh di {model_durasi.DATASET}"
        )
    model_durasi.MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"vec": vec, "hutan": hutan, "n": n},
        model_durasi.MODEL_PATH,
        compress=3,
    )
    ukuran = model_durasi.MODEL_PATH.stat().st_size / 1024 / 1024
    print(f"dilatih : {n} baris dalam {time.time() - t0:.1f} detik")
    print(f"keluar  : {model_durasi.MODEL_PATH.relative_to(ROOT)}  ({ukuran:.2f} MB)")

    # Cek muat balik + kecepatan prediksi -- kalau ini lambat, percuma.
    model_durasi.reset_model()
    t0 = time.time()
    contoh = model_durasi.perkirakan("kerjakan 20 soal kalkulus", 3, 8)
    print(f"muat+prediksi pertama: {(time.time() - t0) * 1000:.0f} ms  -> {contoh.rentang}")


if __name__ == "__main__":
    main()
