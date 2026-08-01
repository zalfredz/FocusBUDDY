"""Model pola mood personal.

Beda dari Energy Predictor (yang dilatih dari data sintetis), model ini
belajar HANYA dari data user sendiri: mood per hari, weekday vs weekend,
dan tag aktivitas dari diary. Makin lama dipakai, makin banyak datanya.

Karena itu model ini sengaja punya tahap: di bawah MIN_LOGS_FOR_PATTERN
dia jujur bilang "masih belajar" daripada ngarang pola dari 2-3 entri.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sklearn.tree import DecisionTreeRegressor

from app import clock

MIN_LOGS_FOR_PATTERN = 5   # minimal entri sebelum berani ngomongin pola
MIN_LOGS_FOR_MODEL = 10    # minimal entri sebelum pakai Decision Tree
MIN_PER_DAYTYPE = 2        # minimal entri per tipe hari buat banding weekday/weekend

DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "aku", "saya", "gue", "gua",
    "banget", "aja", "udah", "sudah", "lagi", "buat", "sama", "juga", "nggak",
    "gak", "tidak", "bisa", "ada", "untuk", "tapi", "kalau", "biar", "jadi",
    "sih", "deh", "kok", "pas", "abis", "habis", "terus", "trus", "gitu", "hari",
    "ya", "nya", "dengan", "karena", "masih", "belum", "akan", "pada", "dalam",
}


# Tag cepat: dipencet dalam hitungan detik, tanpa harus nulis cerita.
# Ini yang bikin data tetap masuk di hari-hari user males ngetik -- pola
# yang paling dipakai app journaling sukses (Daylio) bukan yang paling
# ekspresif nulisnya, tapi yang paling gampang diisi tiap hari.
QUICK_TAGS = {
    "kuliah": "Kuliah",
    "kerja": "Kerja",
    "kelompok": "Kerja kelompok",
    "keluarga": "Keluarga",
    "sosial": "Ketemu orang",
    "sendirian": "Sendirian",
    "olahraga": "Gerak badan",
    "istirahat": "Istirahat",
}

# Kamus kata kunci terbatas -- sengaja BUKAN sentiment analysis penuh.
# Cukup cocokin ke daftar tertutup biar hasilnya bisa dijelasin, dan
# dipakai sebagai sinyal tambahan buat Energy/Burnout Classifier.
KEYWORD_MAP = {
    "capek": ["capek", "lelah", "ngantuk", "letih", "drained", "burnout"],
    "deadline": ["deadline", "dikejar", "mepet", "telat", "buru"],
    "cemas": ["cemas", "takut", "khawatir", "panik", "gelisah", "overthinking"],
    "senang": ["senang", "seneng", "lega", "bahagia", "puas", "bangga"],
    "marah": ["marah", "kesel", "jengkel", "sebel"],
    "sendiri": ["sendiri", "sepi", "kesepian"],
    "produktif": ["produktif", "selesai", "kelar", "beres", "berhasil"],
}


def extract_keywords(diary_text: str) -> list[str]:
    """Cocokin cerita ke kamus tertutup di atas. Return nama kategorinya."""
    text = (diary_text or "").lower()
    return [key for key, words in KEYWORD_MAP.items() if any(w in text for w in words)]


def recurring_tag_prompt(logs: list[dict], min_count: int = 2) -> Optional[str]:
    """Pertanyaan lanjutan kalau ada tag yang sering muncul bareng mood rendah.

    Bikin Kalem kelihatan 'inget' hal spesifik dari entri sebelumnya, bukan
    nanya generik terus -- ini yang bikin app AI journaling kerasa personal.
    """
    paired: dict[str, list[int]] = defaultdict(list)
    for log in logs:
        score = log.get("score")
        if score is None:
            continue
        for tag in (log.get("quick_tags") or []):
            paired[tag].append(score)

    for tag, scores in sorted(paired.items(), key=lambda kv: len(kv[1]), reverse=True):
        if len(scores) >= min_count and sum(scores) / len(scores) <= 3.0:
            label = QUICK_TAGS.get(tag, tag).lower()
            return f"Tiap kali kamu nandain '{label}', mood kamu cenderung turun. Lagi ada apa di situ?"
    return None


def neglect_streak(logs: list[dict]) -> int:
    """Berapa kali CEK-IN terakhir berturut-turut user bilang 'belum makan'
    atau 'kurang istirahat'. Dipakai buat nambahin sinyal burnout_risk di
    energy_predictor -- BUKAN buat ditampilin sebagai streak yang bisa putus
    (itu justru yang mau kita hindari, lihat evaluasi ide 'Eat & Rest Well').

    `logs` diasumsikan urut terbaru dulu (kebiasaan add_mood_log: insert(0)).
    Hari yang kedua toggle-nya nggak dijawab (None, None) dilewatin -- nggak
    mutusin streak, karena jawabnya emang opsional.
    """
    streak = 0
    for log in logs:
        ate = log.get("ate_today")
        rested = log.get("rested_enough")
        if ate is None and rested is None:
            continue
        if ate is False or rested is False:
            streak += 1
        else:
            break
    return streak


def checkin_streak(logs: list[dict], today: Optional[date] = None) -> int:
    """Berapa hari berturut-turut user check-in, dihitung mundur dari hari ini.

    Ini yang dimaksud fitur `streak` di energy_predictor: MOMENTUM, angka
    kecil 0-10 yang naik kalau orangnya lagi konsisten.

    Sebelum ini halaman Mood ngirim "jumlah tugas yang pernah selesai" ke
    situ -- angka yang naik terus tanpa batas dan artinya beda total. Efeknya
    kebalik: makin banyak tugas kelar, makin model nyaranin beban BERAT justru
    pas mood & tidur user lagi paling parah. Morning Brief malah nggak ngirim
    apa-apa, jadi dua halaman bisa kasih vonis beda di hari yang sama.

    CATATAN: angka ini nggak pernah ditampilin ke user sebagai streak yang
    bisa putus -- cuma masuk ke model, sama kayak `neglect_streak`.
    """
    today = today or clock.today()
    seen = set()
    for log in logs:
        try:
            seen.add(date.fromisoformat(log["date"]))
        except (KeyError, ValueError, TypeError):
            continue
    if not seen:
        return 0

    # Boleh mulai dari hari ini ATAU kemarin: jam 9 pagi user belum sempat
    # check-in, dan streak-nya nggak pantes dianggap putus gara-gara itu.
    from datetime import timedelta

    cursor = today if today in seen else today - timedelta(days=1)
    streak = 0
    while cursor in seen and streak < 10:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@dataclass
class MoodInsight:
    ready: bool
    log_count: int
    headline: str
    details: list[str] = field(default_factory=list)
    best_day: Optional[str] = None
    hardest_day: Optional[str] = None
    top_tags: list[tuple[str, int]] = field(default_factory=list)
    predicted_score: Optional[float] = None


def extract_tags(diary_text: str, limit: int = 5) -> list[str]:
    """Ambil kata kunci sederhana dari cerita user (buat lacak 'momen')."""
    words = re.findall(r"[a-zA-ZÀ-ÿ]{4,}", (diary_text or "").lower())
    meaningful = [w for w in words if w not in STOPWORDS]
    return [w for w, _ in Counter(meaningful).most_common(limit)]


def _weekday_averages(logs: list[dict]) -> dict[int, float]:
    grouped: dict[int, list[int]] = defaultdict(list)
    for log in logs:
        weekday = log.get("weekday")
        if weekday is None:
            weekday = date.fromisoformat(log["date"]).weekday()
        grouped[weekday].append(log["score"])
    return {day: sum(scores) / len(scores) for day, scores in grouped.items()}


def _daytype_averages(logs: list[dict]) -> tuple[Optional[float], Optional[float], int, int]:
    weekday_scores = [l["score"] for l in logs if not _is_weekend(l)]
    weekend_scores = [l["score"] for l in logs if _is_weekend(l)]
    weekday_avg = sum(weekday_scores) / len(weekday_scores) if weekday_scores else None
    weekend_avg = sum(weekend_scores) / len(weekend_scores) if weekend_scores else None
    return weekday_avg, weekend_avg, len(weekday_scores), len(weekend_scores)


def _is_weekend(log: dict) -> bool:
    if "is_weekend" in log and log["is_weekend"] is not None:
        return bool(log["is_weekend"])
    return date.fromisoformat(log["date"]).weekday() >= 5


def _predict_today(logs: list[dict]) -> Optional[float]:
    """Prediksi skor mood hari ini dari pola sendiri.

    Decision Tree kalau datanya cukup; kalau nggak, pakai rata-rata hari
    yang sama. Return None kalau nggak ada dasar sama sekali.
    """
    today = clock.today()
    weekday = today.weekday()

    if len(logs) >= MIN_LOGS_FOR_MODEL:
        X = []
        y = []
        for log in logs:
            wd = log.get("weekday")
            if wd is None:
                wd = date.fromisoformat(log["date"]).weekday()
            X.append([wd, 1 if _is_weekend(log) else 0, log.get("energy") or 3])
            y.append(log["score"])
        model = DecisionTreeRegressor(max_depth=3, random_state=42).fit(X, y)
        recent_energy = logs[0].get("energy") or 3
        return float(model.predict([[weekday, 1 if weekday >= 5 else 0, recent_energy]])[0])

    averages = _weekday_averages(logs)
    return averages.get(weekday)


def analyse(logs: list[dict]) -> MoodInsight:
    logs = [l for l in logs if l.get("score") is not None]
    count = len(logs)

    if count < MIN_LOGS_FOR_PATTERN:
        remaining = MIN_LOGS_FOR_PATTERN - count
        return MoodInsight(
            ready=False,
            log_count=count,
            headline=f"Kalem masih belajar pola kamu ({count}/{MIN_LOGS_FOR_PATTERN} catatan).",
            details=[
                f"Isi check-in {remaining} hari lagi biar Kalem mulai bisa lihat polanya.",
                "Makin sering kamu cerita, makin akurat pola yang kebaca.",
            ],
        )

    details: list[str] = []
    averages = _weekday_averages(logs)

    best_day = hardest_day = None
    if averages:
        best_idx = max(averages, key=lambda d: averages[d])
        worst_idx = min(averages, key=lambda d: averages[d])
        if averages[best_idx] - averages[worst_idx] >= 0.5:
            best_day = DAY_NAMES[best_idx]
            hardest_day = DAY_NAMES[worst_idx]
            details.append(f"Mood kamu cenderung paling bagus hari {best_day}, paling berat hari {hardest_day}.")

    weekday_avg, weekend_avg, n_weekday, n_weekend = _daytype_averages(logs)
    if (
        weekday_avg is not None
        and weekend_avg is not None
        and n_weekday >= MIN_PER_DAYTYPE
        and n_weekend >= MIN_PER_DAYTYPE
    ):
        gap = weekend_avg - weekday_avg
        if gap >= 0.5:
            details.append("Kamu jelas lebih enak pas weekend dibanding hari kerja.")
        elif gap <= -0.5:
            details.append("Menariknya, mood kamu justru lebih stabil pas hari kerja daripada weekend.")
        else:
            details.append("Mood kamu relatif stabil antara hari kerja dan weekend.")

    # Tag cepat dihitung duluan: dia terstruktur, jadi lebih bisa dipercaya
    # daripada kata yang kebetulan sering muncul di cerita bebas.
    tag_counter: Counter[str] = Counter()
    for log in logs:
        tag_counter.update(QUICK_TAGS.get(t, t) for t in (log.get("quick_tags") or []))
        tag_counter.update(log.get("tags") or [])
    top_tags = tag_counter.most_common(3)
    if top_tags:
        details.append("Hal yang paling sering muncul di catatan kamu: " + ", ".join(t for t, _ in top_tags) + ".")

    follow_up = recurring_tag_prompt(logs)
    if follow_up:
        details.append(follow_up)

    predicted = _predict_today(logs)
    if predicted is not None:
        if predicted <= 2.2:
            details.append("Berdasarkan pola kamu, hari ini kemungkinan agak berat -- pasang target yang ringan aja.")
        elif predicted >= 4:
            details.append("Berdasarkan pola kamu, hari ini biasanya termasuk hari yang cukup oke.")

    avg_all = sum(l["score"] for l in logs) / count
    headline = f"Dari {count} catatan, rata-rata mood kamu {avg_all:.1f}/5."

    if not details:
        details.append("Belum ada pola yang cukup jelas -- catatan kamu masih cukup merata.")

    return MoodInsight(
        ready=True,
        log_count=count,
        headline=headline,
        details=details,
        best_day=best_day,
        hardest_day=hardest_day,
        top_tags=top_tags,
        predicted_score=predicted,
    )
