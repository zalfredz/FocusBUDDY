"""Tes unit boundary Auth/cloud tanpa memanggil jaringan."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from app import clock, focus_session, storage
from app.cloud import FocusBuddyCloud, oauth_code_from_url


class _StorePalsu:
    def __init__(self):
        self.data = {}

    def set(self, key, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def contains_key(self, key):
        return key in self.data

    def remove(self, key):
        self.data.pop(key, None)


def test_oauth_code_dari_callback_web():
    code, error = oauth_code_from_url(
        "https://demo.focusbuddy.id/auth/callback?code=abc123&state=x"
    )
    assert code == "abc123"
    assert error == ""


def test_oauth_error_dari_callback_web():
    code, error = oauth_code_from_url(
        "/?error=access_denied&error_description=User+cancelled"
    )
    assert code == ""
    assert error == "User cancelled"


def test_pkce_verifier_bisa_dipulihkan_setelah_redirect():
    cloud = FocusBuddyCloud()
    cloud.restore_pkce_verifier("verifier-browser")
    assert cloud.pkce_verifier() == "verifier-browser"


def test_storage_user_dipisah_dan_hook_dipanggil():
    old = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    called = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            storage.DATA_DIR = base
            storage.DATA_FILE = base / "data.json"
            storage.BACKUP_FILE = base / "data.json.bak"
            storage.set_cloud_save_hook(lambda state: called.append(state))
            state = storage.load_state()
            state["profile"]["name"] = "A"
            storage.save_state(state)
            assert called[-1]["profile"]["name"] == "A"
    finally:
        storage.set_cloud_save_hook(None)
        storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = old


def test_dua_sesi_browser_tidak_berbagi_state_runtime():
    """Storage, jam demo, dan timer wajib terpisah dalam satu proses web."""
    stores = {"a": _StorePalsu(), "b": _StorePalsu()}
    active = ["a"]

    def current_store():
        return stores[active[0]]

    with tempfile.TemporaryDirectory() as tmp, patch(
        "app.session_scope.current_store", side_effect=current_store
    ), patch(
        "app.session_scope.current_session_id", side_effect=lambda: active[0]
    ):
        root = Path(tmp)

        storage.configure_user_storage("user-a", cache_root=root)
        state_a = storage.load_state()
        state_a["profile"]["name"] = "A"
        storage.save_state(state_a)
        storage.advance_day(7)
        focus_session.start(10, task_title="Tugas A")

        active[0] = "b"
        storage.configure_user_storage("user-b", cache_root=root)
        assert storage.load_state()["profile"]["name"] == ""
        assert clock.get_offset() == 0
        assert not focus_session.is_active()

        active[0] = "a"
        assert storage.load_state()["profile"]["name"] == "A"
        assert clock.get_offset() == 7
        assert focus_session.snapshot()["task_title"] == "Tugas A"
        focus_session.stop()
        clock.reset_offset()
