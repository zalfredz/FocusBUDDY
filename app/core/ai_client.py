"""Helper Gemini yang dipakai bareng oleh Task Decomposer & kartu rekomendasi
Weekly Insight -- satu tempat, biar key handling & pesan error konsisten di
kedua fitur (nggak duplikat).
"""
from __future__ import annotations

import os
from typing import Optional

# PILIHAN MODEL -- diukur, bukan ditebak (dicek langsung ke API pakai key ini):
#
#   gemini-flash-latest       -> resolve ke gemini-3.6-flash.
#                                Kuota gratis CUMA 20 panggilan/HARI, dan
#                                ngabisin ~1600-2000 token "thinking" tiap
#                                panggilan sebelum sempat nulis JSON-nya.
#   gemini-flash-lite-latest  -> kuota harian jauh lebih longgar, dan
#                                thinking token-nya NOL. Kualitas hasil
#                                Pecah Tugas dites setara buat kerjaan ini
#                                (langkah konkret, langkah pertama < 5 menit,
#                                nurut sama level energi).
#   gemini-2.5-flash / -lite  -> 404 buat API key baru.
#
# Kuota dihitung PER MODEL, jadi gonta-ganti model = jatah baru. Yang bikin
# 20/hari kerasa sempit itu bukan pemakaian user -- tapi sesi ngoprek: sekali
# testing bisa abis, terus semua fitur AI diem-diem jatuh ke rule-based dan
# keliatan kayak "API-nya belum nyala".
#
# Mau dipatok ke versi tertentu? "gemini-3.5-flash-lite" juga dites jalan.
MODEL = "gemini-flash-lite-latest"

# Tanpa thinking token, budget nggak perlu segede model yang mikir dulu.
# Angka ini dipakai bareng sama decomposer & kartu rekomendasi.
MAX_OUTPUT_TOKENS = 3072


def api_key() -> Optional[str]:
    """Ambil key dari environment, dibantu .env kalau python-dotenv ada.

    Nggak pernah nge-hardcode key: kalau nggak ketemu, fitur pemanggilnya
    diem-diem balik ke mode fallback (dan alasannya dilaporin ke UI).
    """
    try:
        from dotenv import load_dotenv

        # override=False: kalau user udah export manual di shell, itu yang menang.
        load_dotenv(override=False)
    except ImportError:
        pass
    return os.environ.get("GEMINI_API_KEY") or None


# --------------------------------------------------------- lama panggilan
# Dipakai UI buat nampilin progress bar yang BERDASAR, bukan animasi ngasal.
# Disimpen di memori proses aja -- ini bukan data user, dan nggak ada gunanya
# dibawa antar sesi.
_lama: list[float] = []
LAMA_DEFAULT = 2.5      # tebakan awal sebelum ada pengukuran (detik)
LAMA_MAKS = 30.0


def catat_lama(detik: float) -> None:
    """Catat lama satu panggilan API yang sukses."""
    if 0 < detik < LAMA_MAKS:
        _lama.append(detik)
        del _lama[:-20]     # 20 terakhir aja; yang lama nggak relevan


def perkiraan_lama() -> float:
    """Berapa detik panggilan berikutnya kemungkinan makan waktu.

    Median, bukan rata-rata: satu panggilan yang kebetulan lemot nggak boleh
    bikin semua progress bar berikutnya kepanjangan.
    """
    if not _lama:
        return LAMA_DEFAULT
    urut = sorted(_lama)
    n = len(urut)
    return urut[n // 2] if n % 2 else (urut[n // 2 - 1] + urut[n // 2]) / 2


def punya_ukuran() -> bool:
    return bool(_lama)


def explain_error(exc: Exception) -> str:
    """Terjemahin exception SDK google-genai jadi kalimat yang actionable buat user."""
    name = type(exc).__name__
    text = str(exc).lower()

    if "api key" in text or "api_key" in text or "unauthenticated" in text or "401" in text:
        return "API key salah atau nggak valid (cek GEMINI_API_KEY di .env)"
    if "permission" in text or "403" in text:
        return "API key nggak punya akses ke model ini"
    if "quota" in text or "rate limit" in text or "resource_exhausted" in text or "429" in text:
        return "kena rate limit / kuota harian habis"
    if "not found" in text or "404" in text:
        return f"model '{MODEL}' nggak ketemu"
    if any(k in text for k in ("connection", "timeout", "network", "dns", "unreachable")):
        return "nggak bisa nyambung ke internet"
    return f"panggilan API gagal ({name})"
