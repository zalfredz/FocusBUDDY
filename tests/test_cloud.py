"""Tes Auth, sinkronisasi cloud, dan isolasi sesi."""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import clock, focus_session, storage
from app.cloud import FocusBuddyCloud, oauth_code_from_url
from app.main import _hydrate_user_state
from app.views import home


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


def test_exchange_oauth_memakai_verifier_callback_yang_eksplisit():
    cloud = FocusBuddyCloud()
    try:
        with patch.object(cloud.auth, "exchange_code_for_session") as exchange:
            cloud.exchange_code("kode-oauth", "verifier-browser")
        assert exchange.call_args.args[0] == {
            "auth_code": "kode-oauth",
            "code_verifier": "verifier-browser",
        }
    finally:
        cloud._http.close()


def test_fetch_database_selalu_difilter_dengan_uid_login():
    cloud = FocusBuddyCloud()
    response = SimpleNamespace(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: [{"state": {"profile": {"name": "Dari DB"}}}],
    )
    try:
        with patch.object(
            cloud, "session", return_value=SimpleNamespace(access_token="jwt-user-a")
        ), patch.object(cloud._http, "get", return_value=response) as get:
            state = cloud.download_state("uid-user-a")
        assert state["profile"]["name"] == "Dari DB"
        assert get.call_args.kwargs["params"]["user_id"] == "eq.uid-user-a"
        assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer jwt-user-a"
    finally:
        cloud._http.close()


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
        ticker_a = home._ticker_state()
        ticker_a["running"] = True

        active[0] = "b"
        storage.configure_user_storage("user-b", cache_root=root)
        assert storage.load_state()["profile"]["name"] == ""
        assert clock.get_offset() == 0
        assert not focus_session.is_active()
        ticker_b = home._ticker_state()
        assert ticker_b is not ticker_a
        assert ticker_b["running"] is False

        active[0] = "a"
        assert storage.load_state()["profile"]["name"] == "A"
        assert clock.get_offset() == 7
        assert focus_session.snapshot()["task_title"] == "Tugas A"
        assert home._ticker_state()["running"] is True
        focus_session.stop()
        clock.reset_offset()


def test_fetch_database_menghidrasi_state_yang_dibaca_frontend():
    stores = {"browser": _StorePalsu()}
    remote = storage._default_state()
    remote["profile"]["name"] = "Nama dari Supabase"

    class CloudPalsu:
        uploads = []

        def download_state(self, user_id):
            assert user_id == "uid-db"
            return remote

        def upload_state(self, user_id, state):
            self.uploads.append((user_id, state))

    with tempfile.TemporaryDirectory() as tmp, patch(
        "app.session_scope.current_store", return_value=stores["browser"]
    ), patch(
        "app.session_scope.current_session_id", return_value="browser"
    ):
        storage.configure_user_storage("uid-db", cache_root=Path(tmp))
        cloud = CloudPalsu()
        sumber = _hydrate_user_state(cloud, "uid-db")
        assert sumber == "database"
        assert storage.get_profile()["name"] == "Nama dari Supabase"
        assert cloud.uploads == []
