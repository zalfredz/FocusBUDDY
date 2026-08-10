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
Di Flet Web state ini tetap terpisah untuk setiap sesi browser.

SISA WAKTU DIHITUNG DARI JAM DINDING, BUKAN DIKURANGI TIAP DETIK
----------------------------------------------------------------
`remaining()` ngitung selisih ke waktu akhir sesi. Jadi kalau UI-nya telat
nge-tick (halaman lagi sibuk, app ke-background, user pindah tab), sisa
waktunya tetap bener -- nggak ngambang ngikutin berapa kali layar sempat
digambar ulang.

Sengaja pakai `datetime.now()` asli, BUKAN `clock.now()`: `clock` punya
geseran hari buat testing, dan durasi sesi fokus nggak boleh ikut kegeser
gara-gara tombol "Maju 1 hari".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from app import session_scope

_SESSION_KEY = "focusbuddy.focus_session.v1"


@dataclass
class _FocusState:
    total_seconds: int = 0
    label: str = ""
    task_title: str = ""
    ends_at: Optional[datetime] = None   # keisi kalau lagi jalan
    paused_left: Optional[int] = None    # keisi kalau lagi dijeda
    finished: bool = False
    # Konteks tugas buat prediksi durasi. Kosong = tidak ada kategori yang
    # dapat dipakai model durasi personal.
    kategori: str = ""
    jumlah_unit: float = 0.0
    energi: int = 4
    recorded: bool = False


_FALLBACK_STATE = _FocusState()


def _state() -> _FocusState:
    """Timer sesi browser aktif; fallback global hanya untuk CLI/test."""
    return session_scope.get_or_create(_SESSION_KEY, _FocusState) or _FALLBACK_STATE


def start(
    minutes: int,
    label: str = "",
    task_title: str = "",
    kategori: str = "",
    jumlah_unit: float = 0,
    energi: int = 4,
) -> None:
    """Mulai sesi baru. Sesi yang lagi jalan ditimpa."""
    state = _state()
    state.total_seconds = max(int(minutes), 1) * 60
    state.label = label
    state.task_title = task_title
    state.ends_at = datetime.now() + timedelta(seconds=state.total_seconds)
    state.paused_left = None
    state.finished = False
    state.kategori = kategori
    state.jumlah_unit = float(jumlah_unit)
    state.energi = int(energi)
    state.recorded = False


def elapsed_minutes() -> float:
    """Berapa menit yang beneran kepakai, bukan yang direncanain."""
    state = _state()
    return max(0.0, (state.total_seconds - remaining()) / 60.0)


def record_if_worthwhile() -> Optional[dict]:
    """Catat sesi ini sebagai bahan belajar kecepatan personal.

    Yang dicatat MENIT ASLI YANG KEPAKAI, bukan durasi yang direncanain --
    kalau nggak, model cuma bakal belajar dari tebakannya sendiri dan
    angkanya nggak akan pernah bergerak (umpan balik yang muter di tempat).

    Aman dipanggil berkali-kali: flag ``recorded`` njaga biar nggak dobel.
    """
    from app import storage

    state = _state()
    if state.recorded or state.total_seconds <= 0:
        return None
    state.recorded = True
    # Sesi TANPA kategori tetap dicatat. Dia nggak dipakai buat nebak durasi
    # (`personal_average` nyaring per kategori), tapi tetap ngasih dua sinyal
    # yang berharga: rasio sesi yang bertahan sampai habis, dan seberapa jauh
    # perkiraan waktu meleset dari kenyataan.
    return storage.add_focus_record(
        kategori=state.kategori,
        jumlah_unit=state.jumlah_unit,
        menit=elapsed_minutes(),
        energi=state.energi,
        task_title=state.task_title,
        menit_est=state.total_seconds // 60,
        selesai=remaining() <= 0,
    )


def pause() -> None:
    state = _state()
    if state.ends_at is None:
        return
    state.paused_left = remaining()
    state.ends_at = None


def resume() -> None:
    state = _state()
    if state.paused_left is None or state.paused_left <= 0:
        return
    state.ends_at = datetime.now() + timedelta(seconds=state.paused_left)
    state.paused_left = None


def reset() -> None:
    """Balikin ke awal durasi yang sama, dalam keadaan berhenti."""
    state = _state()
    state.ends_at = None
    state.paused_left = state.total_seconds
    state.finished = False


def stop() -> None:
    """Sudahi sesinya sama sekali -- Beranda balik ke kartu aksi biasa.

    Dicatat DULU sebelum dibersihin: user yang mencet "Sudahi" sesudah
    ngerjain 18 dari 20 menit tetap ngasih sinyal yang berharga. Yang di
    bawah 3 menit disaring di `storage.add_focus_record`.
    """
    record_if_worthwhile()
    state = _state()
    state.total_seconds = 0
    state.label = ""
    state.task_title = ""
    state.ends_at = None
    state.paused_left = None
    state.finished = False
    state.kategori = ""
    state.jumlah_unit = 0.0
    state.energi = 4
    state.recorded = False


def remaining() -> int:
    state = _state()
    if state.ends_at is not None:
        return max(0, int((state.ends_at - datetime.now()).total_seconds()))
    if state.paused_left is not None:
        return max(0, state.paused_left)
    return state.total_seconds


def is_running() -> bool:
    return _state().ends_at is not None and remaining() > 0


def is_paused() -> bool:
    state = _state()
    return state.paused_left is not None and state.paused_left > 0


def is_active() -> bool:
    """Ada sesi yang lagi dipegang user (jalan, dijeda, atau baru kelar)."""
    return _state().total_seconds > 0


def just_finished() -> bool:
    """True sekali aja pas hitungannya nyampe nol -- biar pesan selesainya
    nggak nongol berulang tiap layar digambar ulang.

    Ini juga titik di mana sesi yang kelar penuh dicatat.
    """
    state = _state()
    if state.total_seconds > 0 and remaining() <= 0 and state.ends_at is not None:
        _ends_at_none()
        state.finished = True
        record_if_worthwhile()
    return state.finished


def _ends_at_none() -> None:
    state = _state()
    state.ends_at = None
    state.paused_left = 0


def progress() -> float:
    """1.0 di awal, 0.0 pas habis -- lingkarannya MENYUSUT, bukan ngisi."""
    state = _state()
    if state.total_seconds <= 0:
        return 0.0
    return max(0.0, min(1.0, remaining() / state.total_seconds))


def snapshot() -> dict[str, Any]:
    # UI manggil ini tiap detik, jadi ini titik paling andal buat nangkep
    # momen "hitungannya baru aja nyampe nol" dan nyatet sesinya.
    just_finished()
    state = _state()
    left = remaining()
    return {
        "kategori": state.kategori,
        "jumlah_unit": state.jumlah_unit,
        "total_seconds": state.total_seconds,
        "remaining": left,
        "label": state.label,
        "task_title": state.task_title,
        "running": is_running(),
        "paused": is_paused(),
        "active": is_active(),
        "finished": state.total_seconds > 0 and left <= 0,
        "progress": progress(),
        "clock": fmt(left),
    }


def fmt(seconds: int) -> str:
    m, s = divmod(max(int(seconds), 0), 60)
    return f"{m:02d}:{s:02d}"
