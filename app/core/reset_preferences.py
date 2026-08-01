"""Opsi & data statis buat halaman Reset + deteksi pola distress.

Personalisasi urutan opsi penenang SEKARANG ada di `kalem_ml/model_penenang.py`
(dulu di sini, frequency-based murni -- ditinggal karena "sering dipakai"
nggak sama dengan "beneran nolong", lihat docstring modul itu). Yang tersisa
di sini cuma dua hal yang emang harus rule-based:

1. Deteksi pola distress -- kalau user berulang kali mencet SOS sambil
   mood-nya rendah, app berhenti nawarin musik lagi dan lebih tegas
   ngarahin ke bantuan profesional. Ini SENGAJA bukan ML: keputusan nunjuk
   ke hotline krisis harus bisa dijelasin dalam satu kalimat dan nggak boleh
   probabilistik.

2. Data statis: opsi jeda, peta trigger->opsi (dipakai model_penenang buat
   tebakan awal sebelum ada riwayat), hotline, dan partner telehealth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from app import clock

# --- Opsi penenang yang tersedia di halaman Reset ---
#
# SEMUANYA MENENANGKAN, NGGAK ADA YANG NARIK TUGAS.
# Versi lama punya opsi "Satu tugas 60 detik" yang ngambil langkah dari daftar
# tugas beneran. Itu salah tempat: halaman ini bilang "semua daftar tugas lagi
# disembunyiin", terus nyodorin tugas. Buat orang yang lagi kewalahan, disodorin
# kerjaan pas minta jeda itu ngerusak kepercayaan ke halamannya sendiri.
#
# Yang gantiin: grounding 5-4-3-2-1 (teknik standar buat cemas) dan gerak badan
# 60 detik. Dua-duanya ngasih "menang kecil" yang sama tanpa nyentuh backlog.
OPTIONS = {
    "napas": {
        "label": "Latihan napas 4-7-8",
        "desc": "Dipandu lingkaran yang ikut napas kamu, sekitar semenit",
        "icon": "AIR",
    },
    "grounding": {
        "label": "Balik ke sini: 5-4-3-2-1",
        "desc": "Nyebutin apa yang keliatan, kedengeran, kerasa — narik kamu keluar dari spiral",
        "icon": "VISIBILITY",
    },
    "musik": {
        "label": "Dengerin musik nenangin",
        "desc": "Langsung buka musik yang kamu bilang bikin tenang",
        "icon": "MUSIC_NOTE",
    },
    "gerak": {
        "label": "Gerak 60 detik",
        "desc": "Badan dulu yang digerakin, kepalanya nyusul",
        "icon": "DIRECTIONS_WALK",
    },
}

# --- Ambang deteksi distress ---
SOS_WINDOW_DAYS = 7
SOS_COUNT_THRESHOLD = 3
LOW_MOOD_THRESHOLD = 2.0  # skor mood rata-rata (skala 1-5)


# Trigger overwhelm dari onboarding -> opsi mana yang paling masuk akal
# dimunculin duluan SEBELUM app punya riwayat pilihan user.
#
# Pemicu yang diketik sendiri user nggak ada di sini, dan itu nggak apa-apa:
# `model_penenang.peringkat()` cuma make peta ini buat tebakan awal, terus
# digantiin sama manfaat terukur begitu ada riwayat.
TRIGGER_DEFAULTS = {
    # Kepala penuh / muter-muter -> tarik balik ke indra dulu.
    "tugas_numpuk": "grounding",
    "gagal_fokus": "grounding",
    # Beku di titik mulai -> gerakin badan, jangan nambah mikir.
    "mulai_susah": "gerak",
    # Cemas akut -> napas yang paling cepat nurunin.
    "deadline": "napas",
    "sosial": "napas",
    # Capek fisik -> yang paling nggak nuntut apa-apa.
    "kurang_tidur": "musik",
}


def music_links(query: str) -> list[dict]:
    """Deep link ke pencarian musik -- BUKAN pemutar audio bawaan.

    `ft.Audio` nggak ada di Flet 0.86.4 yang kepakai di project ini (dicek
    lewat `dir(ft)`), dan lagian nge-bundle lagu berhak cipta jelas nggak
    boleh. Jadi polanya sama kayak "cari apotek": serahin ke layanan yang
    isinya beneran hidup daripada bikin pemutar palsu yang nggak bunyi.
    """
    from urllib.parse import quote_plus

    q = quote_plus(query.strip() or "lofi calm")
    return [
        {"name": "Spotify", "desc": f"Cari '{query}'", "url": f"https://open.spotify.com/search/{q}"},
        {"name": "YouTube Music", "desc": f"Cari '{query}'", "url": f"https://music.youtube.com/search?q={q}"},
    ]


@dataclass
class DistressSignal:
    escalate: bool
    sos_count: int
    avg_mood: Optional[float]
    reason: str = ""


def detect_distress(
    reset_events: list[dict],
    mood_logs: list[dict],
    window_days: int = SOS_WINDOW_DAYS,
) -> DistressSignal:
    """Bedain overwhelm harian biasa vs pola distress yang perlu rujukan.

    Kriteria eskalasi: SOS >= 3x dalam 7 hari DAN rata-rata mood <= 2.0.
    Dua-duanya harus kena -- SOS sering tapi mood oke belum tentu distress,
    dan mood rendah sekali-sekali juga hal yang normal.
    """
    today = clock.today()

    def within_window(iso_day: str) -> bool:
        return (today - date.fromisoformat(iso_day)).days < window_days

    recent_sos = [e for e in reset_events if within_window(e["date"])]
    sos_count = len(recent_sos)

    recent_scores = [
        log["score"] for log in mood_logs
        if log.get("score") is not None and within_window(log["date"])
    ]
    avg_mood = sum(recent_scores) / len(recent_scores) if recent_scores else None

    escalate = (
        sos_count >= SOS_COUNT_THRESHOLD
        and avg_mood is not None
        and avg_mood <= LOW_MOOD_THRESHOLD
    )

    reason = ""
    if escalate:
        reason = (
            f"Dalam {window_days} hari terakhir kamu buka halaman ini {sos_count}x "
            f"dan mood kamu rata-rata {avg_mood:.1f}/5."
        )

    return DistressSignal(
        escalate=escalate,
        sos_count=sos_count,
        avg_mood=avg_mood,
        reason=reason,
    )


# --- Hotline krisis: TELEPON, bukan tautan web ---
# Ditaruh paling atas dan sengaja bukan deep link ke situs: nomor telepon
# nggak bisa 404, nggak butuh sinyal data yang kenceng, dan orang yang lagi
# di titik terburuk nggak sanggup navigasiin website dulu.
CRISIS_HOTLINES = [
    {
        "name": "SEJIWA — Kemenkes",
        "desc": "Konseling kesehatan jiwa, gratis, 24 jam",
        "number": "119 ext. 8",
        "tel": "tel:119",
    },
]

# --- Partner telehealth (deep link, bukan sistem sesi sendiri) ---
#
# CATATAN URL: situs partner sering ngubah struktur URL-nya, dan tautan yang
# mati di halaman krisis itu kegagalan yang paling nggak boleh kejadian.
# Semua URL di bawah dicek manual (bukan cuma kode 200 -- Halodoc balikin 200
# buat halaman "Halaman tidak ditemukan"-nya juga, jadi isinya ikut dicek).
# Kalau ragu, mending nunjuk ke beranda partner daripada deep link yang rapuh.
TELEHEALTH_PARTNERS = [
    {
        "name": "Into The Light",
        "desc": "Direktori layanan & hotline krisis di Indonesia",
        "url": "https://www.intothelightid.org/saya-ingin-bunuh-diri/",
    },
    {
        "name": "Halodoc",
        "desc": "Cari psikolog & psikiater online",
        "url": "https://www.halodoc.com/cari-dokter/spesialis-kejiwaan",
    },
    {
        "name": "Riliv",
        "desc": "Konseling psikolog via chat",
        "url": "https://riliv.co",
    },
]
