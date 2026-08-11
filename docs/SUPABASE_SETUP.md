# Demo FocusBuddy: Flet Web + Google Auth + Supabase

Target akhirnya adalah satu URL HTTPS publik. Peserta cukup membuka link atau
scan QR di browser; mereka tidak perlu memasang Flet atau APK. Python, engine
Kalem, dan integrasi database berjalan di server hosting.

## Arsitektur data demo

1. Browser membuka Flet Web dan login Google.
2. Google kembali ke Supabase Auth, lalu Supabase mengarahkan browser ke
   `https://DOMAIN-DEMO/auth/callback`.
3. FocusBuddy memperoleh JWT user dan membaca/menulis satu row dengan
   `user_id = auth.uid()`.
4. Row Level Security menolak akun A membaca row akun B.
5. Cache runtime, timer fokus, dan jam demo juga dipisahkan per sesi browser.

Semua pengguna memakai project Supabase yang sama, tetapi bukan data yang
sama. Identitas Google menentukan row masing-masing.

## 1. Buat tabel dan RLS

Di Supabase Dashboard buka **SQL Editor**, tempel seluruh isi
`supabase/migrations/202608100001_focusbuddy_states.sql`, lalu klik **Run**.

Jangan memakai database password atau service-role key di aplikasi. FocusBuddy
hanya membutuhkan Project URL dan publishable key; aturan RLS yang menjaga
setiap row.

## 2. Aktifkan Google Auth

1. Di Google Cloud Console buat OAuth Client bertipe **Web application**.
2. Tambahkan Authorized redirect URI Google berikut:
   `https://PROJECT_REF.supabase.co/auth/v1/callback`
3. Di Supabase Dashboard buka **Authentication → Providers → Google**.
   Masukkan Client ID dan Client Secret dari Google, lalu aktifkan provider.
4. Di **Authentication → URL Configuration**:
   - Site URL: `https://DOMAIN-DEMO`
   - Redirect URL: `https://DOMAIN-DEMO/auth/callback`
   - Untuk uji lokal, boleh tambah `http://localhost:8550/auth/callback`.

Client Secret Google hanya disimpan di dashboard Supabase, bukan `.env`, kode,
Docker image, atau GitHub.

## 3. Deploy Flet Web

Repository sudah memiliki `Dockerfile`; hubungkan repository ke layanan
hosting container yang mendukung HTTPS dan WebSocket. Build dependency terjadi
di server hosting, bukan di laptop demo.

Set environment variables di dashboard hosting:

```text
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
FOCUSBUDDY_PUBLIC_URL=https://DOMAIN-DEMO
AI_PROVIDER=...
GEMINI_API_KEY=...        # hanya provider yang dipakai
OPENAI_API_KEY=...        # opsional
DEEPSEEK_API_KEY=...      # opsional
```

Hosting biasanya menyediakan `PORT` otomatis. `main.py` membaca nilai itu dan
menjalankan Flet Web pada `0.0.0.0`.

## 4. Uji sebelum acara

1. Buka domain di dua browser/profil incognito berbeda.
2. Login memakai dua akun Google berbeda.
3. Buat tugas berbeda di masing-masing akun.
4. Refresh dan login ulang; pastikan data kembali dari Supabase.
5. Pastikan akun A tidak melihat data akun B.
6. Uji 50 koneksi bersamaan di hosting yang dipilih; database sudah ringan,
   tetapi kapasitas server Flet/WebSocket tetap harus dibuktikan lewat load test.

Untuk uji lokal tanpa deploy:

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/flet run --web --host localhost --port 8550 app/main.py
```

URL lokal hanya untuk laptop sendiri. Link yang dapat dibuka peserta dari
jaringan mana pun baru tersedia setelah deploy ke domain HTTPS publik.
