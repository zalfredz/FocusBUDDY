"""Flag kecil buat bedain build demo/kompetisi vs rilis beneran.

Satu tempat, satu baris diubah -- daripada nyari-nyari manual tiap ada
tombol testing yang harus ilang pas rilis (rawan kelewatan).
"""
from __future__ import annotations

# True selama kompetisi/demo: nampilin tombol bantu testing di header Home
# (maju hari, lompat ke malam, tutup & buka lagi app, toggle SUBS, Auto Feel)
# buat gampang nunjukkin fitur tanpa nunggu beneran gonta-ganti tanggal/jam.
# Ganti ke False sebelum rilis publik -- semua tombol itu bakal ilang
# otomatis, nggak perlu ubah home.py lagi. "Hapus semua data" NGGAK ikut
# di sini -- itu udah pindah ke Pengaturan sebagai fitur permanen.
DEMO_MODE = True
