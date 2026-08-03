"""Jam aplikasi -- satu-satunya sumber "hari ini" buat seluruh app.

Alasan modul ini ada: fitur yang bergantung riwayat beberapa hari (mood
model, deteksi distress, prediksi obat habis) mustahil dites kalau harus
nunggu hari beneran ganti. Dengan offset yang bisa digeser, satu sesi
testing bisa nyimulasiin dua minggu pemakaian.

Di produksi offset-nya selalu 0, jadi `today()` sama persis dengan
`date.today()`. Modul ini sengaja nggak import apa-apa dari app lain
supaya bebas dari circular import.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

_offset_days = 0
# Geseran JAM, kepisah dari geseran hari. Perlu sendiri karena ada fitur yang
# gerbangnya jam, bukan tanggal (mis. pertanyaan "udah makan?" yang cuma
# nongol lewat jam 18). Tanpa ini, "Maju 1 hari" nggak nolong sama sekali
# buat nunjukkin fitur kayak gitu pas demo siang-siang.
_offset_hours = 0


def set_offset(days: int) -> None:
    global _offset_days
    _offset_days = int(days)


def get_offset() -> int:
    return _offset_days


def advance(days: int = 1) -> int:
    global _offset_days
    _offset_days += int(days)
    return _offset_days


def set_hour_offset(hours: int) -> None:
    global _offset_hours
    _offset_hours = int(hours)


def get_hour_offset() -> int:
    return _offset_hours


def advance_hours(hours: int) -> int:
    global _offset_hours
    _offset_hours += int(hours)
    return _offset_hours


def hours_until(target_hour: int) -> int:
    """Berapa jam lagi biar `now()` nyampe di `target_hour`.

    Kalau sekarang udah lewat jamnya, dilanjut ke hari berikutnya -- jadi
    tombolnya selalu maju, nggak pernah mundurin waktu.
    """
    selisih = target_hour - now().hour
    return selisih if selisih > 0 else selisih + 24


def reset_offset() -> None:
    global _offset_days, _offset_hours
    _offset_days = 0
    _offset_hours = 0


def is_simulated() -> bool:
    return _offset_days != 0 or _offset_hours != 0


def today() -> date:
    # Diturunin dari now(), bukan dihitung sendiri: geseran jam yang nyebrang
    # tengah malam harus ikut ganti tanggal juga. Kalau dua-duanya dihitung
    # terpisah, jam bisa nunjukkin 01.00 tapi tanggalnya masih kemarin.
    return now().date()


def now() -> datetime:
    return datetime.now() + timedelta(days=_offset_days, hours=_offset_hours)
