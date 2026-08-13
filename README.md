# FocusBuddy

FocusBuddy adalah aplikasi pendamping micro-planning harian berbasis Flet. Karakter KALEM membantu pengguna memilih satu langkah yang realistis berdasarkan tugas, energi, mood, pola tidur, jam produktif, dan riwayat penggunaan.

Aplikasi ini dirancang untuk mengurangi beban memulai, bukan untuk memaksimalkan jumlah pekerjaan. FocusBuddy bukan alat diagnosis dan bukan pengganti tenaga medis.

## Isi dokumentasi

- [Panduan penggunaan aplikasi](docs/PANDUAN_APLIKASI.md)
- [Setup Google Auth dan Supabase](docs/SUPABASE_SETUP.md)
- [Arsitektur machine learning](docs/ML_ARCHITECTURE.md)
- [Alur data outcome](docs/ML_OUTCOME_DATA_FLOW.md)
- [Skema data outcome pengguna](docs/ML_USER_OUTCOME_DATA_SCHEMA.md)
- [Retrieval pecah tugas](docs/TASK_DECOMPOSITION_RETRIEVAL.md)

## Fitur saat ini

### Onboarding dan personalisasi

- Nama panggilan dan tanggal lahir sebagai data profil utama.
- Kesibukan, jam produktif, pola tidur, obat rutin, dan hal yang membuat khawatir sebagai jawaban opsional.
- Usia dihitung dari tanggal lahir; tanggal tidak disimpan sebagai usia statis.
- Pengguna dapat memperbarui semua jawaban personalisasi dari Pengaturan.

### Insight pagi

- KALEM menampilkan progress sampai data harian cukup untuk membentuk pola.
- Setelah data cukup, halaman menampilkan prediksi kondisi hari ini, alasan singkat, dan saran durasi fokus.
- Pengguna dapat menerima saran atau memilih `Aku ngerasa beda` untuk memperbarui check-in.

### Home dan sesi fokus

- Maskot serta bubble chat mengikuti energi hari ini dalam dua kelompok: energi 1–3 dan 4–6.
- Home menampilkan satu tugas yang disarankan; jika tidak ada tugas, tampil keadaan kosong tanpa tombol tambah tugas.
- `Ada yang Keingat?` menyimpan catatan cepat yang nanti dapat dirapikan menjadi tugas.
- Durasi fokus dapat diubah dari 1 sampai 30 menit.
- Sesi dapat dijeda, diulang, atau disudahi. Perpindahan tab diblokir selama sesi aktif agar konteks fokus tidak hilang.

### Tracker tugas

- Kalender mingguan yang ringkas dan kalender bulanan lengkap.
- Tugas aktif tetap berfokus pada tanggal yang dipilih; filter Harian, Mingguan, dan Bulanan hanya mengubah Sebaran Tugas.
- Form tambah tugas bertema gelap, dengan nama, deskripsi sebagai konteks, deadline, waktu, pengulangan, tingkat kepentingan, dan tingkat kesulitan memulai.
- Deskripsi tugas mendukung input suara ketika provider transkripsi tersedia.
- Pengulangan: Sekali, Harian, Mingguan, atau Bulanan.
- Pecah Tugas menyusun langkah kecil yang dapat diedit, ditandai selesai, ditambah, atau dihapus dari card tugas.
- Focus History dan Sebaran Tugas tersedia di bawah aksi utama Tracker.

### Mood, insight, Cerita, dan Favorit

- Check-in memilih mood, energi melalui slider 1–6, serta jawaban opsional tentang istirahat semalam dalam satu halaman.
- Maskot konsisten dengan Home dan Tracker.
- Ringkasan check-in diikuti `Yang KALEM paling pelajarin tentang kamu`, rekomendasi personal, grafik bulanan, Cerita Kamu, dan Favorit Kamu.
- Cerita mendukung ketik atau rekam suara, serta menampilkan cerita sebelumnya.
- Tombol hati di kanan atas halaman Mood membuka Favorit Kamu.

### Kewalahan

Alur `Kewalahan? YUK AMBIL JEDA` berjalan berurutan:

1. grounding dengan lima indra tanpa angka di kalimat instruksi;
2. latihan napas 4–7–8;
3. layar selesai;
4. pertanyaan `Sekarang rasanya gimana?`;
5. pilihan kembali perlahan atau melihat bantuan tambahan.

Halaman bantuan memuat latihan ulang, layanan profesional, dan HEALING119.ID dari KEMENKES di nomor 119.

### Pengaturan dan fitur lain

- Profil hanya menampilkan nama serta pengantar singkat dari KALEM.
- Pengingat obat menyimpan nama, stok, dosis harian, dan memberi peringatan ketika stok kurang dari tiga hari.
- Favorit menyimpan hal-hal yang membantu fokus dan menenangkan pengguna.
- Catatan cepat tersedia di `Catatan Kamu` dan dapat diubah menjadi tugas.
- Halaman Langganan KALEM memakai mode demo. Checkout kartu/GoPay tidak memproses pembayaran nyata.
- Tombol keluar akun dan hapus semua data dibuat sebagai dua aksi terpisah.

## Teknologi

- Python 3.13
- Flet 0.86 untuk UI desktop dan web
- Supabase Auth untuk login Google
- Supabase REST dengan Row Level Security untuk state per pengguna
- Gemini, OpenAI, atau DeepSeek untuk penyusunan berbasis AI
- Gemini atau OpenAI untuk transkripsi suara
- scikit-learn untuk eksperimen dan inference model yang sudah disetujui

## Struktur repositori

```text
FocusBuddy/
├── main.py                    # entry point desktop/web
├── app/
│   ├── main.py                # routing, auth, shell, navigation
│   ├── views/                 # halaman Flet
│   ├── core/                  # keputusan KALEM, AI, mood, obat, retrieval
│   ├── assets/                # maskot, ikon, dan aset UI
│   ├── storage.py             # state lokal per user + cloud save hook
│   └── focus_session.py       # lifecycle timer fokus
├── datasets/                  # dataset runtime dan evaluasi
├── models/                    # model runtime dan registry approval
├── ml/                        # pipeline eksperimen offline
├── reports/                   # laporan eksperimen reproducible
├── supabase/migrations/       # skema tabel dan RLS
├── tests/                     # regresi UI, storage, cloud, dan ML
├── tools/                     # utilitas dataset, evaluasi, dan audit
└── docs/                      # panduan teknis dan pengguna
```

Alur data ringkas:

```text
input pengguna
  -> storage per sesi/per pengguna
  -> sinkronisasi Supabase
  -> engine KALEM + model/retrieval yang tersedia
  -> keputusan, rekomendasi, dan UI
  -> outcome fokus/check-in disimpan kembali
```

## Menjalankan secara lokal

### 1. Prasyarat

- Python 3.13.x
- Project Supabase dengan Google OAuth aktif
- PowerShell, Command Prompt, atau shell setara

### 2. Instalasi

```powershell
git clone https://github.com/zalfredz/FocusBUDDY.git
cd FocusBUDDY
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Jika PowerShell menolak aktivasi virtual environment, jalankan Python langsung melalui `.\.venv\Scripts\python.exe`.

### 3. Konfigurasi minimum

Isi `.env`:

```dotenv
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
FOCUSBUDDY_PUBLIC_URL=http://localhost:8550
SUPABASE_REDIRECT_URI=http://localhost:8550/auth/callback
```

Jalankan migrasi [supabase/migrations/202608100001_focusbuddy_states.sql](supabase/migrations/202608100001_focusbuddy_states.sql), lalu ikuti [docs/SUPABASE_SETUP.md](docs/SUPABASE_SETUP.md) untuk Google OAuth dan redirect URL.

Tanpa `SUPABASE_URL` dan `SUPABASE_PUBLISHABLE_KEY`, aplikasi hanya menampilkan pemberitahuan bahwa database demo belum dikonfigurasi.

### 4. Jalankan aplikasi

Desktop:

```powershell
python main.py
```

Web lokal:

```powershell
$env:FOCUSBUDDY_WEB = "1"
$env:PORT = "8550"
python main.py
```

Buka `http://localhost:8550` dan login dengan Google.

## Environment variables

| Variable | Wajib | Fungsi |
| --- | --- | --- |
| `SUPABASE_URL` | Ya | URL project Supabase. |
| `SUPABASE_PUBLISHABLE_KEY` | Ya | Publishable/anon key untuk Auth dan REST yang dilindungi RLS. |
| `FOCUSBUDDY_PUBLIC_URL` | Ya untuk web | Origin publik aplikasi. |
| `SUPABASE_REDIRECT_URI` | Ya untuk OAuth | Callback OAuth, biasanya `<public-url>/auth/callback`. |
| `AI_PROVIDER` | Tidak | Memaksa `gemini`, `openai`, atau `deepseek`. Jika kosong, provider dipilih dari API key yang tersedia. |
| `GEMINI_API_KEY` | Tidak | Penyusunan AI dan/atau transkripsi Gemini. Alias `GEMINI_API` juga diterima. |
| `OPENAI_API_KEY` | Tidak | Penyusunan AI dan/atau transkripsi OpenAI. |
| `DEEPSEEK_API_KEY` | Tidak | Penyusunan AI melalui DeepSeek. Tidak dipakai untuk transkripsi. |
| `KALEM_SPEECH_PROVIDER` | Tidak | Memaksa transkripsi `gemini` atau `openai`. |
| `FOCUSBUDDY_CACHE_DIR` | Tidak | Lokasi cache state per user dan sesi web. |
| `FOCUSBUDDY_RUNTIME_MODE` | Tidak | Gunakan `production` untuk inference-only. |
| `FOCUSBUDDY_DURATION_MODEL_PATH` | Tidak | Path artefak durasi yang sudah dipromosikan dan lolos checksum. |
| `FOCUSBUDDY_PERSONALIZATION_MIN_OUTCOMES` | Tidak | Minimum outcome untuk kalibrasi personal; default contoh adalah 30. |
| `FOCUSBUDDY_WEB` | Tidak | `1`, `true`, atau `yes` untuk membuka mode web. |
| `PORT` / `FLET_SERVER_PORT` | Tidak | Port server web; adanya port juga mengaktifkan mode web. |

Jangan commit `.env`, API key, access token, refresh token, Google Client Secret, database password, atau service-role key.

## Data dan autentikasi

- Login memakai Google OAuth melalui Supabase PKCE.
- State setiap pengguna disimpan pada row `focusbuddy_states` dengan `user_id = auth.uid()`.
- RLS mencegah pengguna membaca atau menulis row milik akun lain.
- Runtime membuat cache JSON terpisah per pengguna dan per sesi, lalu mengantrekan sinkronisasi ke Supabase.
- Hapus semua data mengosongkan state aplikasi pengguna; keluar akun menghapus sesi lokal tanpa menghapus akun Google.

## Provider AI dan fallback

Pemilihan provider penyusunan mengikuti urutan:

1. nilai valid di `AI_PROVIDER`;
2. Gemini jika key tersedia;
3. OpenAI jika key tersedia;
4. DeepSeek jika key tersedia.

Tanpa provider AI, bagian yang mempunyai strategi lokal tetap memakai rule/retrieval lokal. Fitur generatif atau transkripsi yang memerlukan provider akan menampilkan pesan bahwa layanan belum dikonfigurasi; pengguna tetap dapat mengetik.

## Pengujian

Instal test runner bila belum tersedia:

```powershell
python -m pip install pytest
```

Jalankan seluruh suite:

```powershell
python -m pytest tests
```

Pemeriksaan cepat tanpa membuka UI:

```powershell
python -m compileall app models ml tests tools
python tests/test_regresi.py
```

Suite mencakup onboarding dan tanggal, daily check-in, Home/focus, Tracker, Mood, alur Kewalahan, Settings, storage, Supabase, provider AI, retrieval, dan fondasi ML.

## Docker dan deployment

Repository menyertakan `Dockerfile` berbasis Python 3.13. Image menjalankan `python main.py`; platform hosting perlu menyediakan HTTPS, WebSocket, dan variable `PORT`.

```powershell
docker build -t focusbuddy .
docker run --rm -p 8550:8550 --env-file .env -e PORT=8550 focusbuddy
```

Sebelum demo publik, uji login callback, isolasi dua akun, refresh/sinkronisasi data, microphone permission, dan kapasitas koneksi WebSocket.

## Batasan produk

- Checkout langganan adalah simulasi presentasi; tidak ada transaksi nyata.
- Insight adalah dukungan refleksi dari data pengguna, bukan diagnosis atau keputusan medis.
- Pengingat obat membantu menghitung stok, tetapi tidak menentukan dosis dan tidak menggantikan resep dokter.
- Tautan bantuan profesional adalah akses eksternal. Dalam keadaan darurat, hubungi layanan darurat setempat.

## Kontribusi

Sebelum mengirim perubahan:

1. pertahankan tema utama `#141416` dan kontras teks;
2. jangan hardcode tanggal hari ini;
3. jaga data tiap user/sesi tetap terisolasi;
4. jangan melakukan training model pada startup atau request pengguna;
5. tambahkan atau perbarui tes regresi untuk perubahan perilaku;
6. jalankan test suite dan `git diff --check`.
