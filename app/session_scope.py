"""State sementara yang terisolasi per koneksi/browser Flet.

Flet Web menjalankan banyak pengguna di satu proses Python. Karena itu state
runtime tidak boleh ditaruh sebagai global module biasa. ``page.session.store``
memberi ruang terpisah untuk setiap sesi browser dan Flet memasang page yang
benar di ``ft.context`` setiap kali handler dijalankan.

Fungsi di sini sengaja mengembalikan ``None`` saat dipanggil di luar Flet,
supaya script CLI dan regression test lama tetap bisa memakai fallback lokal.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional, TypeVar

T = TypeVar("T")


def current_store() -> Optional[Any]:
    """Ambil SessionStore aktif, atau ``None`` di luar callback Flet."""
    try:
        import flet as ft

        return ft.context.page.session.store
    except (AttributeError, RuntimeError):
        return None


def current_session_id() -> str:
    """ID acak sesi Flet aktif; string kosong di luar Flet."""
    try:
        import flet as ft

        return str(ft.context.page.session.id)
    except (AttributeError, RuntimeError):
        return ""


def get_or_create(key: str, factory: Callable[[], T]) -> Optional[T]:
    """Ambil value per-session; buat sekali kalau key belum tersedia."""
    store = current_store()
    if store is None:
        return None
    value = store.get(key)
    if value is None:
        value = factory()
        store.set(key, value)
    return value


def set_value(key: str, value: Any) -> bool:
    """Set value di sesi aktif. Return False bila tidak ada sesi Flet."""
    store = current_store()
    if store is None:
        return False
    store.set(key, value)
    return True


def remove_value(key: str) -> bool:
    """Hapus value dari sesi aktif tanpa menyentuh sesi browser lain."""
    store = current_store()
    if store is None:
        return False
    if store.contains_key(key):
        store.remove(key)
    return True
