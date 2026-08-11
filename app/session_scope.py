"""Penyimpanan runtime yang terisolasi per sesi Flet Web."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional, TypeVar

T = TypeVar("T")


def current_store() -> Optional[Any]:
    try:
        import flet as ft

        return ft.context.page.session.store
    except (AttributeError, RuntimeError):
        return None


def current_session_id() -> str:
    try:
        import flet as ft

        return str(ft.context.page.session.id)
    except (AttributeError, RuntimeError):
        return ""


def get_or_create(key: str, factory: Callable[[], T]) -> Optional[T]:
    store = current_store()
    if store is None:
        return None
    value = store.get(key)
    if value is None:
        value = factory()
        store.set(key, value)
    return value


def set_value(key: str, value: Any) -> bool:
    store = current_store()
    if store is None:
        return False
    store.set(key, value)
    return True


def remove_value(key: str) -> bool:
    store = current_store()
    if store is None:
        return False
    if store.contains_key(key):
        store.remove(key)
    return True
