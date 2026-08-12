"""Ekstraksi fitur durasi yang deterministik dari teks tugas saja."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


EXTRACTOR_VERSION = "duration-text-rules-v3"
MISSING_CATEGORY = "<missing>"

NUMBER_WORDS = {
    "sebuah": 1.0,
    "satu": 1.0,
    "dua": 2.0,
    "tiga": 3.0,
    "empat": 4.0,
    "lima": 5.0,
    "enam": 6.0,
    "tujuh": 7.0,
    "delapan": 8.0,
    "sembilan": 9.0,
    "sepuluh": 10.0,
    "seratus": 100.0,
    "seribu": 1000.0,
}
NUMBER_PATTERN = r"(?:\d+(?:[.,]\d+)?|" + "|".join(NUMBER_WORDS) + r")"

# Controlled vocabulary. A match means the object/unit is explicitly present in text.
UNIT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("soal", r"soal(?:-soal)?|pertanyaan"),
    ("halaman", r"halaman"),
    ("bab", r"bab"),
    ("file", r"file|folder"),
    ("dokumen", r"dokumen|laporan|proposal|paper|esai|draf|draft|silabus|formulir"),
    ("email", r"e-?mail"),
    ("slide", r"slide"),
    ("video", r"video|rekaman|episode"),
    ("orang", r"orang|peserta|anggota"),
    ("item", r"poin|posisi|lowongan|porsi|kata|kali|langkah|gambar|tabel|modul"),
    ("menit", r"menit"),
    ("jam", r"jam"),
)

ACTION_RULES: tuple[tuple[str, str], ...] = (
    ("membaca", r"\b(?:baca|review|proofread|periksa|cek)\b"),
    ("menulis", r"\b(?:tulis|catat|rangkum|dokumentasikan)\b"),
    ("belajar", r"\b(?:belajar|latihan|persiapan|pelajari)\b"),
    (
        "membersihkan",
        r"\b(?:bersihkan|cuci|lap|vacuum|sapu|rapikan|buang|kosongkan|lipat)\b",
    ),
    (
        "mengirim",
        r"\b(?:kirim|unggah|upload|balas|chat|telepon|posting|follow up|minta|konfirmasi|berikan)\b",
    ),
    ("mengisi", r"\b(?:isi|daftar|ajukan|kumpulkan|melamar|tanda tangan)\b"),
    (
        "membuat",
        r"\b(?:buat|membuat|bangun|masak|panggang|memanggang|merebus|marinasi|merakit|pasang|foto|rekam|melukis|gambar|jahitkan)\b",
    ),
    ("menonton", r"\b(?:tonton|nonton|menonton|dengarkan)\b"),
    (
        "mengedit",
        r"\b(?:edit|revisi|update|perbarui|ganti|perbaiki|format|terjemahkan|tanggapi|hapus|sesuaikan|tambah)\b",
    ),
    (
        "mengorganisir",
        r"\b(?:atur|rencanakan|siapkan|susun|jadwalkan|packing|inventarisasi|simpan|backup|ekspor|unduh|arsipkan|cetak|booking)\b",
    ),
    ("mengerjakan", r"\b(?:kerjakan|selesaikan|lakukan|jalankan|implementasi)\b"),
    (
        "transaksi",
        r"\b(?:beli|belanja|bayar|pesan|jual|kembalikan|batalkan|berhenti berlangganan)\b",
    ),
    (
        "perawatan",
        r"\b(?:minum|mandi|tidur|makan|pakai|obati|operasi|suntik|skincare|waxing|manicure|threading)\b",
    ),
    (
        "olahraga",
        r"\b(?:main|lari|berenang|stretching|pemanasan|gym|pilates|dansa|tenis|basket|sepak bola|voli)\b",
    ),
    ("perjalanan", r"\b(?:pergi|antar|jemput|ambil|bawa|pindahkan)\b"),
    ("sosial", r"\b(?:hadiri|menghadiri|ikut|temui|bicara|wawancarai)\b"),
    (
        "mencari",
        r"\b(?:cari|riset|identifikasi|tentukan|brainstorming|pilih|ukur)\b",
    ),
)

CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    (
        "akademik",
        r"\b(?:kuliah|dosen|praktikum|skripsi|ujian|uts|tugas|silabus|mata kuliah|kampus|beasiswa|sitasi|daftar pustaka|tesis|proposal penelitian|paper konferensi|peer review)\b",
    ),
    (
        "pekerjaan",
        r"\b(?:kerja|recruiter|wawancara|linkedin|cv|portofolio|project|proyek|github|grant|lowongan|lamaran|startup|klien|deliverable|equity research|valuasi|insiden)\b",
    ),
    (
        "kesehatan",
        r"\b(?:dokter|obat|antibiotik|vitamin|terapis|kesehatan|skincare|mandi|tidur|makan|sunscreen|gigi|mata|operasi|botox|filler|rambut|kuku|waxing|medical check up)\b",
    ),
    (
        "olahraga",
        r"\b(?:olahraga|gym|lari|berenang|pilates|dansa|tenis|basket|sepak bola|voli|hockey|skating|polo air|pickleball|sit up|pemanasan|stretching)\b",
    ),
    (
        "perjalanan",
        r"\b(?:trip|perjalanan|tiket pesawat|visa|mobil|kendaraan|stnk|antar|jemput|pulang|museum|taman hiburan)\b",
    ),
    (
        "rumah",
        r"\b(?:rumah|apartemen|dapur|kamar|wastafel|sampah|baju|piring|lantai|meja|lemari|rak|kulkas|microwave|kompor|seprai|handuk|tanaman|dinding|furnitur|makanan|masak|meal prep|vacuum)\b",
    ),
    (
        "administrasi",
        r"\b(?:bayar|tagihan|formulir|rekening|kartu kredit|asuransi|transaksi|langganan|audit|portal|ktp|dmv|autopay|donasi|regrade|izin|pendaftaran)\b",
    ),
    (
        "sosial",
        r"\b(?:teman|keluarga|ibu|ayah|nenek|sepupu|pacar|pesta|brunch|coffee chat|mente|rekan|mentoring|ngobrol|catch up)\b",
    ),
    (
        "pribadi",
        r"\b(?:game|musik|playlist|gitar|piano|drum|merajut|melukis|fotografi|instagram|pinterest|puzzle|origami|konser|halloween|parfum|makeup|diary|jurnal)\b",
    ),
)

COMPLEXITY_RULES: tuple[tuple[str, str], ...] = (
    (
        "analysis",
        r"\b(?:analisis|bandingkan|dibanding|evaluasi|hipotesis|statistik|pemodelan|valuasi|simulasi|kalibrasi)\b",
    ),
    (
        "research",
        r"\b(?:riset|penelitian|studi literatur|tinjauan literatur|cari tahu|referensi)\b",
    ),
    ("revision", r"\b(?:revisi|review|proofread|periksa ulang|edit|tanggapi komentar)\b"),
    (
        "long_form",
        r"\b(?:laporan|proposal|paper|skripsi|esai|dokumentasi|dokumentasikan)\b",
    ),
    ("completion", r"\b(?:selesaikan|final|akhir)\b"),
    ("learning", r"\b(?:pelajari|belajar)\b"),
)

SCOPE_RULES = {
    "scope_all": r"\b(?:seluruh|semua|keseluruhan)\b",
    "scope_multiple": r"\bbeberapa\b",
    "scope_each": r"\b(?:setiap|tiap)\b",
    "scope_complete": r"\blengkap\b",
}


@dataclass(frozen=True)
class ExtractedDurationFeatures:
    quantity_available: int
    quantity_value: float
    unit_type: str
    action_type: str
    task_category: str
    complexity_indicator: str
    complexity_analysis: int
    complexity_research: int
    complexity_revision: int
    complexity_long_form: int
    complexity_completion: int
    complexity_learning: int
    scope_all: int
    scope_multiple: int
    scope_each: int
    scope_complete: int
    n_token: int

    def as_dict(self) -> dict[str, str]:
        values = vars(self)
        return {key: str(value) for key, value in values.items()}


def _normalise(text: str) -> str:
    return " ".join(text.casefold().split())


def _number_value(raw: str) -> float:
    value = raw.casefold()
    if value in NUMBER_WORDS:
        return NUMBER_WORDS[value]
    return float(value.replace(",", "."))


def _extract_quantity(text: str) -> tuple[int, float, str]:
    candidates: list[tuple[int, float, str]] = []
    for unit_type, unit_pattern in UNIT_PATTERNS:
        pattern = re.compile(
            rf"\b(?P<number>{NUMBER_PATTERN})\s+(?:buah\s+)?(?:{unit_pattern})\b"
        )
        for match in pattern.finditer(text):
            candidates.append((match.start(), _number_value(match.group("number")), unit_type))
    if not candidates:
        return 0, 0.0, MISSING_CATEGORY
    _, value, unit_type = min(candidates, key=lambda item: item[0])
    return 1, value, unit_type


def _extract_unit(text: str, quantity_unit: str) -> str:
    if quantity_unit != MISSING_CATEGORY:
        return quantity_unit
    matches: list[tuple[int, str]] = []
    for unit_type, pattern in UNIT_PATTERNS:
        if unit_type in {"menit", "jam"}:
            continue
        match = re.search(rf"\b(?:{pattern})\b", text)
        if match:
            matches.append((match.start(), unit_type))
    if matches:
        return min(matches, key=lambda item: item[0])[1]
    return MISSING_CATEGORY


def _first_rule(text: str, rules: tuple[tuple[str, str], ...]) -> str:
    matches: list[tuple[int, int, str]] = []
    for priority, (label, pattern) in enumerate(rules):
        match = re.search(pattern, text)
        if match:
            matches.append((match.start(), priority, label))
    if not matches:
        return MISSING_CATEGORY
    return min(matches)[2]


def extract_duration_text_features(task_text: str) -> ExtractedDurationFeatures:
    """Menghasilkan fitur hanya dari string yang tersedia saat task dibuat."""
    text = _normalise(task_text)
    quantity_available, quantity_value, quantity_unit = _extract_quantity(text)
    complexity = {
        label: int(bool(re.search(pattern, text))) for label, pattern in COMPLEXITY_RULES
    }
    active_complexity = [label for label, active in complexity.items() if active]
    scope = {
        name: int(bool(re.search(pattern, text))) for name, pattern in SCOPE_RULES.items()
    }
    tokens = re.findall(r"\b[\w]+(?:-[\w]+)?\b", text, flags=re.UNICODE)
    return ExtractedDurationFeatures(
        quantity_available=quantity_available,
        quantity_value=quantity_value,
        unit_type=_extract_unit(text, quantity_unit),
        action_type=_first_rule(text, ACTION_RULES),
        task_category=_first_rule(text, CATEGORY_RULES).replace(MISSING_CATEGORY, "lainnya"),
        complexity_indicator="|".join(active_complexity) or MISSING_CATEGORY,
        complexity_analysis=complexity["analysis"],
        complexity_research=complexity["research"],
        complexity_revision=complexity["revision"],
        complexity_long_form=complexity["long_form"],
        complexity_completion=complexity["completion"],
        complexity_learning=complexity["learning"],
        scope_all=scope["scope_all"],
        scope_multiple=scope["scope_multiple"],
        scope_each=scope["scope_each"],
        scope_complete=scope["scope_complete"],
        n_token=len(tokens),
    )


def feature_rules_metadata() -> dict[str, Any]:
    return {
        "extractor_version": EXTRACTOR_VERSION,
        "input": "task text only",
        "target_used": False,
        "future_information_used": False,
        "quantity": (
            "First explicit numeric/number-word immediately followed by a controlled "
            "unit. Numbers after nomor/project/bab/kuliah/ujian and bare years are rejected."
        ),
        "unit_type_vocabulary": [label for label, _ in UNIT_PATTERNS],
        "action_type_vocabulary": [label for label, _ in ACTION_RULES],
        "task_category_vocabulary": [label for label, _ in CATEGORY_RULES] + ["lainnya"],
        "complexity_signals": [label for label, _ in COMPLEXITY_RULES],
        "scope_signals": list(SCOPE_RULES),
        "n_token": "Unicode word tokens from task text; punctuation is not a token.",
    }
