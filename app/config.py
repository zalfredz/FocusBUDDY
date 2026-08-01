"""Flag kecil buat bedain build demo/kompetisi vs rilis beneran.

Satu tempat, satu baris diubah -- daripada nyari-nyari manual tiap ada
tombol testing yang harus ilang pas rilis (rawan kelewatan).
"""
from __future__ import annotations

# True selama kompetisi/demo: nampilin tombol "Reset data" & "Maju 1 hari"
# di Home buat gampang nunjukkin fitur tanpa nunggu beneran gonta-ganti
# tanggal. Ganti ke False sebelum rilis publik -- dua tombol itu bakal
# ilang otomatis, nggak perlu ubah home.py lagi.
DEMO_MODE = True
