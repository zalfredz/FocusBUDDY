# FocusBuddy

Micro-planning app buat orang dengan kecenderungan ADHD/executive dysfunction.
Ditemenin **Kalem**, karakter buddy yang ekspresinya ngikutin mood kamu dan
makin lama makin kenal kebiasaan kamu.

Dibangun 100% **Python** lewat [Flet](https://flet.dev) -- UI dirender Flutter,
jadi bisa jalan sebagai app Android/iOS beneran (`flet build`) atau langsung di
browser buat demo. Nggak perlu nulis Dart/JS.

## Struktur

```
SettingDemo.py                # 10 skenario demo siap pakai (lihat "Auto Feel" di bawah)
app/
  assets/                    # 5 ekspresi Kalem (SVG) -- harus sejajar main.py,
    kalem_semangat.svg       #   itu yang dicari `flet run` (FLET_ASSETS_DIR)
    kalem_tenang.svg  kalem_cemas.svg  kalem_sedih.svg  kalem_lelah.svg
  config.py                  # DEMO_MODE -- gate tombol testing di Home
  main.py                    # router: 3 tab nav + halaman ekstra
  theme.py                   # palet + font Lexend/Quicksand
  buddy.py                   # Kalem: MOOD_ASSETS, MOOD_SCORE, komponen UI
  storage.py                 # persistensi lokal (~/.focusbuddy/data.json)
  clock.py                   # sumber tunggal "sekarang" -- offset hari & jam buat testing
  focus_session.py           # sesi fokus global, hidup di luar halaman mana pun
  ui_helpers.py               # komponen UI berulang + ProgresAI (bar progres AI)
  core/
    kalem_engine.py          # ★ decision engine: satu otak buat semua halaman
    decomposer_logic.py      # pecah tugas HARI INI -> slot waktu (model_durasi + AI)
    energy_predictor.py      # Decision Tree (data sintetis) -- prior model_energi
    mood_model.py            # checkin_streak/neglect_streak (canonical), diary, tag
    reset_preferences.py     # opsi jeda + deteksi distress (rule-based, safety-critical)
    medication_model.py      # proyeksi stok obat + dosis kelewat + link apotek
    bpom.py                  # validasi nama obat dari registri BPOM (offline)
    recommendations.py       # kartu rekomendasi musik/resep dari Favorit
    ai_client.py             # ★ provider AI (Gemini/OpenAI/DeepSeek, dari .env) + latensi
    decision_quality.py      # beban tugas vs waktu tersedia -- fakta murni, nggak milih/nge-UI
  kalem_ml/
    fitur.py                 # ★ lapisan fitur bersama -- satu definisi, semua model baca dari sini
    riwayat.py                # rekonstruksi fitur per HARI LAMPAU (buat melatih) + sidik_jari()
    model_durasi.py          # judul tugas -> rentang menit (TFIDF + RandomForest)
    model_mood.py            # ramalan skor mood harian (RandomForest, data user)
    model_energi.py          # beban kerja + burnout (prior sintetis + kalibrasi personal)
    model_overwhelm.py       # risiko hari berat (LogisticRegression, belajar dari SOS)
    model_penenang.py        # opsi jeda mana yang beneran nolong (dari perubahan mood)
    model_pecah.py           # pungut pecahan tugas lama yang mirip (TFIDF char n-gram, 0 API)
    model_kalem.py           # ML_KALEM -- kalibrasi ringan next-action, tidur sampai data cukup
  data/
    bpom_index.json          # 8.960 obat, hasil olahan CSV BPOM (dibuat tools/)
    model_durasi.joblib      # model durasi pra-latih (opsional, dibuat tools/)
  views/
    onboarding.py            # 6 pertanyaan singkat (nama & umur wajib)
    morning_brief.py         # ★ Kalem nyapa duluan sekali sehari
    inbox.py                 # isi quick capture -> dirapikan jadi tugas
    home.py                  # Page 1 -- satu next-action + sesi fokus, bukan dashboard
    tracker.py                # Page 2 -- kalender, Eisenhower, Pecah Tugas
    mood.py                  # Page 3 -- check-in + insight + grafik bulan
    mood_chart.py             # kalender bulan buat halaman Mood
    diary.py                 # Cerita ke Kalem (dari Page 3)
    favorites.py             # menu Favorite (dari Page 3)
    reset.py                 # Page 4 (dari tombol "Lagi kewalahan?")
    med_setup.py             # setup obat sekali di awal + validasi BPOM
    settings.py               # profil, kartu status model, hapus data
DATASET/
  APP - Master Produk Komoditi Obat-<tanggal>.csv   # registri BPOM (23.437 baris)
  task_duration_dataset_id_lengkap.csv              # 549 tugas + durasi asli
  focusbuddy_dekomposisi_id.csv                     # 212 pola Pecah Tugas Indonesia (auto-load, lihat model_pecah.py)
  focusbuddy_task_decomposition_dataset_extended.csv # pola Inggris -- bahan terjemahan, TIDAK dimuat ke app
  focusbuddy_task_queries.csv                       # query berlabel buat tools/evaluasi_retrieval.py
tools/
  build_bpom_index.py        # CSV BPOM -> app/data/bpom_index.json
  latih_model_durasi.py      # CSV durasi -> app/data/model_durasi.joblib
  muat_dataset_pecah.py      # intip dataset Pecah Tugas (default = --lihat doang;
                              #   dataset-nya udah auto-load di app, lihat docstring
                              #   sebelum pakai --tulis-ke-storage)
  evaluasi_retrieval.py      # ukur retrieval model_pecah vs query berlabel
                              #   (precision/coverage/wrong-retrieval-rate)
  bikin_query_uji.py         # generate + jalanin query uji buat kalibrasi AMBANG_MIRIP
  tes_manual_kalem.py        # tes manual tiap model KALEM, input custom (storage-independent)
tests/
  test_regresi.py            # regresi -- `python tests/test_regresi.py`
  test_decision_quality.py   # skenario capacity-aware planning -- `python tests/test_decision_quality.py`
```

## Arsitektur: "Kalem sebagai satu otak"

Kelima fitur baca/tulis ke satu struktur data bersama, bukan nyimpen sendiri-sendiri:

- **Profil statis** (`storage.profile` + `favorites`) -- hasil onboarding & menu Favorite.
- **DayState harian** (`kalem_engine.DayState`) -- energi, mood, tugas, absen obat, riwayat SOS,
  favorit, sesi fokus, inbox. **Snapshot LENGKAP**, bukan cuma "hari ini".

`kalem_engine.decide()` jalanin satu urutan prioritas, dan tiap halaman pakai
bagian output yang beda:

| Urutan cek | Kondisi | Sumber keputusan |
|---|---|---|
| 0. Morning Brief | sekali per hari, sebelum Home tampil | `model_mood` + `model_energi` |
| 1. Nudge obat | ada jadwal & belum diabsen hari ini | rule-based (fakta, bukan prediksi) |
| 2. Pola berat | risiko kewalahan hari ini kebaca | `model_overwhelm` |
| 3. Next action | ada tugas belum selesai | rule-based (kuadran Eisenhower + kesulitan) |
| 4. Pesan tenang | nggak ada tugas | rule-based |

Output yang sama juga nyetir **durasi sesi fokus** di Tracker
(`focus_minutes_for`), **urutan opsi jeda** di Reset (`model_penenang`), dan
**ekspresi default Kalem** di Mood.

**Kenapa ada campuran rule-based + ML, bukan salah satu doang:** urutan
prioritas & pemilihan tugas next-action harus bisa dijelasin ke user dalam
satu kalimat dan nggak boleh probabilistik (terutama nudge obat & rujukan
krisis -- itu keputusan yang harus deterministik). Tapi "beban kerja hari ini
segimana", "mood bakal gimana", dan "risiko kewalahan segimana" itu justru
pas buat model yang belajar dari pola user -- rule tetap 2 syarat nggak bakal
pernah setajam itu. `kalem_engine.py` yang nentuin URUTAN & KAPAN masing-masing
dipanggil; `kalem_ml/` yang ngisi ANGKANYA.

### `decide()`/`build_morning_brief()` adalah fungsi murni

Ini yang bikin dua fungsi itu gampang dites: semua input datang dari
`(profile, day)` yang dioper, TIDAK ADA yang diam-diam baca `storage` lagi di
tengah jalan. `kalem_ml.fitur.bangun_fitur(now, day=day, profil=profile)`
menerima `day` yang sama itu dan meneruskannya ke semua model (`model_mood`,
`model_overwhelm`, `riwayat.baris_harian`) -- jadi ngasih `DayState` buatan ke
`decide()` beneran ngubah hasilnya, bukan diabaikan diam-diam.

`kalem_engine.snapshot()` adalah **satu-satunya** tempat engine ini nyentuh
`storage` langsung. Semua fungsi lain di bawahnya murni dari argumen.

### Cache model per-user, bukan per-proses

`model_mood` dan `model_overwhelm` nge-cache model yang udah dilatih di
variabel module-level (biar nggak retrain tiap render halaman). Kunci
cache-nya **sidik jari isi data** (`riwayat.sidik_jari()` -- hash SHA-256 dari
tanggal+skor+label tiap hari), BUKAN cuma jumlah baris.

Ini penting kalau app-nya di-host bareng buat beberapa orang (satu proses
server, storage per-session): kunci berbasis count doang bikin dua user yang
kebetulan punya jumlah catatan sama dianggap "data identik", dan user kedua
bisa dapet prediksi dari model yang dilatih pakai data user pertama.
Diverifikasi lewat tes: sebelum fix, user dengan mood 1/5 terus-terusan dapet
skor 2.69 (bocoran dari user lain yang mood-nya 5/5); sesudah fix, dapet 1.00.

## Model bisnis: free vs premium

Aturannya satu: **paywall ngunci kedalaman, bukan fungsi dasar.** Semua yang
bikin app ini kepakai tiap hari tetap gratis -- biar nggak pernah ada alasan
user cabut ke ChatGPT gratis.

| Fitur | Gratis | Premium |
|---|---|---|
| Tugas, mood, sesi fokus, SOS | penuh | penuh |
| Pecah Tugas (AI) | 3x/hari | tanpa batas |
| Morning Brief | ramalan hari ini + alasannya | + narasi pola lintas minggu |
| Insight mood | 1 temuan | semua temuan |
| Grafik mood | bulan berjalan | telusur bulan-bulan sebelumnya |
| Kartu rekomendasi | 1/minggu | tanpa batas |
| **Pengingat obat, validasi BPOM & cari apotek** | **penuh** | **penuh** |
| Riwayat kepatuhan obat | — | persentase, streak, ringkasan buat dokter |

**Kenapa pengingat obat TETAP gratis:** nggak kehabisan obat resep itu fungsi
dasar, bukan kenyamanan -- ngunci itu bakal ngelanggar aturan main di atas.
Yang dijual lapisan analisisnya.

Yang dibayar justru yang paling susah ditiru: Task breakdown bisa disaingi
ChatGPT (makanya tetap ada di free tier), tapi "Kalem yang inget pola kamu 2
bulan terakhir" butuh histori yang cuma numpuk kalau user stay.

> Harga rencana ~Rp19.000-29.000/bulan. Payment gateway beneran (Midtrans/
> Xendit) belum dibangun -- di build ini status premium di-toggle manual buat
> demo. App ini belum punya audio player sama sekali (musik = deep link ke
> Spotify/YouTube Music, bukan pemutar sendiri).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> **Catatan iCloud Drive / OneDrive:** kalau project ini disimpan di folder
> yang disinkron cloud, virtualenv (`.venv/`, ribuan file kecil) bisa
> di-*evict* ke cloud kalau nggak diakses beberapa hari, dan proses Python
> berikutnya jadi lambat banget (bahkan bisa keliatan macet) karena harus
> download ulang satu-satu. Solusinya bikin venv di luar folder yang disinkron,
> mis. `python3 -m venv ~/.venvs/focusbuddy`, dan jalanin app pakai
> `~/.venvs/focusbuddy/bin/python`.

### (Opsional) Aktifkan AI buat "Pecah Tugas" & kartu rekomendasi

Dua fitur ini jalan **tanpa** API key -- otomatis fallback ke template
rule-based. Buat versi AI-nya, isi salah satu (atau lebih) key AI:

```bash
cp .env.example .env
# isi satu atau lebih: GEMINI_API, OPENAI_API_KEY, DEEPSEEK_API_KEY
# opsional: AI_PROVIDER=gemini|openai|deepseek untuk memilih yang aktif
```

- Gemini -- key gratis di [Google AI Studio](https://aistudio.google.com/apikey)
- OpenAI -- [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- DeepSeek -- [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)

`.env` sudah masuk `.gitignore`. Bisa juga di-`export` manual lewat shell --
kalau ada, environment variable menang atas isi `.env`.

**Jangan pernah commit API key ke `.env.example`** -- file itu memang
di-commit ke repo (buat orang lain lihat formatnya), jadi harus selalu kosong.

#### Provider dipilih dari `.env`, bukan di-hardcode

`app/core/ai_client.py` adalah **satu-satunya** tempat di app ini yang tau
SDK Gemini/OpenAI/DeepSeek itu apa -- `decomposer_logic.py` &
`recommendations.py` cuma manggil `ai_client.generate_json(system_instruction,
prompt, schema, temperature)` dan nggak pernah tau provider mana yang
beneran jalan. Ganti provider = ganti `.env`, nol perubahan kode.

Provider aktif ditentuin `ai_client.active_provider()`:

1. `AI_PROVIDER=gemini|openai|deepseek` di `.env` kalau mau MAKSA salah satu.
2. Kalau nggak diisi, ditebak dari key yang ADA -- urutan menang
   **Gemini > OpenAI > DeepSeek** kalau lebih dari satu keisi sekaligus.
3. Nggak ada key sama sekali -> dua fitur fallback ke rule-based, sama
   kayak kalau API-nya lagi down.

DeepSeek sengaja nggak butuh SDK terpisah -- API-nya kompatibel sama SDK
`openai` (cuma beda `base_url` + nama model), jadi satu jalur kode yang
sama dipakai buat dua provider itu.

Model default per provider (`app/core/ai_client.py`): `gemini-flash-lite-latest`,
`gpt-4o-mini`, `deepseek-chat`. **Fitur obat sengaja NGGAK pakai AI sama
sekali, provider apa pun** -- lihat bagian Data Obat di bawah.

### Model kita dulu, baru AI

Data yang masuk ke API udah diolah model sendiri, bukan mentah. Dulu Gemini
disuruh nebak durasi tiap langkah; sekarang `kalem_ml.model_durasi` yang
ngitung, dan AI-nya cuma nulis teks langkahnya. Diukur di 3 tugas (pakai
Gemini, provider yang diukur pertama kali):

| | token output | total token | waktu |
|---|---|---|---|
| Gemini nebak menit | 409 | 486 | 1,70 dtk |
| Model kita duluan | **156** | **248** | **1,18 dtk** |
| | **-62%** | -49% | -30% |

Bonus yang lebih penting dari hemat token: angkanya jadi KONSISTEN. Perkiraan
di kartu tugas dan di rencana sekarang datang dari sumber yang sama. Output
JSON-nya dipaksa lewat structured output (bentuk persisnya beda per provider
-- `response_schema` di Gemini, mode JSON + validasi manual di OpenAI/DeepSeek,
urusan itu semua ada di `ai_client.generate_json()`), bukan cuma diminta
lewat prompt.

**Progres yang jujur, bukan spinner kosong.** `ui_helpers.ProgresAI` nampilin
bar progres yang panjangnya dari MEDIAN LATENSI PANGGILAN SEBELUMNYA
(`ai_client.perkiraan_lama()`, dihitung terpisah per provider), dan nggak
pernah nyentuh 100% sebelum jawabannya beneran nyampe.

### Kenapa `-lite`, bukan `gemini-flash-latest`

(Pemilihan model di bagian ini spesifik Gemini -- OpenAI & DeepSeek pakai
model default masing-masing yang belum diukur langsung kayak di bawah,
lihat komentar di `app/core/ai_client.py`.)

Diukur langsung ke API, bukan ditebak:

| Model | Kuota gratis | Thinking token |
|---|---|---|
| `gemini-flash-latest` (= `gemini-3.6-flash`) | **20 / hari** | ~1600-2000 per panggilan |
| `gemini-flash-lite-latest` | jauh lebih longgar | **0** |
| `gemini-2.5-flash` / `-lite` | 404 buat API key baru | - |

Kuota dihitung **per model**, jadi ganti model = jatah baru. Yang bikin 20/hari
kerasa sempit itu bukan pemakaian user (free tier app ini cuma 3 Pecah Tugas
per hari), tapi sesi ngoprek -- sekali testing bisa abis, terus semua fitur AI
diem-diem jatuh ke rule-based dan keliatan kayak "API-nya belum nyala".

## Menjalankan

```bash
flet run --web app/main.py      # browser -- paling gampang buat demo
flet run app/main.py            # jendela desktop
flet run --android app/main.py  # HP, lewat app Flet + scan QR
flet run --ios app/main.py # ios
```

Build jadi APK/IPA (butuh Flutter SDK, lihat [docs Flet](https://flet.dev/docs/publish)):

```bash
flet build apk app --module-name main
```

> `flet build` cari `main.py` di ROOT `python_app_path` yang dioper, bukan
> otomatis nyari ke dalam `app/`. Karena entry point project ini ada di
> `app/main.py`, harus dipanggil persis kayak di atas (`apk app`, bukan
> `apk`), plus `--module-name main`.

## Halaman

### Morning Brief -- Kalem nyapa duluan

Sekali sehari, sebelum Home biasa tampil, Kalem ngasih **ramalan hari ini**
duluan -- sebelum user diminta check-in apa pun:

> *"Hari ini kemungkinan bakal berat. (Jumat biasanya berat buat kamu · pola
> tidur lagi berantakan · energi terakhir rendah) Aku udah susunin: ambil yang
> paling ringan aja, sesi fokus 10 menit."*

**Kenapa ini beda dari insight di halaman Mood:** di sana prediksi cuma jadi
*kalimat* yang muncul SETELAH user check-in. Di sini prediksi jadi **aksi
default** -- tombol "Sesuai, mulai hari ini" langsung ngunci level energi hari
itu, jadi durasi sesi fokus di Tracker **dan** tombol FOKUS di Home ikut
nyesuain. Tombol "Aku ngerasa beda" nggak ngunci apa-apa; user yang nentuin.

Alasannya selalu ditulis ("kenapa Kalem mikir gitu") -- bukan kotak hitam.
Kalau catatan mood masih di bawah 5, brief-nya **ngaku belum bisa meramal**
dan pakai setelan tengah.

Ramalannya lewat `kalem_ml.model_mood.ramal()` (skor mood hari ini) +
`kalem_ml.model_energi.nilai()` (beban kerja & burnout, dikalibrasi rasio
penyelesaian tugas & sesi fokus user). Keduanya punya prior yang dicampur
pelan sama model yang belajar begitu datanya cukup -- nggak langsung ganti
total begitu ada 1 data baru.

> Push notification OS-level (biar muncul walau app ditutup) belum dibangun --
> brief-nya jalan berbasis "cek tanggal begitu app dibuka".

### Onboarding
6 pertanyaan singkat (di bawah semenit). Tiap jawaban nyetir minimal satu
fitur -- nggak ada data yang cuma nganggur. Nama & umur wajib; sisanya boleh
di-skip, dan skip **langsung** membawa ke Beranda (bukan lompat ke pertanyaan
berikutnya).

Sengaja **nggak** nanya diagnosis ADHD formal (biar user yang belum/nggak
sempat diagnosis tetap kepakai) dan nggak pakai skala klinis panjang (ASRS dsb).

### Page 1 -- Home
Jawaban satu pertanyaan: **"sekarang ngapain?"** -- bukan dashboard status.
Isinya cuma sapaan, **Kalem besar di tengah**, satu **kartu next-action**
(tugas prioritas + satu langkah pertama + tombol FOKUS), quick capture, dan
satu baris tenang ke halaman jeda.

**Mode fokus ngunci halaman lain.** Selama sesi jalan, pindah ke Tracker/
Mood/Settings bakal dicegat dialog: *"Kamu lagi ngerjain X — sisa 12:34.
Yuk selesaiin itu dulu."* User tetap bisa maksa pindah (sesinya dijeda dulu,
biar nggak keitung putus). **Halaman jeda SELALU boleh dibuka** -- ngunci
jalan keluar orang yang lagi kewalahan itu kebalikan dari tujuan app ini.

**Sesi fokus jalan DI SINI**, bukan pindah halaman. Nyalain timer nggak
sekadar "titip niat" ke Tracker terus mental ke halaman lain -- sesinya hidup
di `app/focus_session.py` (state module-level, bukan punya satu halaman), jadi
tetap jalan walau user keliling ke Tracker/Mood terus balik lagi. Timer-nya
lingkaran yang **menyusut** (bukan bar + digit), plus progress bar linear di
bawahnya.

Grid 4 kuadran Eisenhower **dipindah ke Tracker**: nampilin 4 kategori
keputusan sekaligus (apalagi pas angkanya masih 0) bikin overwhelm duluan
sebelum mulai apa-apa.

Tombol **"Lagi kewalahan?"** tetap selalu ada dan bisa dipencet kapan aja
(self-initiated), tapi tenang secara visual -- bukan banner merah full-width
yang bikin halaman ini kerasa darurat terus.

**Quick capture / brain dump:** satu tombol buat nulis apa pun yang keinget,
masuk antrian mentah tanpa harus langsung dirapikan jadi tugas. Badge
"n tersimpan" di kartunya buka **halaman Inbox** -- di situ tiap catatan bisa
di-"Jadiin tugas" (langkahnya dipecah otomatis pakai Task Decomposer yang
sama, dengan kuota Pecah Tugas yang sama -- jalur ini juga dicek, bukan celah
buat nembus limit 3x/hari) atau dihapus kalau udah nggak relevan.

### Page 2 -- Tracker
Halaman kerja. Default kalendernya **strip 7 hari**; bulan penuh baru muncul
kalau ditekan "Lihat bulan".

- **Add Task** dengan penanda mendesak/penting (Eisenhower), estimasi
  "seberat apa buat dimulai" (gampang/sedang/berat), dan opsional kategori +
  jumlah unit (buat perkiraan durasi personal).
- **Perkiraan durasi langsung dari judul tugas** -- `kalem_ml.model_durasi`
  baca TEKS judulnya (TFIDF n-gram huruf + RandomForest), nggak wajib pilih
  kategori dulu. Nampilin RENTANG ("15-40 menit"), bukan satu angka -- galat
  khasnya diukur ~faktor 2x, jadi angka pasti itu bohong yang keliatan presisi.
- **Grid 4 kuadran Eisenhower** ada di sini, bukan di Home.
- **Mini-timeline** "urutan yang disaranin": blok warna proporsional sesuai
  kuadran & tingkat kesulitan.
- **Pecah Tugas** (opsional, bisa pilih tugas mana aja) -- menata ulang tugas
  **hari ini** jadi slot waktu berurutan. Durasinya dari `model_durasi` dulu,
  AI-nya (Gemini/OpenAI/DeepSeek) cuma nulis kalimat langkahnya (lihat
  "Model kita dulu, baru AI" di atas). Kalau satu tugas dihapus, rencana disusun ulang otomatis --
  sisanya digeser, bukan ninggalin jam bolong.
- **Mendesak DIHITUNG dari deadline**, bukan ditanya ke user. Yang diisi
  cuma tanggal + jam (opsional); `storage.is_urgent()` ngitung ulang tiap
  kali dibaca. Versi lama pakai centang "Mendesak" -- dan centang itu beku:
  tugas yang dicentang "nggak mendesak" minggu lalu tetap ngaku gitu walau
  deadline-nya besok.
- **Level energi PINDAH ke halaman Mood.** Di sini dia ketimbun daftar tugas
  dan jarang kelihatan, padahal dia yang nyetel skala hari itu. Tracker
  tetap PAKAI angkanya (durasi sesi & ukuran langkah Pecah Tugas), cuma
  nggak nyediain UI buat ngubahnya lagi.
- **Rayaan kecil pas tugas kelar** -- overlay sedetik yang muncul & ilang
  sendiri. Cuma pas tugas BERUBAH jadi selesai, bukan tiap centang langkah:
  kalau tiap langkah dirayain, rayaannya kehilangan arti.

Tombol FOKUS di sini langsung mulai sesi yang tampil balik di Home.

### Page 3 -- Mood
**Level energi (1-6) ada di sini**, bukan di Tracker lagi. Alasannya: di
Tracker dia ketimbun daftar tugas dan jarang kelihatan, padahal dia yang
nyetel skala hari itu. Di sini dia nyatu sama check-in -- satu tempat, satu
momen, dan datanya langsung kepakai. Skalanya 1-6 (bukan 1-5) supaya nggak
ada "angka tengah aman". Cuma judul + chip angka -- keterangan efek di
bawahnya (durasi sesi fokus, ukuran langkah Pecah Tugas) sengaja nggak
ditulis di sini lagi, karena isinya ganti tiap chip dipencet dan bikin
bloknya goyang persis pas user lagi milih.

**Popup check-in pas buka app.** Sekali sehari, mood + energi ditanya lewat
dialog dua-tap di Beranda. Mood & energi itu yang nyetel skala hari itu;
kalau nunggu user inisiatif buka halaman ini, data yang paling nentuin
justru yang paling sering kosong. Tombol "Nanti aja" SENGAJA nggak nyimpen
apa-apa -- hari tanpa check-in harus beneran kosong, bukan diisi tebakan.

**Popup "udah makan hari ini?" -- cuma lewat jam 18.** Ditanya jam 9 pagi,
"belum" itu jawaban normal yang nggak berarti apa-apa. Ditanya jam 7 malam,
"belum" itu sinyal beneran, dan itu yang dipakai `neglect_streak()` buat
naikin `burnout_risk` (3 hari berturut-turut "belum makan/istirahat" ->
burnout kebaca, lepas dari mood). Popup ini nyusul OTOMATIS di Beranda
sesudah popup check-in (kalau belum check-in) atau langsung (kalau udah
check-in) -- dua tombol doang, "Udah"/"Belum", nggak ada "nanti" karena
dua-duanya jawaban yang sah. Di halaman Mood sendiri, baris "Udah makan hari
ini?" juga cuma nongol lewat jam 18, di atas "Istirahat cukup semalam?" yang
tetap kelihatan kapan pun (itu pertanyaan soal malam KEMARIN, jadi selalu
sah). Gerbangnya `storage.waktunya_tanya_makan()` / `perlu_tanya_makan()`.

**Mood dan energi dua sumbu yang beda.** Energi awalnya ditebak dari mood,
tapi begitu user nyentuh slidernya sendiri, tebakan berhenti nimpa -- orang
bisa sedih tapi masih ada tenaga, atau senang tapi drop.

Urutan chip mood NAIK dari kiri (paling berat) ke kanan (paling enak), kayak
skala rating pada umumnya. Versi lama urutannya nggak monoton (5,4,2,1,2) --
"lelah" nangkring di ujung setelah "sedih", kebaca kayak lelah lebih parah
dari sedih padahal skornya justru lebih tinggi.

Check-in mood lewat Kalem, plus **"Yang Kalem pelajari tentang kamu"**
(insight) dan **rekomendasi personal** langsung di bawahnya -- dua-duanya
jawaban atas pertanyaan yang sama, jadi kebaca sebagai satu alur: temuannya
dulu, baru saran yang keluar dari temuan itu. Insight-nya dari **model yang
belajar pola kamu sendiri**: hari apa mood cenderung bagus/berat, beda
weekday vs weekend, dan tema yang sering muncul di cerita kamu. Model ini
jujur bilang "masih belajar" sebelum datanya cukup (minimal 5 catatan), dan
baru pakai RandomForest setelah 10 catatan. Grafik riwayat langsung ke
**grafik bulanan** (garis + area) -- bar "7 catatan terakhir" yang dulu ada
di atasnya dibuang, karena nampilin hal yang sama dengan grafik bulanan tapi
seminggu doang, dan seminggu terlalu pendek buat kelihatan polanya.

**"Favorit kamu"** turun pangkat jadi ikon hati kecil di pojok kanan atas
halaman (pola yang sama kayak ikon Pengaturan di Beranda), bukan kartu
selebar halaman lagi -- dia pintu ke halaman lain yang jarang dibuka, bukan
bagian dari check-in harian. Hitungan "n/9 terisi" pindah ke tooltip.

Setelah check-in tersimpan, Kalem **otomatis nawarin nulis diary** -- momen
paling wajar buat nanya "kenapa harinya gitu", karena user baru aja mikirin
harinya.

**Diary, alias "Cerita Kamu"** (halaman terpisah): bukan cuma buat hari ini
-- cerita lama tetap tersimpan & bisa dibaca lagi di bawah form. Kata
kuncinya dicocokin ke **kamus tertutup** (capek, deadline, cemas, senang,
...) -- sengaja bukan sentiment analysis penuh, biar hasilnya bisa
dijelasin. Kalau satu tag berulang bareng mood rendah, Kalem **nanya soal
tag itu spesifik** di check-in berikutnya, bukan pertanyaan generik.

> Picker tag cepat ("Hari ini isinya apa? kuliah/kerja kelompok/dll") yang
> dulu ada di check-in Mood udah **dibuang** -- nggak satu pun model di
> `kalem_ml/` baca `quick_tags`, cuma dipakai buat milih prompt diary
> (`recurring_tag_prompt`). Tag lama yang udah kesimpen tetap ditulis balik
> apa adanya tiap nyimpen check-in, cuma UI buat milihnya udah nggak ada.

**Menu Favorite** (opsional, 9 kolom). Aturan mainnya: **field cuma boleh
nambah kalau ada fitur yang beneran makainya** -- nggak ada data nganggur.

| Favorit | Dipakai di |
|---|---|
| Musik | opsi "dengerin musik" di Reset (deep link Spotify/YouTube Music) |
| Comfort food | kartu "ambil dulu?" di Reset pas kewalahan |
| Hobi | kartu rekomendasi resep (kalau hobinya masak) |
| Tempat nyaman | saran pindah suasana di Reset (opsi gerak) |
| Kalimat penyemangat (tulisan sendiri) | dikutip balik di Reset & Morning Brief pas hari berat |
| Warna favorit | aksen di kartu Kalem punya user |
| Orang tempat cerita (nama panggilan) | ditawarin pas pola SOS berulang kedeteksi |
| Gerak ringan favorit | opsi "Gerak 60 detik" di Reset |
| Jam paling capek | Kalem nurunin ekspektasi + input Morning Brief |

Dua yang terakhir sengaja bukan teks bebas: warna butuh hex yang valid buat
dipakai jadi aksen UI, jam capek butuh rentang biar bisa dibandingin sama jam
sekarang.

**Soal privasi:** "orang tempat cerita" cuma nama panggilan -- app nggak
nyimpen kontak dan **nggak pernah ngehubungin siapa pun otomatis**. Kartunya
muncul di *samping* rujukan profesional, bukan gantiin.

### Page 4 -- Reset (dari tombol "Lagi kewalahan?")
Semua daftar tugas disembunyiin. **Nggak ada satu pun opsi yang nyentuh
daftar tugas** -- versi lama sempat punya "satu tugas 60 detik" yang narik
langkah dari tugas beneran, dan itu ngerusak janji halaman ini sendiri
("semua tugas lagi disembunyiin"), jadi dibuang.

Empat opsi: **napas 4-7-8** (lingkaran yang beneran mengembang/menyusut ikut
hitungan, bukan cuma angka mundur), **grounding 5-4-3-2-1** (teknik standar
buat cemas -- sebut hal yang dilihat/disentuh/didengar), **musik** (deep link
ke pencarian musik favorit user, atau lo-fi kalau belum diisi), dan **gerak 60
detik**.

Urutannya dari `kalem_ml.model_penenang` -- BUKAN sekadar hitung opsi mana
yang paling sering dipencet. Yang diukur: **mood user berubah gimana
SESUDAH** pakai opsi itu (dibanding sebelum). Opsi yang diulang-ulang belum
tentu yang nolong; bisa jadi justru yang nggak mempan, makanya diulang.
Sebelum ada histori pemakaian, urutan awal dari trigger overwhelm yang
disebut waktu onboarding.

Kalau user udah isi comfort food di Favorite, ada kartu tambahan "ambil
[comfort food] dulu?" -- aksi paling murah, nol usaha kognitif.

**Hotline TELEPON, bukan cuma tautan.** Nomor **119 ext. 8** (SEJIWA,
Kemenkes, gratis 24 jam) ditulis besar dan langsung bisa dipencet. Alasannya
praktis: tautan web bisa mati (dan pernah), butuh sinyal data, dan orang di
titik terburuk nggak sanggup navigasiin website dulu. Di bawahnya ada rujukan
telehealth (deep link ke Halodoc/Riliv/Into The Light).

**Deteksi pola distress** (rule-based, sengaja BUKAN ML): app bedain
overwhelm harian biasa dari pola yang lebih serius. Kalau SOS ditekan >= 3x
dalam 7 hari **dan** rata-rata mood <= 2/5, hotline naik ke paling atas dan
rujukan profesional lebih ditekankan. Keputusan yang ngarah ke rujukan krisis
harus deterministik & bisa dijelasin satu kalimat, jadi ini satu-satunya
bagian sinyal "berat" yang sengaja TIDAK lewat model belajar -- beda dari
`model_overwhelm` yang menentukan pesan lembut Kalem di Home (ambangnya lebih
longgar, dan itu bukan keputusan safety-critical).

Satu event SOS cuma dicatat SEKALI per pembukaan aktivitas (bukan tiap
render layar) -- biar mencet "kasih ide lain" berkali-kali nggak
diam-diam nge-trigger eskalasi.

### Medication Companion -- di belakang layar
Bukan halaman harian. User setup **sekali** (nama obat, stok, dosis harian).
Sesudah itu formnya nggak diisi lagi: **stok berkurang otomatis** tiap user
mencet "Udah minum" di Home. **7 hari** sebelum diprediksi habis, banner
muncul di Home yang nawarin **deep link ke Google Maps** "apotek terdekat"
atau tebus ke partner apotek daring.

**Nama obat divalidasi ke registri BPOM saat diketik** -- offline, instan
(~10ms), dari 8.960 nama obat resmi. Salah ketik disarankan ("Maksudnya
CONCERTA?"), nama zat aktif dikenali ("metilfenidat" -> merek yang
mengandungnya), dan golongan (Bebas/Terbatas/Keras/Psikotropika/Narkotika)
dibaca langsung dari struktur NIE-nya -- bukan tebakan. Nama yang nggak
ketemu (racikan apotek, jamu/suplemen yang memang di daftar BPOM lain) TETAP
BOLEH disimpan; nolak nyimpen bakal ngunci pengingat dari orang yang paling
butuh. Lihat "Data Obat (BPOM)" di bawah.

**Tidak diabsen = dianggap tidak diminum.** Kalau >=2 hari berturut-turut
nggak ada absen, Morning Brief menurunkan ekspektasi hari itu dan bilang
alasannya terang-terangan: *"obat kamu belum keabsen 4 hari terakhir"*.
Bukan menyuruh minum obat, bukan menyebut ini penyebabnya -- kalimatnya
eksplisit ngarahin ke dokter kalau ada yang mau didiskusikan.

Kenapa stok cuma turun saat diabsen, bukan dihitung dari tanggal setup:
nebak dari kalender bakal salah tiap kali user skip dosis, dan angka stok yang
bohong lebih bahaya daripada angka yang ketinggalan.

**Yang sengaja nggak ada: rekomendasi dosis, dan info obat dari AI.** Angka
dosis yang diisi user itu yang sudah ditentukan dokternya. Sempat ada fitur
"Kalem jelasin obatnya buat apa" lewat Gemini, dan itu **dibuang** -- urusan
obat itu tempat paling nggak pantas buat jawaban yang "kedengeran meyakinkan
tapi bisa keliru". Registri resmi (BPOM) yang dipakai sekarang, bukan LLM.

**Privasi:** data obat local-only, dan notifikasi pengingat ditulis netral.

> Push notification beneran (Firebase dkk) belum dibangun -- untuk sekarang
> pengingatnya muncul saat app dibuka.

### Hari tanpa check-in = kosong, bukan hari buruk

Masalah yang ditutup: catatan mood TERAKHIR dulu dipakai tanpa batas waktu.
Jadi kalau catatan terakhir user isinya "capek banget" lalu dia menghilang
seminggu, pas balik lagi Kalem MASIH nyaranin beban ringan berdasarkan
perasaan seminggu lalu -- capeknya divalidasi terus-terusan, dan justru bikin
makin nggak jalan.

Tiga hal yang sekarang dipegang:

1. **Ada batas kedaluwarsa** (`storage.STALE_AFTER_DAYS = 3`). Lewat itu,
   `energi_terakhir` balik ke netral dan `streak_abai` di-nol-in -- bukan
   diwarisin dari catatan lama. "Nggak tau" itu jawaban yang lebih jujur
   daripada nganggep user masih kelaparan seminggu kemudian.
2. **Hari bolong nggak diisi tebakan.** `riwayat.baris_harian()` cuma bikin
   baris latih dari hari yang BENERAN ada check-in-nya. Nggak ada
   interpolasi, nggak ada "kemungkinan hari itu buruk".
3. **Kalem nyapa, bukan meramal.** Morning Brief ganti jadi *"Udah 10 hari
   nggak ketemu. Seneng kamu balik lagi. Aku sengaja nggak nebak-nebak hari
   kamu dari catatan lama — itu udah lewat."*

Absen NGGAK diperlakukan sebagai sinyal buruk maupun baik. Bisa lupa, bisa
lagi berat beneran, dan dua-duanya nggak pantes ditebak-tebak. Fitur
`hari_sejak_checkin` tetap masuk ke model sebagai konteks, tapi nggak pernah
jadi dasar buat nge-judge.

## Menjalankan tes

```bash
python tests/test_regresi.py
```

Nggak butuh pytest. Tiap tes bikin storage sendiri di folder temp, jadi data
asli di `~/.focusbuddy` nggak pernah kesentuh. Yang dicakup: mendesak dari
deadline, data basi, hari kosong, urutan mood, isolasi model antar-user,
kemurnian `decide()`, komponen UI baru, kunci mode fokus, gerbang jam
pertanyaan "udah makan?" (termasuk geseran jam yang nyebrang tengah malam),
dan semua halaman
kebangun.

## Limitasi yang Wajib Didisclose

- **Pecah Tugas & kartu rekomendasi bergantung API AI pihak ketiga**
  (Gemini/OpenAI/DeepSeek, pilih salah satu lewat `.env` -- lihat
  `ai_client.py`). Ada fallback rule-based buat Pecah Tugas, tapi ini bukan
  solusi 100% mandiri.
- **`model_energi` punya prior dari data SINTETIS** (`generate_synthetic_data`
  di `energy_predictor.py`), karena app belum punya histori pengguna riil
  buat semua kondisi. Dikalibrasi ke data user asli begitu ada histori
  (rasio penyelesaian tugas, rasio sesi fokus yang kelar).
- **`model_mood` & `model_overwhelm` belajar dari data user asli**, tapi
  butuh waktu -- di bawah ambangnya (5 & 10 hari) mereka jujur ngaku belum
  bisa/pakai prior rule-based yang jelas ditandai.
- **`model_durasi` dilatih dari 549 tugas contoh** (bukan tugas user sendiri)
  + kecepatan personal user begitu ada minimal 2 sesi di kategori yang sama.
  Galat khas diukur ~faktor 2x, makanya ditampilin rentang, bukan angka pasti.
- **Deteksi distress di halaman Reset rule-based, bukan diagnosis.** Cuma
  trigger rujukan, sengaja nggak pakai model belajar untuk keputusan ini.
- **Medication Companion bukan alat diagnosis / pengganti dokter**, dan nggak
  pernah nyaranin dosis. Validasi nama obat dari registri BPOM bisa aja nggak
  nemu obat yang beneran ada (racikan, obat baru yang belum masuk data).
  Pencarian apotek diserahin ke Google Maps -- app ini sengaja nggak bikin
  data "lokasi apotek" sendiri yang isinya karangan.
- **Stok obat cuma seakurat absen user.** Kalau user nggak pernah mencet "udah
  minum", angkanya nggak gerak (dan Kalem bakal nanya terus).
- FocusBuddy **bukan layanan krisis** dan nggak menggantikan diagnosis ADHD formal.

## Data

Semua data (profil, tugas, mood, diary, favorit, obat) disimpan **lokal** di
`~/.focusbuddy/data.json` (schema v3, migrasi otomatis dari v1/v2).
Nggak ada server eksternal di build ini -- **satu file storage, satu user**.
Kalau nanti di-hosting buat banyak orang sekaligus, storage-nya perlu
dipisah per-session (di luar scope build ini); lapisan model (`kalem_ml/`)
sendiri sudah aman dipakai lintas-user (lihat "Cache model per-user" di atas).

### Auto Feel — data demo instan

Model mood/energi baru kelihatan pinter kalau udah ada histori. Daripada
check-in manual berkali-kali sambil mencet "Maju 1 hari", pakai
**`SettingDemo.py`** di folder utama: isi/tambah skenario di situ, lalu
pilih lewat ikon tongkat sihir di Beranda (atau `python SettingDemo.py
<skenario>` dari terminal).

Riwayat panjang (sampai 90 hari) di-*generate* dari seed acak yang TETAP
(`random.Random(seed)`), bukan ditulis manual satu-satu -- nulis ratusan
baris `mood_history` per tangan nggak kepraktisan dan gampang salah hitung
tanggal/hari. Jadwal kuliah 1 semester (`JADWAL_KULIAH`) jadi konstanta
bersama yang otomatis muncul jadi tugas "hari ini" di **SEMUA** skenario,
bukan cuma yang eksplisit nyebut jadwal berat.

10 skenario bawaan:

| Key | Isi |
|---|---|
| `baru` | Belum ada histori sama sekali |
| `kuliah_2minggu` | 14 hari, SUBS OFF, 1 dari 2 minggu berat (Kamis-Jumat numpuk quiz/deadline) |
| `sebulan_off` | 30 hari, SUBS OFF, 2-3 dari 4 minggu berat (dipilih acak) |
| `sebulan_on` | Sama seperti di atas, SUBS ON |
| `3bulan_jenuh_off` | 90 hari aktif, SUBS OFF, event acak senang:jenuh = 1:2 |
| `3bulan_senang_off` | 90 hari aktif, SUBS OFF, event acak senang:jenuh = 2:1 |
| `3bulan_jenuh_on` | Sama seperti `3bulan_jenuh_off`, SUBS ON |
| `3bulan_senang_on` | Sama seperti `3bulan_senang_off`, SUBS ON |
| `krisis_sos` | 90 hari, SOS ditekan >5x, kepatuhan obat ~50%, hampir tiap minggu berat |
| `jarang_checkin` | Cuma 15-20/30 hari ke-check-in, diary nyaris kosong, SOS malah sering (termasuk di hari TANPA check-in) |

File-nya isinya data + generator kecil buat data itu doang, nggak ada logika
app -- dan otomatis reset cache model (`kalem_ml.reset_semua()`) tiap ganti
skenario biar nggak nyampur sama model skenario sebelumnya.

Tombol **SUBS** (ikon medali) nyalain/matiin status premium seketika buat
nunjukin gating ke juri tanpa flow pembayaran.

Buat testing ada 5 tombol di pojok kanan atas Home:

- **Maju 1 hari** -- nggeser tanggal (`app/clock.py`), semua fitur yang
  bergantung tanggal ikut.
- **Lompat ke malam** (ikon bulan/matahari, TOGGLE) -- majuin **jam**
  aplikasi sampai lewat jam 18 tanpa nyentuh tanggal, khusus buat nunjukin
  fitur yang gerbangnya jam (pertanyaan "udah makan?"). "Maju 1 hari" nggak
  nolong buat ini -- dia cuma geser tanggal, jamnya tetap jam asli. Pencet
  lagi buat balik ke jam asli tanpa ngerusak geseran hari yang udah dipasang.
- **Tutup & buka lagi app** (ikon logout) -- ngulang alur pembukaan app dari
  awal (Morning Brief nyapa lagi, popup check-in/makan ikut kepancing) tanpa
  bener-bener matiin app di depan juri. Nggak nyentuh data sama sekali --
  cuma penanda "brief hari ini udah tampil" yang direset.
- **SUBS on/off**.
- **Auto Feel** -- pilih salah satu dari 10 skenario di atas.

"Reset data" **NGGAK** ada di header Home -- itu udah pindah permanen ke
Pengaturan (`ui_helpers.show_reset_confirm`), biar nggak ada dua pintu ke
aksi yang sama-sama nggak bisa dibalikin. Kelima tombol di atas di-gate
`config.DEMO_MODE`; ganti ke `False` sebelum rilis publik dan semua ilang
otomatis, nggak perlu ubah `home.py`.

## Catatan teknis

**ColorScheme.** Spesifikasi awal pakai `ColorScheme(background=...,
on_background=...)`. Di Flet 0.86 (Material 3) dua field itu sudah dihapus dan
diganti `surface`/`on_surface` -- warnanya tetap sama persis, cuma dipetakan ke
nama field yang baru di `app/theme.py`.

**Letak folder assets.** Harus `app/assets/` (sejajar `main.py`), bukan di root
project. CLI `flet run` otomatis nyetel env var `FLET_ASSETS_DIR` ke
`<folder_script>/assets` dan itu meng-override argumen `assets_dir` di kode --
kalau foldernya di tempat lain, semua SVG Kalem bakal 404.

**Lebar tombol.** Di dalam `Column`, `expand=True` ngatur tinggi, bukan lebar.
Buat CTA full-width pakai `ui_helpers.wide_button()` (yang mbungkus tombolnya
di `Row`), bukan `primary_button(expand=True)`.

**`python3` di macOS butuh sertifikat CA.** Kalau `pip`/`flet build` gagal
dengan `SSLCertVerificationError`, jalanin `/Applications/Python 3.x/Install
Certificates.command` -- Python dari installer resmi nggak otomatis makai
sertifikat sistem.

## Data Obat (BPOM)

Validasi nama obat jalan **offline** dari registri resmi BPOM, bukan dari AI.

```
DATASET/APP - Master Produk Komoditi Obat-<tanggal>.csv   # sumber, 23.437 baris, 4,8 MB
        |
        |  python tools/build_bpom_index.py
        v
app/data/bpom_index.json                          # 8.960 nama unik, 1,66 MB
```

Yang dipakai app: nama resmi, **NIE** (nomor izin edar), golongan, komposisi,
bentuk sediaan, masa berlaku. Huruf ke-2 NIE nentuin golongan -- `B`ebas,
bebas `T`erbatas, `K`eras, `P`sikotropika, `N`arkotika -- jadi app bisa bilang
"ini wajib resep dokter" sebagai fakta registri, bukan tebakan.

Empat lapis pencocokan (`app/core/bpom.py`), dari yang paling ketat: (1) nama
persis, (2) nama tanpa angka kekuatan sediaan ("Concerta 18mg" -> "CONCERTA"),
(3) nama zat aktif (ejaan Indonesia & internasional diseragamkan otomatis:
"metilfenidat" = "methylphenidate"), (4) tebakan salah ketik (ambang kemiripan
diukur lewat uji, bukan ditebak).

Bikin ulang indeksnya cuma perlu kalau CSV-nya di-update:

```bash
python tools/build_bpom_index.py
```

**Yang nggak ada di dataset ini:** jamu, herbal, dan suplemen didaftarin BPOM
di daftar terpisah (nomor TR/SD/POM). Jadi "Tolak Angin" bakal balik "nggak
ketemu" -- itu bener, bukan bug.

## Model Kalem (`app/kalem_ml/`)

Satu file per model, satu lapisan fitur bersama (`fitur.py`) -- semua model
baca angka dari sana, bukan hitung ulang sendiri-sendiri.

| File | Belajar apa | Sumber | Ambang mulai belajar |
|---|---|---|---|
| `fitur.py` | — (lapisan fitur, ~45 sinyal) | `DayState` / storage | — |
| `riwayat.py` | — (rekonstruksi fitur per hari lampau) | `DayState` / storage | — |
| `model_durasi.py` | Judul tugas → rentang menit | `DATASET/task_duration_dataset_id_lengkap.csv` (549) + sesi user | 2 sesi/kategori |
| `model_mood.py` | Ramalan skor mood harian | catatan user | 5 catatan (pola), 10 (RandomForest) |
| `model_energi.py` | Beban kerja + burnout | 500 baris sintetis + kalibrasi user | jalan dari hari-1 |
| `model_overwhelm.py` | Risiko hari berat | hari user mencet SOS | 10 hari ber-label |
| `model_penenang.py` | Opsi jeda yang beneran nolong | perubahan mood sesudah pakai | 4x pemakaian |

Semua **sudah tersambung ke `kalem_engine.py`** (bukan cuma dilaporkan lewat
kartu status di Settings) -- `model_overwhelm` nentuin pesan "pola berat" di
Home, `model_mood`+`model_energi` nyusun Morning Brief, `model_penenang`
ngurutin opsi jeda, `model_durasi` ngisi perkiraan waktu di Tracker & Pecah
Tugas.

**Lima aturan yang dipegang semua model:**

1. **Jujur soal tahap.** Di bawah ambang, model ngaku "belum kebaca" atau
   pakai prior yang ditandai jelas. Nggak ada yang ngarang pola dari 3 hari.
2. **Prior dicampur, bukan diganti.** Bobot model naik pelan seiring data
   numpuk (`w = n / (n + 20)`), biar tebakannya nggak ayun-ayunan.
3. **Koreksi cuma nurunin target.** Salah nyaranin terlalu ringan ruginya
   kecil; salah nyaranin terlalu berat bikin hari gagal.
4. **Angka mentah nggak dipajang.** Skor risiko & probabilitas dipakai buat
   ngatur nada, bukan ditunjukin sebagai nilai rapor.
5. **Fungsi murni dari argumen.** `nilai()`/`ramal()` terima `Fitur` (bisa
   dibangun dari `DayState` buatan buat testing), model TIDAK baca `storage`
   diam-diam di tengah jalan. Cache-nya dikunci dari isi data (sidik jari),
   bukan cuma jumlah baris -- lihat "Cache model per-user" di atas.

### Melatih ulang

```bash
python tools/build_bpom_index.py      # indeks obat dari DATASET/
python tools/latih_model_durasi.py    # model durasi -> app/data/*.joblib
```

Dua-duanya opsional: app tetap jalan tanpa artefaknya (model durasi dilatih
sendiri saat pertama dipakai, ~1,6 detik).

### Hubungan energi-kecepatan: dipelajari, bukan dikarang

Dataset durasi SENGAJA nggak punya kolom "energi saat itu", dan itu keputusan
sadar. Dataset isinya tugas orang lain -- nambahin kolom energi ke situ artinya
ngarang angka (energi siapa, diukur kapan?). Lebih parah lagi: seberapa jauh
energi rendah ngelambatin orang itu BEDA-BEDA per orang, jadi koefisien
rata-rata populasi malah bisa nyesatin.

Sesi fokus user udah nyimpen `energi` apa adanya. Dari situ dihitung faktor
kalibrasi PER PITA ENERGI (rendah 1-2, sedang 3-4, tinggi 5-6):

```
sesi user: energi 2 -> rencana 30m, nyata 60m   (4 sesi)
           energi 5 -> rencana 30m, nyata 24m   (4 sesi)

faktor  : energi 2 = 1.70   global = 1.40   energi 5 = 1.10
perkiraan tugas yang sama: 77 menit vs 60 menit
```

Butuh minimal 3 sesi dalam satu pita sebelum faktornya dipercaya; di bawah itu
balik ke faktor global. Dan faktor per-pita ditarik separuh jalan ke global --
sesi per-pita selalu lebih sedikit, jadi lebih berisik.

### Kejujuran akurasi model durasi

Diukur 5-fold CV di 549 baris:

```
baseline (selalu tebak median 30 mnt)   MAE_log 0.952
TFIDF huruf + RandomForest, 300 fitur   MAE_log 0.755   <- dipakai
```

Galat khasnya **faktor ~2x**. Makanya yang ditampilin RENTANG, bukan satu
angka — dan pita 25–75% itu terkalibrasi (50% data asli jatuh di dalamnya).

### Latensi predict, diukur & dioptimasi

`model_mood` sempat makan ~50ms per panggilan gara-gara `n_jobs=-1` di
`RandomForestRegressor` -- buat predict SATU baris, overhead spin-up
parallel backend-nya lebih mahal dari kerjaannya sendiri. Dibuang +
jumlah pohon diturunin dari 200 ke 100 (hasil prediksi diverifikasi
IDENTIK di data uji): jadi ~12ms.

`model_durasi` masih ~70ms per panggilan (dipakai live pas ngetik judul tugas
di dialog Tambah Tugas) -- itu dari loop manual 300 pohon buat ngitung pita
kuantil (bukan `n_jobs`), desain yang sengaja dipilih dan udah divalidasi
lewat 5-fold CV. Belum disentuh di optimasi ini karena ubah jumlah pohon di
situ butuh re-validasi akurasi, bukan cuma ukur kecepatan.
