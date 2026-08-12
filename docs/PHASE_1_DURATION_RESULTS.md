# Phase 1 — Duration Clean v2 Results

## Status dan batas eksperimen

Phase 1 selesai sebagai eksperimen offline. Model dan artifact berstatus
`experimental`; tidak ada production inference, runtime training, UI, KALEM, API,
Supabase, Render, TensorFlow, atau TFLite yang diubah.

Target sumber `durasi_menit` dipetakan secara eksplisit ke nama internal
`estimated_duration_minutes`. Nilainya adalah **estimasi manusia**, bukan durasi
aktual hasil observasi.

## Dataset durasi bersih

- Sumber: `datasets/task_duration_id_clean.csv`
- Versi: `task-duration-id-clean-v2`
- SHA-256: `3a730c016f68236b640e05a16f4a2b7bc1ad304b594ffb6fdf65af64b96939fb`
- Baris: 549
- Kolom: 23
- Duplikat full-row: 0
- Duplikat judul ternormalisasi: 7 baris; ketujuh pasangan berada dalam
  `source_group_id` yang sama
- Duplikat pada kombinasi fitur-target model: 0
- `label_review_needed=1`: 2 baris
- Source group: 542; 7 grup punya 2 baris

Kolomnya adalah `row_id`, `task_en`, `tugas`, `tugas_raw`, `task_en_raw`,
`jatuh_tempo_hari`, `ada_tenggat`, `tenggat_hari`, `durasi_jam`, `durasi_menit`,
`tingkat_kepentingan_1_10`, `notes_en`, `catatan`, `quality_flag`,
`label_review_needed`, `source_group_id`, `data_source`, `source_dataset`,
`source_row_id`, `upstream_match`, `label_provenance`, `license`, dan `created_at`.

Missing values:

| Kolom | Missing | Keterangan |
|---|---:|---|
| `tenggat_hari` | 111 | Expected: seluruhnya `ada_tenggat=0` |
| `notes_en` | 495 | Metadata opsional |
| `catatan` | 495 | Metadata opsional |
| `quality_flag` | 495 | Kosong berarti tidak ada flag |
| `source_row_id` | 549 | Provenance belum diisi |
| Kolom lain | 0 | Lengkap |

Distribusi target sangat right-skewed:

| Statistik | Menit |
|---|---:|
| Minimum | 1.80 |
| P25 | 15.00 |
| Median | 39.00 |
| Mean | 100.19 |
| P75 | 120.00 |
| P95 | 420.00 |
| Maksimum | 1,500.00 |

Ada 41 estimasi di atas 300 menit dan 6 di atas 600 menit. Distribusi bucket:
156 `(0,15]`, 113 `(15,30]`, 83 `(30,60]`, 92 `(60,120]`, 64
`(120,300]`, 35 `(300,600]`, dan 6 `>600`.

Distribusi deadline: 438 baris punya deadline dan 111 tidak. Untuk baris yang
punya deadline, nilai yang paling sering adalah 3 hari (60), 0 hari (53), 2 hari
(50), 4 hari (45), 1 hari (32), dan 7 hari (32). Distribusi lengkap disimpan di
`reports/duration-clean-v2.json`.

Kolom `task_category`, `action_type`, `complexity_indicator`, dan `n_token` tidak
ada di file yang diberikan. Karena Phase 1 melarang fitur rekaan, distribusinya
ditandai `null` dan Experiment C structured dicatat sebagai **skipped**, bukan
dijalankan dengan proxy yang tidak sah.

## Encoding deadline

Eksperimen A mereproduksi representasi lama: `jatuh_tempo_hari` sebagai satu
angka, termasuk `-1` untuk tidak ada deadline. Nilai ini hanya dipakai sebagai
kontrol Phase 0.

Eksperimen B memakai dua fitur:

| Kondisi | `has_deadline` | `deadline_days_or_zero` |
|---|---:|---:|
| Tidak ada deadline | 0 | 0 |
| Deadline hari ini | 1 | 0 |
| Deadline N hari | 1 | N |

Dengan begitu, `-1` tidak pernah diperlakukan sebagai deadline numerik dan
deadline hari ini tetap dapat dibedakan dari tidak ada deadline. Perubahan ini
hanya berada di pipeline offline.

## Disiplin evaluasi dan leakage

- Holdout: `GroupShuffleSplit`, 80/20, seed 42.
- Hasil split: 438 training rows / 111 locked-test rows.
- Grup: 433 train / 109 test / **0 overlap**.
- CV: 5-fold `GroupKFold(shuffle=True, random_state=42)` hanya pada training set.
- TF-IDF dan preprocessing lain di-fit ulang hanya pada bagian train tiap fold.
- Semua konfigurasi, transformasi target, kandidat, dan aturan seleksi dikunci
  sebelum locked test dibuka.
- Model, fitur, dan target transform dipilih dengan mean CV RMSE, tidak dengan
  locked-test result.
- Jika CV RMSE seri persis, tie-break memilih representasi deadline bersih agar
  artifact tidak mempertahankan sentinel `-1`; tie-break ini tidak membaca test.

Tidak ada overlap judul Indonesia, judul Inggris, raw Indonesia, atau raw Inggris
antara train dan test. Semua 549 baris berlabel `data_source=original`; tidak ada
augmentation. `source_group_id` dipakai sebagai boundary untuk pasangan sumber
dan terjemahan. Repositori belum punya detektor semantic duplicate independen,
jadi semantic duplicate tidak diberi angka palsu.

## Hasil

Enam kandidat yang sama diuji pada setiap konfigurasi: Median, Decision Tree,
Random Forest, Extra Trees, Gradient Boosting, dan HistGradientBoosting.

Tabel berikut hanya menampilkan konfigurasi yang benar-benar dijalankan dan
pemenang modelnya berdasarkan CV. Locked test baru dihitung setelah seluruh
pemenang dibekukan.

| Experiment | Target | Model | CV RMSE | Test MAE | Test RMSE | Test R² | Median AE | ±30% |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Phase 0 historical | log1p | Gradient Boosting | 93.58 | 86.62 | 207.60 | 0.065 | 26.57 | 25.45% |
| Clean data + old features | raw | HistGradientBoosting | 117.10 | 72.49 | 131.57 | 0.298 | 41.23 | 18.92% |
| Clean data + old features | log1p | HistGradientBoosting | 120.78 | 59.67 | 131.68 | 0.297 | 29.04 | 22.52% |
| Clean deadline | raw | HistGradientBoosting | 117.10 | 72.49 | 131.57 | 0.298 | 41.23 | 18.92% |
| Clean deadline | log1p | HistGradientBoosting | 120.78 | 59.67 | 131.68 | 0.297 | 29.04 | 22.52% |

Phase 0 memakai dataset dan split row-random yang berbeda. Perubahan terhadap
Phase 0 karena itu deskriptif, bukan bukti kausal bahwa cleaning saja menghasilkan
gain. Dibanding angka historis, artifact Phase 1 terpilih menurunkan MAE 14.13
menit dan RMSE 76.04 menit serta menaikkan R² 0.233.

### Jawaban atas pertanyaan Phase 1

1. **Apakah clean dataset memperbaiki model?** Secara locked-test deskriptif,
   ya pada MAE, RMSE, dan R² dibanding Phase 0. Namun karena split berubah menjadi
   group-aware dan dataset berbeda, belum boleh disebut perbandingan apple-to-apple.
2. **Apakah structured features memperbaiki model?** Belum dapat diuji. Kolomnya
   tidak ada; Experiment C sengaja dilewati.
3. **Apakah corrected deadline memperbaiki model?** Tidak pada pemenang.
   Old-deadline dan clean-deadline menghasilkan metrik identik. Encoding bersih
   tetap lebih benar secara semantik dan mencegah `-1` disalahartikan.
4. **Apakah log1p memperbaiki model?** Mixed. Pada CV, log1p memperbaiki MAE,
   Median AE, dan tolerance rates, tetapi raw lebih baik pada primary selection
   metric RMSE dan pada R². Locked test memperlihatkan log1p MAE lebih rendah
   (59.67 vs 72.49) dan Median AE lebih rendah (29.04 vs 41.23), tetapi RMSE dan
   R² sedikit lebih buruk. Locked test tidak dipakai untuk membalikkan pilihan.
5. **Model existing terbaik?** HistGradientBoosting memenangkan CV pada keempat
   konfigurasi valid. Artifact final memakai `clean_deadline` + target raw; ia
   menang tie-break atas representasi lama dengan CV RMSE yang identik.
6. **Locked-test artifact terpilih?** MAE 72.49 menit, RMSE 131.57 menit,
   R² 0.298, Median AE 41.23 menit, ±10% 6.31%, ±20% 12.61%, dan ±30% 18.92%.
7. **Production-ready?** Tidak. Error absolut dan tolerance rate masih buruk,
   target hanyalah estimasi manusia, dan bukti eksternal/personal belum ada.
8. **Batas performa utama?** Hanya 549 baris, target sangat skewed dan noisy,
   enam label ekstrem di atas 600 menit, fitur task terstruktur belum tersedia,
   provenance `source_row_id` kosong, dan tidak ada actual-duration outcome.
9. **Data paling bernilai berikutnya?** Pasangan estimasi-versus-durasi aktual,
   task category/action type/complexity yang diberi label konsisten, jumlah unit,
   konteks pengguna yang aman, serta lebih banyak contoh untuk durasi panjang.
10. **Phase 2 berikutnya?** Pertahankan locked group test ini, review dua label
    yang ditandai dan tail `>300`, buat data dictionary serta annotation rubric
    untuk fitur structured, kumpulkan actual outcomes terpisah dari estimates,
    lalu pre-register eksperimen berikutnya. Jangan mengubah produksi sebelum
    kualitas locked test memenuhi acceptance criteria yang disepakati.

## Efisiensi artifact terpilih

- Ukuran artifact: sekitar 199 KB.
- Cold load median: sekitar 56 ms.
- Warm inference mean: sekitar 7 ms.
- P50 inference: sekitar 5 ms.
- P95 inference: sekitar 11 ms.

Angka latency bergantung pada mesin dan dapat sedikit berubah saat eksperimen
diulang. Artifact tetap eksperimental dan tidak di-load aplikasi produksi.

## Validasi decomposition v2

- SHA-256: `376896a72105b91528fb246b6c232880b7f31c341136516cb4f3e3fad8a0b0cc`
- Pola: 212; duplikat row 0; duplikat judul 0.
- Kategori: Akademik 39, Kerja 35, Rumah 27, Administrasi 27, Digital 24,
  Personal 23, Komunikasi 21, dan Perawatan diri 16.
- Semua pola punya tepat 5 langkah; missing/empty steps 0; mismatch jumlah 0.
- English contamination berdasarkan quality flag: 4 judul.
- Source group: 190; 20 grup multirow; maksimum 3 baris per grup.
- 179 baris tercatat berasal dari dataset terjemahan; 33 dari kurasi manual.
- Existing first-step manual rubric tetap valid untuk 50 pola: mean 2.0/2.0,
  seluruhnya skor 2, melewati target 1.8.
- Semantic duplicate count tidak tersedia karena tidak ada detector independen.

Retrieval tidak dilatih ulang. Benchmark retrieval produksi juga tidak dijalankan
karena tidak ditemukan test set Indonesia yang independen. File 448 query lama
berbahasa Inggris sengaja tidak dipakai, dan query generator dari judul produksi
tidak dipromosikan sebagai production metric.

## Reproduksi

Jalankan dari root repository dengan environment yang sudah memasang dependency
project:

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/python -m ml.experiments.duration_clean_v2
```

Konfigurasi lengkap, seluruh 24 candidate runs, distribusi deadline, fold audit,
package versions, timings, dan locked-test metrics disimpan di
`reports/duration-clean-v2.json`. Ringkasannya ada di
`reports/duration-clean-v2.csv`; metadata artifact ada di
`ml/registry/metadata/duration-clean-v2.json`.
