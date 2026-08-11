"""Konfigurasi runtime FocusBuddy dari environment."""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except ImportError:
    pass

DEMO_MODE = True

SUPABASE_URL = os.getenv(
    "SUPABASE_URL", ""
).rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.getenv(
    "SUPABASE_PUBLISHABLE_KEY", ""
)

FOCUSBUDDY_PUBLIC_URL = os.getenv(
    "FOCUSBUDDY_PUBLIC_URL", "http://localhost:8550"
).rstrip("/")
SUPABASE_REDIRECT_URI = os.getenv(
    "SUPABASE_REDIRECT_URI", f"{FOCUSBUDDY_PUBLIC_URL}/auth/callback"
)
