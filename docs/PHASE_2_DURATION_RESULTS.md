# Phase 2 — Duration Feature Engineering + Error Analysis

## Kesimpulan

Phase 2 **tidak menghasilkan improvement yang cukup besar untuk menggantikan
baseline Phase 1**. Beberapa fitur dapat diekstrak secara reproducible, tetapi
pada primary raw target tidak ada feature set yang melewati aturan meaningful
improvement yang dipraregistrasi: CV RMSE harus membaik minimal 2% dan menang pada
minimal 4 dari 5 fold.

Kandidat engineered raw terbaik adalah `action_type + HistGradientBoosting`. Ia
menang pada 5/5 fold, tetapi mean CV RMSE hanya membaik 1,24%. Locked test juga
hanya membaik kecil: MAE 0,59 menit, RMSE 0,75 menit, dan R² 0,008. Karena itu
artifact `duration-features-v3` secara sengaja mempertahankan konfigurasi Phase 1.

Status artifact tetap `experimental`; tidak ada production runtime, `app/`,
`models/`, KALEM, Flet, Supabase, Render, API, TensorFlow, atau TFLite yang diubah.

## Dataset dan evaluasi

- Source: `datasets/task_duration_id_clean.csv`, 549 baris.
- Source SHA-256:
  `3a730c016f68236b640e05a16f4a2b7bc1ad304b594ffb6fdf65af64b96939fb`.
- Derived dataset: `datasets/generated/task_duration_features_v3.csv`.
- Derived SHA-256:
  `f318d96e0096318f0a1db5f3817844dd91907802a1c2e651700c3260b0cfc238`.
- Split sama seperti Phase 1: 438 train / 111 locked test.
- Source group: 433 train / 109 test / **0 overlap**.
- CV: 5-fold group-aware pada training set saja, seed 42.
- Raw duration dipraregistrasi sebagai primary target; log1p hanya secondary.
- Setiap extractor hanya menerima teks task. Target, outcome, completion status,
  post-task information, dan future information tidak tersedia bagi extractor.

## Kualitas feature extraction

Audit manual bersifat targeted: mencakup contoh positif, negatif, ambigu, angka
indeks (`project 1`, `bab 4`), tahun, dan jam kalender. Accuracy di bawah adalah
akurasi terhadap assertion yang benar-benar direview, bukan klaim accuracy untuk
seluruh bahasa Indonesia.

| Feature | Coverage | Missing | Manual audit | Error | Gate |
|---|---:|---:|---:|---:|---|
| `n_token` | 100,00% | 0,00% | Deterministik | 0 | Lolos |
| `quantity` | 3,83% | 96,17% | 34/34 | 0 | Lolos |
| `unit_type` | 21,68% | 78,32% | 27/27 | 0 | Lolos |
| `action_type` | 90,71% | 9,29% | 30/30 | 0 | Lolos |
| `complexity_indicator` | 18,94% | 81,06% | 14/14 | 0 | Lolos |
| scope indicators | 2,19% | 97,81% | 11/11 | 0 | Lolos |
| `task_category` | 63,57% | 36,43% | 23/28 (82,14%) | 5 | **Gagal** |

`task_category` gagal ambang 85% sehingga Experiment F dilewati dan category
tidak masuk Experiment H. Lima error audit-nya terdapat pada:

- latihan soal array untuk interview coding;
- masak dua porsi makan malam;
- jalan kaki 10.000 langkah;
- beli deterjen;
- tulis abstrak paper.

Error ini menunjukkan taxonomy category mudah ambigu walaupun rule-nya
reproducible. Category tetap ditampilkan sebagai diagnostic grouping dengan
peringatan, bukan sebagai fitur model.

### Aturan ekstraksi

- `quantity`: angka atau number-word harus berada tepat sebelum controlled unit.
  `20 soal`, `satu bab`, `30 menit`, dan `120 kata` diterima. `nomor 2`,
  `project 1`, `bab 4`, `kuliah 12`, tahun 2021, dan `jam 5 sore` ditolak.
- `unit_type`: vocabulary terbatas pada soal, halaman, bab, file, dokumen, email,
  slide, video, orang, item, menit, dan jam.
- `action_type`: 17 kelas seperti membaca, menulis, belajar, membersihkan,
  membuat, mengedit, mengorganisir, mengerjakan, transaksi, dan olahraga.
- `complexity`: multi-hot linguistic signals `analysis`, `research`, `revision`,
  `long_form`, `completion`, dan `learning`; tidak ada skor intuisi.
- `scope`: exact-token flags untuk seluruh/semua/keseluruhan, beberapa,
  setiap/tiap, dan lengkap.
- `n_token`: jumlah Unicode word tokens; tanda baca bukan token.

False positive dan false negative pada targeted audit adalah 0 untuk feature yang
lolos. Low coverage tetap dilaporkan apa adanya dan tidak dianggap bukti utility.
Rincian assertion, examples, unique values, dan distributions tersedia dalam
report JSON.

## Ablation results

Seluruh angka test di bawah baru dihitung setelah pilihan model setiap konfigurasi
dibekukan dari CV. Experiment yang memburuk tetap ditampilkan.

| Experiment | Target | Best model | CV RMSE | Test MAE | Test RMSE | Test R² | Median AE | ±30% |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Phase 1 reference | raw | HistGradientBoosting | 117,10 | 72,49 | 131,57 | 0,298 | 41,23 | 18,92% |
| A — Phase 1 reproduced | raw | HistGradientBoosting | 117,10 | 72,49 | 131,57 | 0,298 | 41,23 | 18,92% |
| B — `n_token` | raw | HistGradientBoosting | 117,62 | 71,33 | 130,36 | 0,311 | 40,31 | 21,62% |
| C — quantity | raw | HistGradientBoosting | 117,10 | 72,49 | 131,57 | 0,298 | 41,23 | 18,92% |
| D — quantity + unit | raw | HistGradientBoosting | 117,63 | 70,97 | 129,96 | 0,315 | 39,47 | 20,72% |
| E — action | raw | HistGradientBoosting | **115,64** | 71,90 | 130,81 | 0,306 | 41,74 | 21,62% |
| G — complexity + scope | raw | HistGradientBoosting | 116,08 | 71,48 | 129,10 | 0,324 | 42,62 | 18,02% |
| H — all reliable | raw | HistGradientBoosting | 115,78 | 69,15 | 125,90 | 0,357 | 42,71 | 20,72% |
| A — Phase 1 reproduced | log1p | HistGradientBoosting | 120,78 | 59,67 | 131,68 | 0,297 | 29,04 | 22,52% |
| B — `n_token` | log1p | Extra Trees | 122,70 | 56,28 | 121,16 | 0,405 | 23,91 | 23,42% |
| C — quantity | log1p | HistGradientBoosting | 120,78 | 59,67 | 131,68 | 0,297 | 29,04 | 22,52% |
| D — quantity + unit | log1p | Extra Trees | 121,26 | 62,00 | 122,15 | 0,395 | 28,11 | 25,23% |
| E — action | log1p | HistGradientBoosting | **117,35** | 57,36 | 129,36 | 0,321 | 24,04 | 24,32% |
| G — complexity + scope | log1p | Random Forest | 118,58 | 54,91 | 122,26 | 0,394 | 19,63 | 28,83% |
| H — all reliable | log1p | Random Forest | 117,81 | 53,66 | 117,97 | 0,436 | 20,02 | 29,73% |

### Validation interpretation

Untuk primary raw target:

- `action_type` adalah feature tunggal terbaik: CV RMSE membaik 1,24% dan menang
  5/5 fold, tetapi gagal ambang meaningful 2%.
- All-reliable membaik 1,12% dan menang 4/5 fold, juga belum cukup.
- Complexity/scope membaik 0,87% dan menang 4/5 fold.
- Quantity sendirian tidak mengubah pemenang sama sekali karena hanya tersedia
  pada 3,83% data.
- `n_token` dan quantity+unit justru memperburuk mean CV RMSE.

Pada secondary log1p target, action membaik 2,84% dan menang 5/5 fold. All-reliable
membaik 2,46% tetapi hanya menang 2/5 fold, sehingga tidak stabil. Temuan log1p
ini layak dicatat untuk eksperimen berikutnya, tetapi tidak mengubah target primary
atau artifact setelah melihat locked test.

## Phase 1 versus engineered candidate

Best engineered raw candidate adalah Experiment E (`action_type`). Dibanding
Phase 1 pada locked test:

- MAE: 72,49 → 71,90 menit (membaik 0,59).
- RMSE: 131,57 → 130,81 menit (membaik 0,75).
- R²: 0,298 → 0,306 (naik 0,008).
- Median AE: 41,23 → 41,74 menit (**memburuk 0,51**).
- ±30%: 18,92% → 21,62% (naik 2,70 percentage points).

Perubahan ini terlalu kecil dan mixed untuk menyatakan Phase 2 sukses. Test result
ini diagnostic only dan tidak dipakai dalam selection.

## Error analysis — best engineered raw candidate

Error analysis memakai Experiment E, bukan artifact baseline, agar efek feature
baru benar-benar diperiksa. Overall: MAE 71,90, RMSE 130,81, Median AE 41,74,
median signed error +23,01 menit, sehingga kasus tengah cenderung over-predicted.

### Error by duration bucket

| Human-estimated target bucket | N | MAE | RMSE | Mean signed error |
|---|---:|---:|---:|---:|
| 0–15 | 37 | 57,55 | 82,99 | +52,81 |
| 16–30 | 22 | 43,76 | 52,58 | +37,94 |
| 31–60 | 16 | 76,94 | 123,65 | +62,16 |
| 61–120 | 19 | 52,10 | 66,26 | +1,24 |
| 121–300 | 10 | 80,88 | 105,10 | −44,68 |
| >300 | 7 | **265,59** | **404,49** | **−257,49** |

Model over-predict tugas pendek dan sangat under-predict tugas panjang. Short
tasks ≤30 menit mempunyai MAE 52,41; long tasks >300 menit mempunyai MAE 265,59.

Quantity tersedia pada hanya 6 locked-test rows: MAE 41,74 versus 73,63 ketika
quantity tidak tersedia. Sampelnya terlalu kecil untuk klaim general. Deadline
tersedia mempunyai MAE 73,59 versus 66,10 tanpa deadline. Berdasarkan importance,
kelompok importance 1 dan 10 paling sulit (MAE masing-masing 119,32 dan 118,58),
tetapi distribusi durasi di tiap kelompok juga berbeda.

Category diagnostic menunjukkan MAE terendah pada rumah (28,62) dan olahraga
(26,56, hanya 3 rows); tertinggi pada pekerjaan (101,59), `lainnya` (92,20), dan
akademik (89,16). Category gagal reliability gate, jadi angka ini hanya petunjuk
untuk desain annotation rubric, bukan perbandingan kategori yang kuat.

### Top 20 absolute errors

| # | Task | Human estimate | Predicted | Signed error | Absolute error |
|---:|---|---:|---:|---:|---:|
| 1 | selesaikan baca buku fiksi ilmiah yang sudah dibeli | 1200 | 226,17 | −973,83 | 973,83 |
| 2 | bentuk kelompok belajar kalkulus | 60 | 431,70 | +371,70 | 371,70 |
| 3 | kumpulkan draf project 2 | 480 | 160,24 | −319,76 | 319,76 |
| 4 | kerjakan kuis space robotics | 15 | 292,16 | +277,16 | 277,16 |
| 5 | selesaikan team charter untuk laporan praktikum | 60 | 311,70 | +251,70 | 251,70 |
| 6 | bangun dan dokumentasikan pipeline machine learning untuk eksperimen skripsi | 600 | 357,24 | −242,76 | 242,76 |
| 7 | operasi hidung | 180 | 0,00 | −180,00 | 180,00 |
| 8 | belajar untuk ujian sejarah | 300 | 123,96 | −176,04 | 176,04 |
| 9 | atur jadwal waktu praktikum | 9 | 184,08 | +175,08 | 175,08 |
| 10 | unggah aplikasi grant sebelum portal tutup jam 5 sore | 180 | 13,24 | −166,76 | 166,76 |
| 11 | selesaikan modul pelatihan wajib | 120 | 279,58 | +159,58 | 159,58 |
| 12 | bangun model valuasi DCF di Excel | 360 | 200,48 | −159,52 | 159,52 |
| 13 | tulis di jurnal/diary | 15 | 171,41 | +156,41 | 156,41 |
| 14 | tutup rekening deposito | 15 | 153,90 | +138,90 | 138,90 |
| 15 | minta teman membayar kembali untuk trip ke Atlanta | 6 | 144,04 | +138,04 | 138,04 |
| 16 | bayar kembali tagihan listrik ke teman sekamar | 12 | 147,26 | +135,26 | 135,26 |
| 17 | beli hadiah ulang tahun untuk ayah | 60 | 185,65 | +125,65 | 125,65 |
| 18 | perbaiki dimensi gambar lander | 120 | 0,00 | −120,00 | 120,00 |
| 19 | minta surat rekomendasi dari dosen | 30 | 142,04 | +112,04 | 112,04 |
| 20 | cas HP beberapa jam | 4,8 | 113,47 | +108,67 | 108,67 |

## Grouped permutation importance

Importance dihitung setelah seluruh selection dibekukan, pada best engineered raw
candidate. Nilainya adalah mean kenaikan RMSE ketika satu feature group diacak 20
kali:

| Feature group | RMSE increase | Std. dev. |
|---|---:|---:|
| Task text | +25,45 menit | 4,68 |
| `action_type` | +8,62 menit | 2,47 |
| Deadline | +6,72 menit | 2,57 |
| Importance | +2,59 menit | 6,36 |

Model memang menggunakan `action_type`, tetapi ketergantungan ini tidak otomatis
berarti generalization gain-nya cukup besar. Quantity, unit, category, complexity,
scope, dan text length tidak termasuk candidate E; report menandainya
`included_in_model=false`, bukan memberi importance palsu. Tidak ada klaim
kausalitas.

## Jawaban Phase 2

1. **Fitur reliable:** n_token, quantity, unit, action, complexity flags, dan
   scope flags. Category belum reliable.
2. **Coverage:** 100%, 3,83%, 21,68%, 90,71%, 18,94%, dan 2,19% secara berurutan.
3. **Fitur yang memperbaiki validation:** action paling konsisten; complexity dan
   all-reliable memberi gain kecil. Pada secondary log1p, action memberi gain
   2,84% dan menang 5/5 fold.
4. **Fitur yang tidak membantu:** quantity sendirian tidak mengubah hasil;
   n_token serta quantity+unit memperburuk raw CV mean. Category gagal sebelum
   training.
5. **Kombinasi raw terbaik:** action_type saja, tetapi improvement belum meaningful.
6. **Locked-test improvement:** sangat kecil dan mixed; Phase 2 dinyatakan belum
   sukses.
7. **Task tersulit:** task >300 menit, pekerjaan, akademik, dan category tidak
   teridentifikasi; kategori terakhir hanya diagnostic.
8. **Largest errors:** label 1.200-menit membaca buku dan task panjang 360–600
   menit mendominasi under-prediction; beberapa task 6–60 menit justru diprediksi
   140–430 menit.
9. **Akar masalah:** kombinasi noisy human-estimated labels, target definition,
   insufficient data di tail, dan informasi workload eksplisit yang jarang.
   Model limitation bukan satu-satunya penyebab.
10. **Single highest-value next step:** kumpulkan actual FocusBuddy completion
    outcomes yang terhubung ke task identity, sambil menyimpan explicit quantity,
    unit, planned session, dan completion boundaries. Ini lebih bernilai daripada
    menambah rule-based feature yang semakin spekulatif.

## Artifact dan reproducibility

Artifact `duration-features-v3.joblib` sekitar 200 KB, cold-load sekitar 58 ms,
warm inference mean sekitar 9,6 ms, P50 sekitar 8,9 ms, dan P95 sekitar 15,2 ms pada
mesin eksperimen. Artifact mempertahankan baseline Phase 1 karena feature gain
tidak melewati acceptance gate dan tidak terhubung ke produksi.

Reproduce dari root repository:

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/python -m ml.experiments.duration_features_v3
```

Seluruh candidates, fold metrics, extraction errors, top-20 errors, group
aggregates, package versions, dan permutation results ada di
`reports/duration-features-v3.json`. Ringkasan tabular ada di
`reports/duration-features-v3.csv`.
