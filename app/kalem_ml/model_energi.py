"""Penilaian beban kerja yang menggabungkan prior dan histori personal."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.energy_predictor import (
    ADVICE_MAP,
    MISSED_MED_THRESHOLD,
    NEGLECT_BURNOUT_THRESHOLD,
    predict_workload,
)
from app.kalem_ml import fitur as F

AMBANG_SELESAI = 0.35
AMBANG_SESI = 0.4

BEBAN_KE_ENERGI = {"rendah": 2, "sedang": 4, "tinggi": 5}

_TURUN = {"tinggi": "sedang", "sedang": "rendah", "rendah": "rendah"}


@dataclass
class SaranBeban:
    label: str
    level_energi: int
    burnout: bool
    saran: str
    dikoreksi: bool = False
    alasan_koreksi: str = ""
    alasan: list[str] = field(default_factory=list)


def nilai(f: Optional[F.Fitur] = None, skor_mood: Optional[float] = None) -> SaranBeban:
    f = f or F.bangun_fitur()

    mood = skor_mood if skor_mood is not None else (
        f["skor_hari_ini"] or f["skor_3h"] or 3.0
    )
    dasar = predict_workload(
        sleep_hours=f["tidur_jam"],
        mood_score=int(round(max(1.0, min(mood, 5.0)))),
        energy_level=int(f["energi_terakhir"] or 3),
        streak=int(f["streak_checkin"]),
        neglect_days=int(f["streak_abai"]),
        missed_med_days=int(f["obat_kelewat"]),
    )

    label = dasar.workload_label
    dikoreksi = False
    alasan_koreksi = ""

    punya_data_tugas = bool(f["ada_data_tugas_7h"])
    if punya_data_tugas and f["rasio_selesai_7h"] < AMBANG_SELESAI and label != "rendah":
        label = _TURUN[label]
        dikoreksi = True
        alasan_koreksi = (
            "Minggu ini yang kelar baru sedikit, jadi target hari ini aku "
            "turunin — bukan karena kamu kurang, tapi biar realistis."
        )
    elif f["n_sesi_7h"] >= 3 and f["rasio_sesi_kelar"] < AMBANG_SESI and label == "tinggi":
        label = "sedang"
        dikoreksi = True
        alasan_koreksi = (
            "Sesi fokus kamu belakangan sering berhenti di tengah, jadi "
            "aku nggak naruh target yang berat dulu."
        )

    alasan: list[str] = []
    if f["streak_abai"] >= NEGLECT_BURNOUT_THRESHOLD:
        alasan.append(f"{int(f['streak_abai'])} hari makan/istirahat kelewat")
    if f["tidur_jam"] < 5.5:
        alasan.append("pola tidur lagi berantakan")
    if f["obat_kelewat"] >= MISSED_MED_THRESHOLD:
        alasan.append(f"obat belum keabsen {int(f['obat_kelewat'])} hari")
    if f["di_jam_capek"]:
        alasan.append("ini jam yang kamu bilang paling capek")

    level = BEBAN_KE_ENERGI.get(label, 3)
    if dasar.burnout_risk:
        level = min(level, 2)
    if f["di_jam_capek"]:
        level = max(1, level - 1)

    saran = ADVICE_MAP[label]
    if dikoreksi:
        saran = f"{ADVICE_MAP[label]} {alasan_koreksi}"
    elif dasar.advice != ADVICE_MAP[dasar.workload_label]:
        saran = dasar.advice

    return SaranBeban(
        label=label,
        level_energi=level,
        burnout=dasar.burnout_risk,
        saran=saran,
        dikoreksi=dikoreksi,
        alasan_koreksi=alasan_koreksi,
        alasan=alasan[:3],
    )


def status() -> dict:
    f = F.bangun_fitur()
    return {
        "sumber_prior": "DecisionTree, 500 baris sintetis",
        "rasio_selesai_7h": round(f["rasio_selesai_7h"], 2),
        "rasio_sesi_kelar": round(f["rasio_sesi_kelar"], 2),
        "kalibrasi_aktif": f["n_sesi_7h"] >= 3 or f["n_tugas_hari_ini"] > 0,
    }
