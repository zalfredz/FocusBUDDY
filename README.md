# FocusBuddy

Micro-planning app buat orang dengan kecenderungan ADHD/executive dysfunction.
Ditemenin **Kalem**, karakter buddy yang ekspresinya ngikutin mood kamu.

Dibangun 100% **Python** lewat [Flet](https://flet.dev) -- UI dirender Flutter,
jadi bisa jalan sebagai app Android/iOS beneran (`flet build`) atau langsung di
browser buat demo. Nggak perlu nulis Dart/JS.

## Struktur

```
app/
  assets/                    # 5 ekspresi Kalem (SVG) -- harus sejajar main.py,
    kalem_semangat.svg       #   itu yang dicari `flet run` (FLET_ASSETS_DIR)
    kalem_tenang.svg  kalem_cemas.svg  kalem_sedih.svg  kalem_lelah.svg
  config.py                  # DEMO_MODE -- gate tombol testing di Home
  main.py                    # router: 3 tab nav + halaman ekstra
  theme.py                   # palet + font Lexend/Quicksand
  buddy.py                   # Kalem: MOOD_ASSETS, MOOD_SCORE, komponen UI
  storage.py                 # persistensi lokal (~/.focusbuddy/data.json)
  clock.py                   # sumber tunggal "hari ini" (buat tombol next-day)
  focus_session.py           # sesi fokus global, hidup di luar halaman mana pun
  ui_helpers.py
  core/
    kalem_engine.py          # ★ decision engine: satu otak buat semua halaman
    decomposer_logic.py      # pecah tugas HARI INI -> slot waktu (Gemini + fallback)
    energy_predictor.py      # Decision Tree (data sintetis), skala energi 1-6
    mood_model.py            # pola mood + tag cepat + kata kunci diary
    reset_preferences.py     # personalisasi opsi penenang + deteksi distress
    medication_model.py      # proyeksi stok obat + dosis kelewat + link apotek
    bpom.py                  # validasi nama obat dari registri BPOM (offline)
    duration_predictor.py    # RandomForest + rata-rata personal -> perkiraan menit
    recommendations.py       # kartu rekomendasi musik/resep dari Favorit
  data/
    bpom_index.json          # 8.960 obat, hasil olahan CSV BPOM (dibuat tools/)
  views/
    onboarding.py            # 6 pertanyaan singkat (nama & umur wajib)
    morning_brief.py         # ★ Kalem nyapa duluan sekali sehari
    inbox.py                 # isi quick capture -> dirapikan jadi tugas
    home.py                  # Page 1 -- satu next-action, bukan dashboard
    tracker.py               # Page 2 -- halaman kerja
    mood.py                  # Page 3
    diary.py                 # Cerita ke Kalem (dari Page 3)
    favorites.py             # menu Favorite (dari Page 3)
    reset.py                 # Page 4 (dari tombol "Lagi kewalahan?")
    med_setup.py             # setup obat sekali di awal
```

## Arsitektur: "Kalem sebagai satu otak"

Kelima fitur baca/tulis ke satu struktur data bersama, bukan nyimpen sendiri-sendiri:

- **Profil statis** (`storage.profile` + `favorites`) -- hasil onboarding & menu Favorite.
- **DayState harian** (`kalem_engine.DayState`) -- energi, mood, tugas, absen obat, riwayat SOS.

`kalem_engine.decide()` jalanin satu urutan prioritas, dan tiap halaman pakai
bagian output yang beda:

| Urutan cek | Kondisi | Dipakai di |
|---|---|---|
| 0. Morning Brief | sekali per hari, sebelum Home tampil | halaman `morning_brief` |
| 1. Nudge obat | ada jadwal & belum diabsen hari ini | pesan + tombol di Home |
| 2. Pre-escalation | SOS >= 2x dalam 3 hari **dan** mood rata-rata <= 3 | Kalem nyapa duluan di Home |
| 3. Next action | ada tugas belum selesai | kartu utama Home |
| 4. Pesan tenang | nggak ada tugas | Home |

Output yang sama juga nyetir **durasi sesi fokus** di Tracker
(`focus_minutes_for`), **urutan opsi calming** di Reset, dan **ekspresi default
Kalem** di Mood. Semuanya rule-based -- urutannya harus bisa dijelasin dalam
satu kalimat, dan nggak butuh data latih.

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
| **Pengingat obat & cari apotek** | **penuh** | **penuh** |
| Riwayat kepatuhan obat | — | persentase, streak, ringkasan buat dokter |

**Kenapa pengingat obat TETAP gratis** (beda dari draf awal yang ngunci penuh):
nggak kehabisan obat resep itu fungsi dasar, bukan kenyamanan -- ngunci itu
bakal ngelanggar aturan main di atas. Yang dijual lapisan analisisnya. Ini juga
jawaban yang lebih kuat kalau juri nanya soal etika: *"kami nggak masang
paywall di keselamatan."*

Yang dibayar justru yang paling susah ditiru: Task breakdown bisa disaingi
ChatGPT (makanya tetap ada di free tier), tapi "Kalem yang inget pola kamu 2
bulan terakhir" butuh histori yang cuma numpuk kalau user stay.

> Harga rencana ~Rp19.000-29.000/bulan. Payment gateway beneran (Midtrans/
> Xendit) belum dibangun -- di build ini status premium di-toggle manual buat
> demo. Custom soundscape yang ada di rencana awal juga belum: app ini belum
> punya audio sama sekali.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### (Opsional) Aktifkan AI buat "Pecah Tugas"

Fitur ini jalan **tanpa** API key -- otomatis fallback ke template rule-based.
Buat versi AI-nya, ambil key gratis di
[Google AI Studio](https://aistudio.google.com/apikey):

```bash
cp .env.example .env
# lalu isi GEMINI_API_KEY=... di file .env
```

`.env` sudah masuk `.gitignore`. Bisa juga di-`export` manual lewat shell --
kalau ada, environment variable menang atas isi `.env`.

Model default `gemini-flash-lite-latest` -- tier PALING RENDAH yang tersedia,
dan (diukur) juga yang paling cepat: 1,21 dtk vs 1,71 dtk buat `3.1-flash-lite`.
Di-set satu tempat di `app/core/ai_client.py`, dipakai bareng sama DUA fitur:
Pecah Tugas dan kartu rekomendasi.

### Model kita dulu, baru Gemini

Data yang masuk ke API udah diolah model sendiri, bukan mentah. Dulu Gemini
disuruh nebak durasi tiap langkah; sekarang `model_durasi` yang ngitung, dan
Gemini cuma nulis teks langkahnya. Diukur di 3 tugas:

| | token output | total token | waktu |
|---|---|---|---|
| Gemini nebak menit | 409 | 486 | 1,70 dtk |
| Model kita duluan | **156** | **248** | **1,18 dtk** |
| | **-62%** | -49% | -30% |

Bonus yang lebih penting dari hemat token: angkanya jadi KONSISTEN. Perkiraan
di kartu tugas dan di rencana sekarang datang dari sumber yang sama. Fitur obat sengaja NGGAK pakai AI sama sekali -- lihat
bagian Data Obat di bawah. Output JSON-nya dipaksa lewat
`response_schema` Gemini (structured output), bukan cuma diminta lewat prompt.

### Kenapa `-lite`, bukan `gemini-flash-latest`

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

Kualitas Pecah Tugas versi lite udah dites setara buat kerjaan ini: langkah
konkret, langkah pertama di bawah 5 menit, dan nurut sama level energi.

## Menjalankan

```bash
flet run --web app/main.py      # browser -- paling gampang buat demo
flet run app/main.py            # jendela desktop
flet run --android app/main.py  # HP, lewat app Flet + scan QR
```

Build jadi APK/IPA (butuh Flutter SDK, lihat [docs Flet](https://flet.dev/docs/publish)):

```bash
flet build apk
```

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
dan pakai setelan tengah, konsisten sama `mood_model.analyse()` yang nggak
pernah ngarang pola dari data yang belum cukup.

Nggak ada model baru: ramalannya dari `mood_model._predict_today()` +
`energy_predictor.predict_workload()` yang udah ada. Yang berubah cuma
**kapan** hasilnya keluar dan **bentuknya**.

> Push notification OS-level (biar muncul walau app ditutup) belum dibangun --
> brief-nya jalan berbasis "cek tanggal begitu app dibuka", sama seperti
> keputusan di Medication Companion.

### Onboarding
6 pertanyaan singkat (di bawah semenit). Tiap jawaban nyetir minimal satu
fitur -- nggak ada data yang cuma nganggur. Ada pintu keluar **"Aku lagi nggak
pengen jawab-jawab"**: cukup nama, sisanya pakai default netral.

Sengaja **nggak** nanya diagnosis ADHD formal (biar user yang belum/nggak
sempat diagnosis tetap kepakai) dan nggak pakai skala klinis panjang (ASRS dsb).

### Page 1 -- Home
Jawaban satu pertanyaan: **"sekarang ngapain?"** -- bukan dashboard status.
Isinya cuma sapaan, **Kalem besar di tengah**, satu **kartu next-action**
(tugas prioritas + satu langkah pertama + tombol FOKUS), quick capture, dan
satu baris tenang ke halaman jeda.

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
sama) atau dihapus kalau udah nggak relevan.

### Page 2 -- Tracker
Halaman kerja. Default kalendernya **strip 7 hari**; bulan penuh baru muncul
kalau ditekan "Lihat bulan".

- **Add Task** dengan penanda mendesak/penting (Eisenhower) + estimasi
  "seberat apa buat dimulai" (gampang/sedang/berat).
- **Grid 4 kuadran Eisenhower** ada di sini, bukan di Home.
- **Mini-timeline** "urutan yang disaranin": blok warna proporsional sesuai
  kuadran & tingkat kesulitan.
- **Pecah Tugas** (opsional) -- menata ulang tugas **hari ini** jadi slot waktu
  berurutan lengkap dengan jeda.
- **Level energi 1-6** (sengaja bukan 1-5 supaya nggak ada "angka tengah
  aman"). Ini **beneran nyetir durasi sesi fokus**: energi 1 -> 5 menit,
  energi 6 -> 30 menit, dan alasannya ditulis di bawah timer.
- **Sesi fokus pakai lingkaran yang menyusut**, bukan bar lurus + digit --
  riset time blindness ADHD nunjukin visual "disk mengecil" (ala Time Timer)
  jauh lebih kebaca daripada angka.

Tombol FOKUS di Home langsung nyalain timer di sini dengan durasi yang udah
disesuaikan.

### Page 3 -- Mood
Check-in mood lewat Kalem, plus insight dari **model yang belajar pola kamu
sendiri**: hari apa mood cenderung bagus/berat, beda weekday vs weekend, dan
tema yang sering muncul di cerita kamu. Model ini jujur bilang "masih belajar"
sebelum datanya cukup (minimal 5 catatan), dan baru pakai Decision Tree
setelah 10 catatan.

**Tag cepat:** sebelum (atau tanpa) nulis cerita, user bisa pencet 0-3 tag
(kuliah, kerja kelompok, keluarga, sendirian, dll) dalam hitungan detik. Ini
bikin data tetap masuk di hari-hari user males ngetik. Ada juga chip
**"+ Lainnya"** buat ngetik tag sendiri (mis. "sidang proposal") lewat input
inline -- tag custom tetap kehitung ke batas maks 3, jadi nggak balik jadi
checklist panjang.

**Diary** (halaman terpisah): tombol "Cerita tentang hari ini?" -- user cerita
ke Kalem. Kata kuncinya dicocokin ke **kamus tertutup** (capek, deadline,
cemas, senang, ...) -- sengaja bukan sentiment analysis penuh, biar hasilnya
bisa dijelasin. Kalau satu tag berulang bareng mood rendah, Kalem **nanya soal
tag itu spesifik** di check-in berikutnya, bukan pertanyaan generik.

**Menu Favorite** (opsional, 9 kolom). Aturan mainnya: **field cuma boleh
nambah kalau ada fitur yang beneran makainya** -- nggak ada data nganggur.

| Favorit | Dipakai di |
|---|---|
| Musik | opsi "dengerin musik" di Reset |
| Comfort food | afirmasi Kalem |
| Hobi | saran micro-task 60 detik |
| Tempat nyaman | saran pindah suasana |
| Kalimat penyemangat (tulisan sendiri) | dikutip balik di Reset & Morning Brief pas hari berat |
| Warna favorit | aksen di kartu Kalem punya user |
| Orang tempat cerita (nama panggilan) | ditawarin pas pola SOS berulang kedeteksi |
| Gerak ringan favorit | saran micro-task versi gerak badan |
| Jam paling capek | Kalem nurunin ekspektasi + input Morning Brief |

Dua yang terakhir sengaja bukan teks bebas: warna butuh hex yang valid buat
dipakai jadi aksen UI, jam capek butuh rentang biar bisa dibandingin sama jam
sekarang.

**Soal privasi:** "orang tempat cerita" cuma nama panggilan -- app nggak
nyimpen kontak dan **nggak pernah ngehubungin siapa pun otomatis**. Kartunya
muncul di *samping* rujukan profesional, bukan gantiin: orang terdekat dan
tenaga terlatih beda peran. Kalimat penyemangat sengaja diminta pakai kalimat
user sendiri, bukan kutipan orang lain (aman dari isu hak cipta).

### Page 4 -- Reset (dari tombol OVERWHELMED)
Semua daftar tugas disembunyiin. Ditawarin opsi penenang: **musik**,
**latihan napas 4-7-8** (dipandu, ada hitungan mundur), atau **satu tugas 60
detik**. Pilihan user dicatat (hitung frekuensi, bukan ML) supaya opsi yang
paling ngebantu naik ke atas.

Ada juga **rujukan telehealth** (deep link ke Halodoc/Riliv/Into The Light) --
bukan bangun sistem sesi psikolog sendiri, karena berat secara regulasi dan
cuma nge-duplikasi yang sudah ada. Ini sekaligus titik komisi rujukan.

**Deteksi pola distress:** app bedain overwhelm harian biasa dari pola yang
lebih serius. Kalau SOS ditekan >= 3x dalam 7 hari **dan** rata-rata mood <= 2/5,
halaman ini berhenti nawarin musik duluan dan naikin rujukan profesional ke
paling atas.

### Medication Companion -- di belakang layar
Bukan halaman harian. User setup **sekali** (nama obat, stok, dosis harian).
Sesudah itu formnya nggak diisi lagi: **stok berkurang otomatis** tiap user
mencet "Udah minum" di Home (`stok -= dosis_harian`, idempotent per hari).
**7 hari** sebelum diprediksi habis, banner muncul di Home yang nawarin
**deep link ke Google Maps** "apotek terdekat" atau tebus ke partner apotek
daring (titik komisi afiliasi).

Kenapa stok cuma turun saat diabsen, bukan dihitung dari tanggal setup:
nebak dari kalender bakal salah tiap kali user skip dosis, dan angka stok yang
bohong lebih bahaya daripada angka yang ketinggalan. Kalau user belum absen
hari ini, Kalem yang nanya duluan.

**Yang sengaja nggak ada: rekomendasi dosis.** Angka yang diisi user itu yang
sudah ditentukan dokternya. FocusBuddy nggak pernah nyaranin atau ngitungin
"dosis wajar" -- di luar kapasitas app, dan berisiko buat obat psikotropika
terkontrol seperti metilfenidat.

**Privasi:** data obat local-only, dan notifikasi pengingat ditulis netral
("Waktunya check-in ya") -- nama obat nggak muncul di banner, biar aman kalau
HP kepegang orang lain.

> Push notification beneran (Firebase dkk) belum dibangun -- untuk sekarang
> pengingatnya muncul saat app dibuka. Itu rencana produksi, bukan bagian demo.

## Limitasi yang Wajib Didisclose

- **Pecah Tugas bergantung API Gemini pihak ketiga.** Ada fallback rule-based,
  tapi ini bukan solusi 100% mandiri.
- **Energy Predictor dilatih dari data SINTETIS** (`generate_synthetic_data`),
  karena app belum punya histori pengguna riil.
- **Mood model** belajar dari data user asli, tapi butuh waktu -- di bawah 5
  catatan dia sengaja nggak ngeklaim pola apa pun.
- **Deteksi distress rule-based, bukan diagnosis.** Cuma trigger rujukan.
- **Medication Companion bukan alat diagnosis / pengganti dokter**, dan nggak
  pernah nyaranin dosis. Pencarian apotek diserahin ke Google Maps -- app ini
  sengaja nggak bikin data "stok apotek real-time" sendiri yang isinya karangan.
- **Stok obat cuma seakurat absen user.** Kalau user nggak pernah mencet "udah
  minum", angkanya nggak gerak (dan Kalem bakal nanya terus).
- FocusBuddy **bukan layanan krisis** dan nggak menggantikan diagnosis ADHD formal.

## Data

Semua data (profil, tugas, mood, diary, favorit, obat) disimpan **lokal** di
`~/.focusbuddy/data.json` (schema v3, migrasi otomatis dari v1/v2).
Nggak ada server eksternal di build ini.

### Auto Feel — data demo instan

Model mood/energi baru kelihatan pinter kalau udah ada histori. Daripada
check-in manual 14x sambil mencet "Maju 1 hari", pakai **`SettingDemo.py`**
di folder utama: isi skenario di situ, lalu pilih lewat ikon tongkat sihir
di Beranda (atau `python SettingDemo.py <skenario>` dari terminal).

Skenario bawaan: `baru` (0 histori), `stabil` (14 catatan), `burnout`
(SOS berulang + stok obat menipis), `premium` (30 catatan + SUBS ON).
Tambah sendiri sesuka kamu -- file itu isinya data doang, nggak ada logika.

Tombol **SUBS** (ikon medali) nyalain/matiin status premium seketika buat
nunjukin gating ke juri tanpa flow pembayaran.

Morning Brief paling gampang dites lewat tombol **"Maju 1 hari"** -- tiap
ganti hari dia muncul lagi otomatis.

Buat testing ada 4 tombol di pojok kanan atas Home -- **reset data**,
**maju 1 hari** (nggeser semua fitur yang bergantung tanggal lewat
`app/clock.py`), **SUBS on/off**, dan **Auto Feel**. Hapus blok `_dev_buttons` di
`app/views/home.py` kalau app udah mau dipakai beneran.

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


## Data obat (BPOM)

Validasi nama obat jalan **offline** dari registri resmi BPOM, bukan dari AI.

```
APP - Master Produk Komoditi Obat-<tanggal>.csv   # sumber, 23.437 baris, 4,8 MB
        |
        |  python tools/build_bpom_index.py
        v
app/data/bpom_index.json                          # 8.960 nama unik, 1,66 MB
```

Yang dipakai app: nama resmi, **NIE** (nomor izin edar), golongan, komposisi,
bentuk sediaan, masa berlaku. Huruf ke-2 NIE nentuin golongan -- `B`ebas,
bebas `T`erbatas, `K`eras, `P`sikotropika, `N`arkotika -- jadi app bisa bilang
"ini wajib resep dokter" sebagai fakta registri, bukan tebakan.

Bikin ulang indeksnya cuma perlu kalau CSV-nya di-update:

```bash
python tools/build_bpom_index.py
```

**Yang nggak ada di dataset ini:** jamu, herbal, dan suplemen didaftarin BPOM
di daftar terpisah (nomor TR/SD/POM). Jadi "Tolak Angin" bakal balik "nggak
ketemu" -- itu bener, bukan bug.

## Dataset prediksi durasi (opsional)

`duration_predictor.py` sekarang jalan pakai data sintetis. Buat pakai data
asli, taruh CSV di `app/data/durasi_tugas.csv`:

```csv
kategori,jumlah_unit,satuan,energi_saat_itu,durasi_menit
soal,10,soal,3,35
nulis,500,kata,4,45
baca,20,halaman,2,40
```

Kategori yang dikenal ada di `duration_predictor.CATEGORIES`. Minimal 20 baris
sebelum dipakai -- di bawah itu Random Forest cuma bakal ngapalin, jadi
otomatis balik ke kurva sintetis.

## Model Kalem (`app/kalem_ml/`)

Satu file per model, satu lapisan fitur bersama.

| File | Belajar apa | Sumber | Ambang mulai belajar |
|---|---|---|---|
| `fitur.py` | — (lapisan fitur, ~40 sinyal) | storage | — |
| `riwayat.py` | — (rekonstruksi fitur per hari lampau) | storage | — |
| `model_durasi.py` | Judul tugas → rentang menit | `DATASET/task_duration_dataset_id_lengkap.csv` (499) + sesi user | 2 sesi/kategori |
| `model_mood.py` | Ramalan skor mood harian | catatan user | 5 catatan (pola), 10 (model) |
| `model_energi.py` | Beban kerja + burnout | 500 baris sintetis + kalibrasi user | jalan dari hari-1 |
| `model_overwhelm.py` | Risiko hari berat | hari user mencet SOS | 10 hari ber-label |
| `model_penenang.py` | Opsi jeda yang beneran nolong | perubahan mood sesudah pakai | 4x pemakaian |

**Empat aturan yang dipegang semua model:**

1. **Jujur soal tahap.** Di bawah ambang, model ngaku "belum kebaca" atau
   pakai prior yang ditandai jelas. Nggak ada yang ngarang pola dari 3 hari.
2. **Prior dicampur, bukan diganti.** Bobot model naik pelan seiring data
   numpuk (`w = n / (n + 20)`), biar tebakannya nggak ayun-ayunan.
3. **Koreksi cuma nurunin target.** Salah nyaranin terlalu ringan ruginya
   kecil; salah nyaranin terlalu berat bikin hari gagal.
4. **Angka mentah nggak dipajang.** Skor risiko & probabilitas dipakai buat
   ngatur nada, bukan ditunjukin sebagai nilai rapor.

### Melatih ulang

```bash
python tools/build_bpom_index.py      # indeks obat dari DATASET/
python tools/latih_model_durasi.py    # model durasi -> app/data/*.joblib
```

Dua-duanya opsional: app tetap jalan tanpa artefaknya (model durasi dilatih
sendiri saat pertama dipakai, ~1,6 detik).

### Hubungan energi-kecepatan: dipelajari, bukan dikarang

Dataset durasi SENGAJA nggak punya kolom `energi_saat_itu`, dan itu keputusan
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

Diukur 5-fold CV di 499 baris:

```
baseline (selalu tebak median 30 mnt)   MAE_log 0.952
TFIDF huruf + RandomForest, 300 fitur   MAE_log 0.755   <- dipakai
```

Galat khasnya **faktor ~2x**. Makanya yang ditampilin RENTANG, bukan satu
angka — dan pita 25–75% itu terkalibrasi (50% data asli jatuh di dalamnya).
