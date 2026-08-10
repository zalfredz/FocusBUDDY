"""Supabase Auth + sinkronisasi state FocusBuddy Web.

Setiap sesi browser memiliki client dan JWT sendiri. Satu salinan state
di-upsert ke Supabase dan dilindungi RLS berdasarkan ``auth.uid()``. Cache
JSON di server hanya penyangga sesi; Supabase adalah penyimpanan lintas sesi.
"""
from __future__ import annotations

import json
import logging
import threading
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import httpx
from supabase_auth import SyncGoTrueClient, SyncMemoryStorage

from app import config

_log = logging.getLogger(__name__)


class CloudUnavailable(RuntimeError):
    """Koneksi/config cloud belum siap; data lokal tetap aman."""


@dataclass(frozen=True)
class CloudUser:
    id: str
    email: str = ""
    name: str = ""


def oauth_code_from_url(*candidates: str) -> tuple[str, str]:
    """Ambil ``code`` atau error dari route/deep-link Flet."""
    for raw in candidates:
        if not raw:
            continue
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        code = (params.get("code") or [""])[0]
        if code:
            return code, ""
        error = (params.get("error_description") or params.get("error") or [""])[0]
        if error:
            return "", error
    return "", ""


class FocusBuddyCloud:
    """Satu instance per ``ft.Page``, tidak pernah global antar-user."""

    TABLE = "focusbuddy_states"
    AUTH_STORAGE_KEY = "focusbuddy-auth"

    def __init__(self) -> None:
        if not config.SUPABASE_URL or not config.SUPABASE_PUBLISHABLE_KEY:
            raise CloudUnavailable("Konfigurasi Supabase belum lengkap.")
        headers = {
            "apikey": config.SUPABASE_PUBLISHABLE_KEY,
            "Authorization": f"Bearer {config.SUPABASE_PUBLISHABLE_KEY}",
        }
        self._auth_storage = SyncMemoryStorage()
        self.auth = SyncGoTrueClient(
            url=f"{config.SUPABASE_URL}/auth/v1",
            headers=headers,
            storage_key=self.AUTH_STORAGE_KEY,
            storage=self._auth_storage,
            flow_type="pkce",
            auto_refresh_token=True,
            persist_session=True,
        )
        self._http = httpx.Client(timeout=15.0)
        self._lock = threading.Lock()
        self._pending: Optional[dict[str, Any]] = None
        self._worker_running = False

    def begin_google_login(self) -> str:
        response = self.auth.sign_in_with_oauth(
            {
                "provider": "google",
                "options": {
                    "redirect_to": config.SUPABASE_REDIRECT_URI,
                    "query_params": {
                        "access_type": "offline",
                        "prompt": "select_account",
                    },
                },
            }
        )
        return response.url

    def pkce_verifier(self) -> str:
        """Verifier yang harus dipertahankan saat browser pergi ke Google."""
        return self._auth_storage.get_item(
            f"{self.AUTH_STORAGE_KEY}-code-verifier"
        ) or ""

    def restore_pkce_verifier(self, verifier: str) -> None:
        """Pulihkan verifier setelah callback membuat sesi Flet baru."""
        if verifier:
            self._auth_storage.set_item(
                f"{self.AUTH_STORAGE_KEY}-code-verifier", verifier
            )

    def exchange_code(self, code: str):
        return self.auth.exchange_code_for_session({"auth_code": code})

    def restore_session(self, access_token: str, refresh_token: str):
        return self.auth.set_session(access_token, refresh_token)

    def session(self):
        return self.auth.get_session()

    def user(self) -> Optional[CloudUser]:
        session = self.session()
        if not session or not session.user:
            return None
        metadata = session.user.user_metadata or {}
        return CloudUser(
            id=str(session.user.id),
            email=str(session.user.email or ""),
            name=str(metadata.get("full_name") or metadata.get("name") or ""),
        )

    def _headers(self, *, prefer: str = "") -> dict[str, str]:
        session = self.session()
        if not session:
            raise CloudUnavailable("Sesi login sudah berakhir.")
        headers = {
            "apikey": config.SUPABASE_PUBLISHABLE_KEY,
            "Authorization": f"Bearer {session.access_token}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    @property
    def _table_url(self) -> str:
        return f"{config.SUPABASE_URL}/rest/v1/{self.TABLE}"

    def download_state(self, user_id: str) -> Optional[dict[str, Any]]:
        response = self._http.get(
            self._table_url,
            headers=self._headers(),
            params={"select": "state", "user_id": f"eq.{user_id}", "limit": "1"},
        )
        if response.status_code == 404:
            raise CloudUnavailable(
                "Tabel cloud belum dibuat. Jalankan migrasi Supabase terlebih dahulu."
            )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            return None
        state = rows[0].get("state")
        return state if isinstance(state, dict) else None

    def upload_state(self, user_id: str, state: dict[str, Any]) -> None:
        response = self._http.post(
            self._table_url,
            headers=self._headers(prefer="resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "user_id"},
            content=json.dumps(
                {"user_id": user_id, "state": state},
                ensure_ascii=False,
                default=str,
            ),
        )
        if response.status_code == 404:
            raise CloudUnavailable(
                "Tabel cloud belum dibuat. Jalankan migrasi Supabase terlebih dahulu."
            )
        response.raise_for_status()

    def enqueue_state(self, user_id: str, state: dict[str, Any]) -> None:
        """Coalesce save cepat; jaringan tidak boleh membekukan tombol UI."""
        with self._lock:
            self._pending = deepcopy(state)
            if self._worker_running:
                return
            self._worker_running = True
        threading.Thread(
            target=self._upload_worker,
            args=(user_id,),
            name="focusbuddy-cloud-save",
            daemon=True,
        ).start()

    def _upload_worker(self, user_id: str) -> None:
        while True:
            with self._lock:
                state = self._pending
                self._pending = None
                if state is None:
                    self._worker_running = False
                    return
            try:
                self.upload_state(user_id, state)
            except Exception as exc:  # cache lokal tetap source of truth saat offline
                _log.warning("Sinkronisasi Supabase gagal: %s", exc)

    def sign_out(self) -> None:
        self.auth.sign_out()
