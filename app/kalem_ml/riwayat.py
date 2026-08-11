"""Rekonstruksi fitur historis tanpa mengarang data pada hari kosong."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from app import clock, storage

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
    if nilai is True:
        return 1.0
    if nilai is False:
        return 0.0
    return 0.5


def sidik_jari(X: list[list[float]], meta: list[dict]) -> str:
    import hashlib

    bahan = "|".join(
        f"{m['tanggal']}:{m['skor']}:{int(m['ada_sos'])}" for m in meta
    )
    return f"{len(X)}:{hashlib.sha256(bahan.encode()).hexdigest()[:16]}"


def baris_harian(
    sampai: Optional[date] = None, day: Any = None
) -> tuple[list[list[float]], list[dict]]:
    sampai = sampai or clock.today()
    if day is not None:
        semua_log, sos, tugas = day.mood_logs, day.reset_events, day.all_tasks
    else:
        semua_log, sos, tugas = (
            storage.get_mood_logs(),
            storage.get_reset_events(),
            storage.get_tasks(),
        )
    logs = [l for l in semua_log if l.get("score") is not None]

    tgl_sos: list[date] = sorted(
        d for d in (_tanggal(e.get("date", "")) for e in sos) if d
    )
    hari_sos = set(tgl_sos)

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
        if makan is None and istirahat is None:
            pass
        elif makan is False or istirahat is False:
            streak_abai += 1
        else:
            streak_abai = 0

        sebelum = d - timedelta(days=7)
        sos_sebelum = sum(1 for s in tgl_sos if sebelum <= s < d)

        iso = d.isoformat()
        tugas_hari = [t for t in tugas if t.get("deadline") == iso]
        akhir_hari = datetime(d.year, d.month, d.day, 23, 59)
        mendesak = [t for t in tugas_hari if storage.is_urgent(t, akhir_hari)]

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
