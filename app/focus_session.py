"""Sesi fokus -- satu sesi untuk seluruh app, hidup di luar halaman mana pun.

KENAPA MODUL SENDIRI, BUKAN STATE DI DALAM HALAMAN
--------------------------------------------------
Dulu timernya tinggal di dalam `tracker.build()`. Dua akibatnya:

1. Sesi MATI begitu pindah halaman. Buka Mood sebentar buat check-in, balik
   ke Tracker, timernya udah balik ke awal. Buat orang ADHD yang emang
   gampang kesenggol pindah konteks, itu ngehukum persis kelakuan yang
   paling sering kejadian.
2. Tombol FOKUS di Beranda cuma "nitip niat" lewat nav.set_intent(), terus
   mental ke halaman lain. Aksinya kepecah dua halaman padahal niatnya satu.

Sekarang sesinya di sini: Beranda yang nampilin & ngendaliin, halaman lain
tinggal baca kalau perlu, dan sesinya tetap jalan pas user keliling app.

SISA WAKTU DIHITUNG DARI JAM DINDING, BUKAN DIKURANGI TIAP DETIK
----------------------------------------------------------------
`remaining()` ngitung selisih ke `_ends_at`. Jadi kalau UI-nya telat
nge-tick (halaman lagi sibuk, app ke-background, user pindah tab), sisa
waktunya tetap bener -- nggak ngambang ngikutin berapa kali layar sempat
digambar ulang.

Sengaja pakai `datetime.now()` asli, BUKAN `clock.now()`: `clock` punya
geseran hari buat testing, dan durasi sesi fokus nggak boleh ikut kegeser
gara-gara tombol "Maju 1 hari".
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

_total_seconds: int = 0
_label: str = ""
_task_title: str = ""
_ends_at: Optional[datetime] = None      # keisi kalau lagi jalan
_paused_left: Optional[int] = None       # keisi kalau lagi dijeda
_finished: bool = False

# Konteks tugas buat prediksi durasi. Kosong = sesinya nggak nyambung ke tugas
# berkategori, jadi nggak ada yang bisa dipelajari darinya.
_kategori: str = ""
_jumlah_unit: float = 0.0
_energi: int = 4
_recorded: bool = False


def start(
    minutes: int,
    label: str = "",
    task_title: str = "",
    kategori: str = "",
    jumlah_unit: float = 0,
    energi: int = 4,
) -> None:
    """Mulai sesi baru. Sesi yang lagi jalan ditimpa."""
    global _total_seconds, _label, _task_title, _ends_at, _paused_left, _finished
    global _kategori, _jumlah_unit, _energi, _recorded
    _total_seconds = max(int(minutes), 1) * 60
    _label = label
    _task_title = task_title
    _ends_at = datetime.now() + timedelta(seconds=_total_seconds)
    _paused_left = None
    _finished = False
    _kategori = kategori
    _jumlah_unit = float(jumlah_unit)
    _energi = int(energi)
    _recorded = False


def elapsed_minutes() -> float:
    """Berapa menit yang beneran kepakai, bukan yang direncanain."""
    return max(0.0, (_total_seconds - remaining()) / 60.0)


def record_if_worthwhile() -> Optional[dict]:
    """Catat sesi ini sebagai bahan belajar kecepatan personal.

    Yang dicatat MENIT ASLI YANG KEPAKAI, bukan durasi yang direncanain --
    kalau nggak, model cuma bakal belajar dari tebakannya sendiri dan
    angkanya nggak akan pernah bergerak (umpan balik yang muter di tempat).

    Aman dipanggil berkali-kali: `_recorded` njaga biar nggak dobel.
    """
    global _recorded
    from app import storage

    if _recorded or _total_seconds <= 0:
        return None
    _recorded = True
    # Sesi TANPA kategori tetap dicatat. Dia nggak dipakai buat nebak durasi
    # (`personal_average` nyaring per kategori), tapi tetap ngasih dua sinyal
    # yang berharga: rasio sesi yang bertahan sampai habis, dan seberapa jauh
    # perkiraan waktu meleset dari kenyataan.
    return storage.add_focus_record(
        kategori=_kategori,
        jumlah_unit=_jumlah_unit,
        menit=elapsed_minutes(),
        energi=_energi,
        task_title=_task_title,
        menit_est=_total_seconds // 60,
        selesai=remaining() <= 0,
    )


def pause() -> None:
    global _ends_at, _paused_left
    if _ends_at is None:
        return
    _paused_left = remaining()
    _ends_at = None


def resume() -> None:
    global _ends_at, _paused_left
    if _paused_left is None or _paused_left <= 0:
        return
    _ends_at = datetime.now() + timedelta(seconds=_paused_left)
    _paused_left = None


def reset() -> None:
    """Balikin ke awal durasi yang sama, dalam keadaan berhenti."""
    global _ends_at, _paused_left, _finished
    _ends_at = None
    _paused_left = _total_seconds
    _finished = False


def stop() -> None:
    """Sudahi sesinya sama sekali -- Beranda balik ke kartu aksi biasa.

    Dicatat DULU sebelum dibersihin: user yang mencet "Sudahi" sesudah
    ngerjain 18 dari 20 menit tetap ngasih sinyal yang berharga. Yang di
    bawah 3 menit disaring di `storage.add_focus_record`.
    """
    global _total_seconds, _label, _task_title, _ends_at, _paused_left, _finished
    global _kategori, _jumlah_unit, _recorded
    record_if_worthwhile()
    _total_seconds = 0
    _label = ""
    _task_title = ""
    _ends_at = None
    _paused_left = None
    _finished = False
    _kategori = ""
    _jumlah_unit = 0.0
    _recorded = False


def remaining() -> int:
    if _ends_at is not None:
        return max(0, int((_ends_at - datetime.now()).total_seconds()))
    if _paused_left is not None:
        return max(0, _paused_left)
    return _total_seconds


def is_running() -> bool:
    return _ends_at is not None and remaining() > 0


def is_paused() -> bool:
    return _paused_left is not None and _paused_left > 0


def is_active() -> bool:
    """Ada sesi yang lagi dipegang user (jalan, dijeda, atau baru kelar)."""
    return _total_seconds > 0


def just_finished() -> bool:
    """True sekali aja pas hitungannya nyampe nol -- biar pesan selesainya
    nggak nongol berulang tiap layar digambar ulang.

    Ini juga titik di mana sesi yang kelar penuh dicatat.
    """
    global _finished
    if _total_seconds > 0 and remaining() <= 0 and _ends_at is not None:
        _ends_at_none()
        _finished = True
        record_if_worthwhile()
    return _finished


def _ends_at_none() -> None:
    global _ends_at, _paused_left
    _ends_at = None
    _paused_left = 0


def progress() -> float:
    """1.0 di awal, 0.0 pas habis -- lingkarannya MENYUSUT, bukan ngisi."""
    if _total_seconds <= 0:
        return 0.0
    return max(0.0, min(1.0, remaining() / _total_seconds))


def snapshot() -> dict[str, Any]:
    # UI manggil ini tiap detik, jadi ini titik paling andal buat nangkep
    # momen "hitungannya baru aja nyampe nol" dan nyatet sesinya.
    just_finished()
    left = remaining()
    return {
        "kategori": _kategori,
        "jumlah_unit": _jumlah_unit,
        "total_seconds": _total_seconds,
        "remaining": left,
        "label": _label,
        "task_title": _task_title,
        "running": is_running(),
        "paused": is_paused(),
        "active": is_active(),
        "finished": _total_seconds > 0 and left <= 0,
        "progress": progress(),
        "clock": fmt(left),
    }


def fmt(seconds: int) -> str:
    m, s = divmod(max(int(seconds), 0), 60)
    return f"{m:02d}:{s:02d}"
