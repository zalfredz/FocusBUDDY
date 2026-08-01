"""Rekonstruksi fitur HARIAN dari riwayat -- bahan latih model perilaku.

MASALAHNYA
----------
`fitur.bangun_fitur()` ngasih snapshot HARI INI. Buat ngelatih model yang
belajar dari kebiasaan user, dibutuhin satu baris per HARI LAMPAU, dengan
nilai yang bener-bener berlaku di hari itu -- bukan nilai hari ini yang
ditempelin ke tanggal lama.

Salah di titik ini bikin kebocoran data (*leakage*): model keliatan akurat
pas dites padahal dia cuma ngintip masa depan.

ATURANNYA
---------
Cuma fitur yang BISA direkonstruksi jujur yang masuk:

    BOLEH  skor mood hari itu, energi, makan/istirahat, hari apa,
           SOS dalam 7 hari SEBELUMNYA, streak abai sampai hari itu,
           jumlah tugas dengan deadline hari itu
    NGGAK  rasio selesai (nggak tau kapan langkahnya dicentang),
           kalibrasi waktu (nggak ada stempel waktu per sesi lama),
           stok obat (cuma nilai sekarang yang disimpan)

Yang "NGGAK" itu tetap dipakai buat prediksi HARI INI, cuma nggak dipakai
buat melatih -- karena nilai historisnya emang nggak ada.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from app import clock, storage

# Urutan kolom fitur latih. Dikunci di sini biar model & prediksi nggak
# pernah ketuker urutannya -- bug yang senyap dan susah ketahuan.
KOLOM = [
    "skor",
    "energi",
    "makan",
    "istirahat",
    "weekday",
    "is_weekend",
    "sos_7h_sebelum",
    "streak_abai",
    "n_tugas",
    "n_mendesak",
]


def _tanggal(teks: str) -> Optional[date]:
    try:
        return date.fromisoformat(teks)
    except (TypeError, ValueError):
        return None


def _tri(nilai) -> float:
    """Tri-state jadi angka: belum dijawab = 0.5, bukan 0.

    Penting: 0 artinya "belum makan", dan itu beda jauh dari "nggak dijawab".
    Nyamain keduanya bakal ngajarin model hal yang salah.
    """
    if nilai is True:
        return 1.0
    if nilai is False:
        return 0.0
    return 0.5


def baris_harian(sampai: Optional[date] = None) -> tuple[list[list[float]], list[dict]]:
    """Satu baris fitur per hari yang ada check-in-nya.

    Return (X, meta). `meta` bawa tanggal + label mentah biar model lain bisa
    bikin target sendiri tanpa ngulang rekonstruksi ini.
    """
    sampai = sampai or clock.today()
    logs = [l for l in storage.get_mood_logs() if l.get("score") is not None]
    sos = storage.get_reset_events()
    tugas = storage.get_tasks()

    tgl_sos: list[date] = sorted(
        d for d in (_tanggal(e.get("date", "")) for e in sos) if d
    )
    hari_sos = set(tgl_sos)

    # Log diurut LAMA -> BARU biar streak abai bisa dihitung maju.
    urut = []
    for log in logs:
        d = _tanggal(log.get("date", ""))
        if d and d <= sampai:
            urut.append((d, log))
    urut.sort(key=lambda p: p[0])

    X: list[list[float]] = []
    meta: list[dict] = []
    streak_abai = 0

    for d, log in urut:
        makan, istirahat = log.get("ate_today"), log.get("rested_enough")
        # Streak abai dihitung MAJU, pakai keadaan sampai hari itu doang.
        if makan is None and istirahat is None:
            pass                      # nggak dijawab: streak nggak berubah
        elif makan is False or istirahat is False:
            streak_abai += 1
        else:
            streak_abai = 0

        sebelum = d - timedelta(days=7)
        sos_sebelum = sum(1 for s in tgl_sos if sebelum <= s < d)

        iso = d.isoformat()
        tugas_hari = [t for t in tugas if t.get("deadline") == iso]
        mendesak = [t for t in tugas_hari if t.get("urgent")]

        X.append([
            float(log["score"]),
            float(log.get("energy") or 3),
            _tri(makan),
            _tri(istirahat),
            float(d.weekday()),
            1.0 if d.weekday() >= 5 else 0.0,
            float(sos_sebelum),
            float(streak_abai),
            float(len(tugas_hari)),
            float(len(mendesak)),
        ])
        meta.append({
            "tanggal": iso,
            "skor": log["score"],
            "ada_sos": iso in {s.isoformat() for s in hari_sos},
        })

    return X, meta


def baris_hari_ini(fitur) -> list[float]:
    """Baris fitur buat HARI INI, urutan kolomnya sama persis kayak latih.

    Diambil dari snapshot `fitur.Fitur` supaya definisinya nggak kepisah --
    tapi urutannya tetap dikunci lewat KOLOM di atas.
    """
    log = fitur.catatan.get("log_hari_ini") or {}
    return [
        float(log.get("score") or fitur["skor_7h"]),
        float(log.get("energy") or fitur["energi_terakhir"]),
        _tri(log.get("ate_today")),
        _tri(log.get("rested_enough")),
        fitur["weekday"],
        fitur["is_weekend"],
        fitur["n_sos_7h"],
        fitur["streak_abai"],
        fitur["n_tugas_hari_ini"],
        fitur["n_mendesak"],
    ]
