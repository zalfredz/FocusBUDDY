"""Flag kecil buat bedain build demo/kompetisi vs rilis beneran.

Satu tempat, satu baris diubah -- daripada nyari-nyari manual tiap ada
tombol testing yang harus ilang pas rilis (rawan kelewatan).
"""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except ImportError:
    pass

# True selama kompetisi/demo: nampilin tombol bantu testing di header Home
# (maju hari, lompat ke malam, tutup & buka lagi app, toggle SUBS, Auto Feel)
# buat gampang nunjukkin fitur tanpa nunggu beneran gonta-ganti tanggal/jam.
# Ganti ke False sebelum rilis publik -- semua tombol itu bakal ilang
# otomatis, nggak perlu ubah home.py lagi. "Hapus semua data" NGGAK ikut
# di sini -- itu udah pindah ke Pengaturan sebagai fitur permanen.
DEMO_MODE = True

# Konfigurasi PUBLIK Supabase. Publishable key memang dirancang untuk ada di
# aplikasi client; keamanan data tetap datang dari Auth + Row Level Security,
# bukan dengan menyembunyikan key ini. Service-role key dan password database
# tidak boleh pernah ditaruh di aplikasi atau repository.
SUPABASE_URL = os.getenv(
    "SUPABASE_URL", ""
).rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.getenv(
    "SUPABASE_PUBLISHABLE_KEY", ""
)

# URL publik Flet Web. Saat lokal, jalankan web di port 8550. Di hosting nilai
# ini harus diganti ke domain HTTPS final agar callback Google kembali ke sesi
# browser, bukan ke custom scheme APK.
FOCUSBUDDY_PUBLIC_URL = os.getenv(
    "FOCUSBUDDY_PUBLIC_URL", "http://localhost:8550"
).rstrip("/")
SUPABASE_REDIRECT_URI = os.getenv(
    "SUPABASE_REDIRECT_URI", f"{FOCUSBUDDY_PUBLIC_URL}/auth/callback"
)
