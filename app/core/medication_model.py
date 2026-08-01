"""Medication Companion -- jalan di BELAKANG LAYAR, bukan halaman sendiri.

User setup sekali di awal (nama obat, dosis harian, stok awal). Sesudah itu
form-nya nggak diisi lagi: stok berkurang otomatis tiap user mencet "Udah
minum obat" di Home. Kalau mendekati habis (<= REMINDER_THRESHOLD hari),
Home nampilin banner yang nawarin cari apotek.

Kenapa stok cuma turun saat diabsen, bukan dihitung dari tanggal setup:
menebak dari kalender bakal salah tiap kali user skip dosis, dan angka stok
yang bohong lebih berbahaya daripada angka yang ketinggalan. Kalau user
belum absen hari ini, Kalem yang nanya duluan (lihat kalem_engine.decide).

BUKAN alat diagnosis / pengganti dokter. FocusBuddy nggak pernah nyaranin
atau ngitungin "dosis wajar" -- dosis yang diisi user itu yang sudah
ditentukan dokternya. Pencarian apotek nunjuk ke Google Maps + partner
daring asli (`ONLINE_PHARMACY_PARTNERS`) -- BUKAN daftar lokasi karangan.
Kalau butuh "apotek terdekat beneran", itu tugas Maps API, bukan data
statis yang bisa basi/salah alamat.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import numpy as np
from sklearn.linear_model import LinearRegression

from app import clock

# Lead time sengaja panjang: user butuh ruang buat nyari apotek / nebus resep
# tanpa mepet. Riset medication reminder app nyaranin 5-7 hari, bukan 3.
REMINDER_THRESHOLD_DAYS = 7

# Partner apotek daring -- titik komisi afiliasi.
#
# CATATAN URL: `halodoc.com/apotik-antar` DULU kepakai di sini dan sekarang
# soft-404 (dialihin ke /artikel/apotik-antar yang isinya "Halaman tidak
# ditemukan" -- tapi tetap balikin HTTP 200, jadi cek status doang nggak
# ketahuan). Semua deep link ke apotek Halodoc yang dicoba juga mati, makanya
# yang dipakai berandanya: rapuh dikit di UX, tapi nggak pernah mati.
ONLINE_PHARMACY_PARTNERS = [
    {"name": "Halodoc", "desc": "Tebus resep & antar obat", "url": "https://www.halodoc.com"},
    {"name": "K24Klik", "desc": "Apotek daring 24 jam", "url": "https://www.k24klik.com"},
]


@dataclass
class DepletionPrediction:
    days_left: int
    depletion_date: date
    daily_rate: float
    pills_remaining: float


def predict_depletion(
    pills_left: int,
    pills_per_day: float = 1.0,
    consumption_log: Optional[list[float]] = None,
) -> DepletionPrediction:
    """consumption_log: kumulatif pil terpakai, terlama duluan (opsional).

    Di bawah 3 titik data nggak cukup sinyal buat regresi, jadi fallback ke
    perhitungan dosis harian sederhana.
    """
    daily_rate = max(pills_per_day, 0.01)
    if consumption_log and len(consumption_log) >= 3:
        X = np.arange(len(consumption_log)).reshape(-1, 1)
        y = np.array(consumption_log)
        fitted_rate = float(LinearRegression().fit(X, y).coef_[0])
        if fitted_rate > 0:
            daily_rate = fitted_rate

    days_left = math.floor(pills_left / daily_rate)
    return DepletionPrediction(
        days_left=days_left,
        depletion_date=clock.today() + timedelta(days=days_left),
        daily_rate=daily_rate,
        pills_remaining=float(pills_left),
    )


@dataclass
class MedicationStatus:
    active: bool
    name: str = ""
    days_left: int = 0
    depletion_date: Optional[date] = None
    pills_remaining: float = 0.0
    needs_reminder: bool = False
    message: str = ""
    taken_today: bool = False


def check_status(medication: Optional[dict], today: Optional[date] = None) -> MedicationStatus:
    """Proyeksikan kapan stok habis dari sisa stok yang sudah dikonfirmasi.

    Inilah bagian "background"-nya: dipanggil tiap app dibuka, hasilnya
    dipakai buat nentuin perlu nampilin banner pengingat atau nggak.
    Stok (`pills_left`) cuma berubah lewat storage.take_medication(), jadi
    di sini tinggal bagi sisa stok dengan dosis harian.
    """
    if not medication or not medication.get("enabled", True):
        return MedicationStatus(active=False)

    today = today or clock.today()
    rate = max(float(medication.get("pills_per_day", 1)), 0.01)
    remaining = float(medication.get("pills_left", 0))
    taken_today = medication.get("last_taken") == today.isoformat()

    if remaining <= 0:
        return MedicationStatus(
            active=True,
            name=medication.get("name", "Obat"),
            days_left=0,
            depletion_date=today,
            pills_remaining=0.0,
            needs_reminder=True,
            message=f"Stok {medication.get('name', 'obat')} kamu diperkirakan sudah habis.",
            taken_today=taken_today,
        )

    days_left = math.floor(remaining / rate)
    depletion_date = today + timedelta(days=days_left)
    needs_reminder = days_left <= REMINDER_THRESHOLD_DAYS

    message = ""
    if needs_reminder:
        message = (
            f"{medication.get('name', 'Obat')} kamu diperkirakan habis "
            f"{days_left} hari lagi ({depletion_date.strftime('%d %b')})."
        )

    return MedicationStatus(
        active=True,
        name=medication.get("name", "Obat"),
        days_left=days_left,
        depletion_date=depletion_date,
        pills_remaining=remaining,
        needs_reminder=needs_reminder,
        message=message,
        taken_today=taken_today,
    )


def missed_streak(medication: Optional[dict], today: Optional[date] = None) -> int:
    """Berapa hari BERTURUT-TURUT obatnya nggak keabsen, dihitung dari kemarin.

    Nggak absen = dianggap nggak minum. Buat obat ADHD, beberapa hari bolong
    itu penjelasan yang masuk akal kenapa fokus & mood ikut turun -- dan itu
    konteks yang bikin Kalem nurunin ekspektasi, BUKAN alasan buat negur.

    HARI INI SENGAJA NGGAK DIHITUNG: jam 9 pagi user belum tentu udah minum,
    dan ngitung hari yang belum kelar jadi "kelewat" itu nuduh kecepetan.

    Dibatasi juga sama `start_date` -- hari sebelum obatnya didaftarin jelas
    bukan dosis yang kelewat.
    """
    if not medication or not medication.get("enabled", True):
        return 0

    today = today or clock.today()
    taken = set(medication.get("take_log", []))

    try:
        start = date.fromisoformat(medication.get("start_date", ""))
    except (TypeError, ValueError):
        start = None

    streak = 0
    cursor = today - timedelta(days=1)
    # Dibatasi 14 hari: lebih dari itu nggak nambah keputusan apa pun, dan
    # angka gede malah kesannya nge-judge.
    while streak < 14:
        if start and cursor < start:
            break
        if cursor.isoformat() in taken:
            break
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def maps_search_url(query: str = "apotek terdekat") -> str:
    """Deep link ke pencarian Google Maps.

    Sengaja nggak bikin data "stok real-time" palsu -- mending nyerahin ke
    Maps yang datanya beneran hidup daripada nampilin daftar contoh yang
    keliatan asli tapi bohong.
    """
    from urllib.parse import quote_plus

    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


# CATATAN: dulu ada `find_nearby_pharmacies()` + `_haversine_km()` di sini,
# ngitung jarak ke `SAMPLE_PHARMACIES` (5 apotek Jakarta yang DIKARANG lat/
# lon-nya buat demo). Nggak pernah dipanggil di mana pun, dan kalaupun
# kepasang bakal nampilin lokasi apotek palsu seolah nyata -- persis yang
# diperingatin di docstring `maps_search_url()` di atas. Dihapus.
