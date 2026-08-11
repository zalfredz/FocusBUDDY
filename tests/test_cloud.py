"""Tes Auth, sinkronisasi cloud, dan isolasi sesi."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import clock, focus_session, storage
from app.cloud import FocusBuddyCloud, oauth_code_from_url
from app.main import (
    _canonical_local_login_url,
    _exchange_or_restore_oauth,
    _hydrate_user_state,
    _oauth_candidates_from_page,
    _read_preference_string,
    _restore_saved_cloud_session,
    _save_cloud_session,
)
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


class _PreferencesAsyncPalsu:
    def __init__(self, data=None, delayed=None, set_results=None):
        self.data = dict(data or {})
        self.delayed = {key: list(values) for key, values in (delayed or {}).items()}
        self.set_results = list(set_results or [])
        self.get_calls = {}
        self.set_calls = []

    async def get(self, key):
        self.get_calls[key] = self.get_calls.get(key, 0) + 1
        values = self.delayed.get(key, [])
        if values:
            return values.pop(0)
        return self.data.get(key)

    async def set(self, key, value):
        self.set_calls.append((key, value))
        result = self.set_results.pop(0) if self.set_results else True
        if result:
            self.data[key] = value
        return result


class _CloudAuthPalsu:
    def __init__(self, user=None, exchange_error=None):
        self.current_user = user
        self.exchange_error = exchange_error
        self.restored_verifier = ""
        self.exchanges = []
        self.restored_tokens = []

    def restore_pkce_verifier(self, verifier):
        self.restored_verifier = verifier

    def exchange_code(self, code, verifier):
        self.exchanges.append((code, verifier))
        if self.exchange_error:
            raise self.exchange_error
        self.current_user = SimpleNamespace(id="uid-oauth")

    def restore_session(self, access_token, refresh_token):
        self.restored_tokens.append((access_token, refresh_token))
        self.current_user = SimpleNamespace(id="uid-session")

    def user(self):
        return self.current_user

    def session(self):
        if self.current_user is None:
            return None
        return SimpleNamespace(
            access_token="access-baru", refresh_token="refresh-baru"
        )


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


def test_oauth_code_bisa_dibaca_dari_query_flet():
    code, error = oauth_code_from_url({"code": "dari-page-query", "state": "x"})
    assert code == "dari-page-query"
    assert error == ""


def test_kandidat_callback_menyertakan_page_query():
    class QueryPalsu:
        to_dict = {"code": "query-pertama"}

        def __call__(self):
            return None

    page = SimpleNamespace(
        query=QueryPalsu(),
        route="/auth/callback",
        url="http://localhost:8550",
    )
    candidates = _oauth_candidates_from_page(page, page.route)
    code, error = oauth_code_from_url(*candidates)
    assert code == "query-pertama"
    assert error == ""


def test_origin_127_dialihkan_ke_localhost_sebelum_login():
    assert _canonical_local_login_url(
        "ws://127.0.0.1:8550",
        "http://localhost:8550/auth/callback",
    ) == "http://localhost:8550/"


def test_origin_login_yang_sudah_sama_tidak_dialihkan():
    assert _canonical_local_login_url(
        "ws://localhost:8550",
        "http://localhost:8550/auth/callback",
    ) == ""


def test_domain_deploy_tidak_dialihkan_oleh_fix_lokal():
    assert _canonical_local_login_url(
        "wss://focusbuddy.onrender.com",
        "https://focusbuddy.onrender.com/auth/callback",
    ) == ""


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


def test_callback_pertama_menunggu_pkce_yang_belum_langsung_terbaca():
    preferences = _PreferencesAsyncPalsu(
        delayed={"pkce": [None, "", "verifier-pertama"]}
    )
    cloud = _CloudAuthPalsu()

    source = asyncio.run(
        _exchange_or_restore_oauth(
            cloud, preferences, "kode-pertama", "pkce", "tokens"
        )
    )

    assert source == "exchange"
    assert preferences.get_calls["pkce"] == 3
    assert cloud.exchanges == [("kode-pertama", "verifier-pertama")]
    assert cloud.user().id == "uid-oauth"


def test_callback_berulang_memakai_sesi_yang_sudah_tersimpan():
    tokens = json.dumps(
        {"access_token": "access-aman", "refresh_token": "refresh-aman"}
    )
    preferences = _PreferencesAsyncPalsu(data={"tokens": tokens})
    cloud = _CloudAuthPalsu()

    source = asyncio.run(
        _exchange_or_restore_oauth(
            cloud, preferences, "kode-sudah-dipakai", "pkce", "tokens"
        )
    )

    assert source == "session"
    assert cloud.exchanges == []
    assert cloud.restored_tokens == [("access-aman", "refresh-aman")]
    assert cloud.user().id == "uid-session"


def test_sesi_browser_rusak_tidak_dianggap_login_sah():
    preferences = _PreferencesAsyncPalsu(data={"tokens": "bukan-json"})
    cloud = _CloudAuthPalsu()

    assert asyncio.run(
        _restore_saved_cloud_session(cloud, preferences, "tokens")
    ) is False


def test_preference_string_kosong_tidak_dianggap_verifier():
    preferences = _PreferencesAsyncPalsu(delayed={"pkce": ["", "verifier"]})
    assert asyncio.run(
        _read_preference_string(
            preferences, "pkce", attempts=2, delay_seconds=0
        )
    ) == "verifier"


def test_token_browser_dicoba_ulang_tanpa_membatalkan_login():
    preferences = _PreferencesAsyncPalsu(set_results=[False, False, True])
    cloud = _CloudAuthPalsu(user=SimpleNamespace(id="uid-login"))

    saved = asyncio.run(
        _save_cloud_session(
            cloud, preferences, "tokens", attempts=3, delay_seconds=0
        )
    )

    assert saved is True
    assert len(preferences.set_calls) == 3
    assert json.loads(preferences.data["tokens"]) == {
        "access_token": "access-baru",
        "refresh_token": "refresh-baru",
    }


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
