"""Energy & Burnout Predictor.

Rekomendasi beban kerja harian pakai Decision Tree kecil yang dilatih dari
data SINTETIS (lihat generate_synthetic_data) -- app belum punya histori
pengguna riil, jadi ini stand-in heuristik, bukan alat klinis.

Skala energi sengaja 1-6 (bukan 1-5) supaya nggak ada "angka tengah aman":
user harus condong ke sisi rendah (1-3) atau tinggi (4-6).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from sklearn.tree import DecisionTreeClassifier

LABELS = ["rendah", "sedang", "tinggi"]

ENERGY_MIN, ENERGY_MAX = 1, 6

ENERGY_HINTS = {
    1: "Lagi capek banget -- target hari ini cukup satu langkah kecil.",
    2: "Masih berat, tapi bisa gerak dikit.",
    3: "Agak di bawah biasanya.",
    4: "Lumayan bisa diajak kerja.",
    5: "Energi bagus, siap tugas yang lebih berat.",
    6: "Lagi penuh energi -- manfaatin buat yang paling menantang.",
}


def generate_synthetic_data(n: int = 500, seed: int = 42) -> tuple[list[list[float]], list[str]]:
    """Data simulasi: (jam tidur, skor mood 1-5, level energi 1-6, streak)."""
    rng = random.Random(seed)
    X: list[list[float]] = []
    y: list[str] = []
    for _ in range(n):
        sleep_hours = round(rng.uniform(3, 9), 1)
        mood_score = rng.randint(1, 5)
        energy = rng.randint(ENERGY_MIN, ENERGY_MAX)
        streak = rng.randint(0, 10)

        score = (
            (sleep_hours - 3) / 6 * 1.8
            + (mood_score - 1) / 4 * 1.8
            + (energy - 1) / 5 * 2.2
            + min(streak, 5) / 5 * 0.8
        )
        score += rng.uniform(-0.55, 0.55)

        if score < 2.1:
            label = "rendah"
        elif score < 3.9:
            label = "sedang"
        else:
            label = "tinggi"

        X.append([sleep_hours, mood_score, energy, streak])
        y.append(label)
    return X, y


def train_model() -> DecisionTreeClassifier:
    X, y = generate_synthetic_data()
    model = DecisionTreeClassifier(max_depth=4, random_state=42)
    model.fit(X, y)
    return model


_model: Optional[DecisionTreeClassifier] = None


def _get_model() -> DecisionTreeClassifier:
    global _model
    if _model is None:
        _model = train_model()
    return _model


@dataclass
class EnergyPrediction:
    workload_label: str
    burnout_risk: bool
    advice: str


ADVICE_MAP = {
    "rendah": "Hari ini pelan-pelan aja. Satu-dua micro-task ringan udah cukup.",
    "sedang": "Energi kamu cukup buat beberapa tugas. Selingi istirahat tiap sesi.",
    "tinggi": "Energi lagi bagus -- ini waktu yang pas buat tugas yang lebih berat.",
}

# Estimasi jam tidur dari jawaban onboarding (storage.SLEEP_OPTIONS). Kasar
# sengaja -- ini bukan alat pelacak tidur, cuma titik awal biar burnout_risk
# nggak selalu dihitung dari angka netral 7.0 yang bikin syaratnya
# (sleep_hours < 5.5) nggak akan pernah kena.
SLEEP_CONDITION_HOURS = {
    "cukup": 7.0,
    "begadang": 5.0,
    # Insomnia ditaruh di bawah "begadang": begadang itu pilihan (bisa balik
    # normal kapan pun), susah tidur itu nggak. Yang kedua lebih konsisten
    # bikin kurang tidur, jadi ambangnya digeser lebih rendah.
    "susah_tidur": 4.5,
    "berantakan": 4.0,
}


def sleep_hours_for(sleep_condition: str) -> float:
    return SLEEP_CONDITION_HOURS.get(sleep_condition, 7.0)


NEGLECT_BURNOUT_THRESHOLD = 3  # hari berturut-turut "belum makan"/"kurang istirahat"

# Berapa hari obat kelewat sebelum ekspektasi diturunin. 2 hari, bukan 1:
# sekali lupa itu wajar banget dan nggak layak ngubah apa-apa.
MISSED_MED_THRESHOLD = 2

# Label beban diturunin satu tingkat, bukan langsung ke dasar.
_LOWER_LABEL = {"tinggi": "sedang", "sedang": "rendah", "rendah": "rendah"}


def predict_workload(
    sleep_hours: float,
    mood_score: int,
    energy_level: int,
    streak: int = 0,
    neglect_days: int = 0,
    missed_med_days: int = 0,
) -> EnergyPrediction:
    model = _get_model()
    energy_level = max(ENERGY_MIN, min(energy_level, ENERGY_MAX))
    label = str(model.predict([[sleep_hours, mood_score, energy_level, streak]])[0])

    classic_burnout = mood_score <= 2 and sleep_hours < 5.5 and energy_level <= 2
    neglect_burnout = neglect_days >= NEGLECT_BURNOUT_THRESHOLD
    burnout_risk = classic_burnout or neglect_burnout

    # Obat resep kelewat beberapa hari itu penjelasan yang masuk akal kenapa
    # fokus & energi ikut turun. Yang dilakuin cuma NURUNIN EKSPEKTASI hari
    # ini -- bukan nyuruh minum obat, bukan bilang ini penyebabnya. Nyaranin
    # atau ngatur dosis di luar kapasitas app ini, dan itu ranah dokter.
    missed = missed_med_days >= MISSED_MED_THRESHOLD
    if missed:
        label = _LOWER_LABEL.get(label, label)

    advice = ADVICE_MAP[label]
    if classic_burnout:
        advice += (
            " ⚠️ Tanda-tanda burnout kebaca (mood rendah + kurang tidur + energi habis)"
            " -- pertimbangkan istirahat beneran hari ini."
        )
    elif neglect_burnout:
        advice += (
            f" ⚠️ Udah {neglect_days} hari kamu bilang belum makan/istirahat cukup -- "
            "itu juga bagian dari burnout, bukan cuma soal beban kerjaan."
        )

    if missed:
        advice += (
            f" Catatan: obat kamu belum keabsen {missed_med_days} hari terakhir, "
            "jadi target hari ini aku turunin dikit. Bukan nyuruh apa-apa — "
            "kalau ada yang ganjel soal obatnya, itu obrolan sama dokter kamu."
        )

    return EnergyPrediction(workload_label=label, burnout_risk=burnout_risk, advice=advice)


def energy_to_mood_default(mood_score: int) -> int:
    """Tebakan level energi (1-6) dari skor mood, buat auto-fill dari mood terakhir."""
    mapping = {1: 1, 2: 2, 3: 3, 4: 5, 5: 6}
    return mapping.get(mood_score, 3)
