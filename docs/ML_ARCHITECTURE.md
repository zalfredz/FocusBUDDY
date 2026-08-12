# FocusBuddy Production ML Architecture

## Current separation

```text
app/                     Flet UI, Focus lifecycle, storage/Supabase runtime
models/                  production inference, registry resolver, calibration
ml/datasets/             offline builders and immutable dataset metadata
ml/training/             guarded offline fit code
ml/evaluation/           quality, leakage, readiness, and promotion gates
ml/experiments/          explicit experiment entrypoints
ml/registry/             experimental metadata/index; binaries ignored by Git
ml/personalization/      offline user-state builder
reports/                 aggregate, PII-safe experiment/audit reports
docs/                    contracts, results, and migration guidance
```

## Global Model + user personalization

```text
PRODUCTION

task input
   |
   v
promoted Global Duration Model -------- global_model_version
   |
   v
global prediction
   |
   +---- no eligible personal state ---> final global prediction
   |
   +---- eligible state for Auth UUID --> bounded calibration
                                            |
                                            v
                                  personalized prediction

OFFLINE

Supabase focusbuddy_states
   -> restricted export
   -> outcome validation + task-occurrence aggregation
   -> versioned dataset snapshot
   -> leakage-safe split/CV/locked test
   -> experimental/candidate artifact
   -> manual promotion gate
   -> promoted Global Duration Model vN+1
```

Global Model adalah satu artifact population-level. Personalization bukan model
ML penuh per user; ia adalah state calibration kecil, versioned, bounded, dan
terikat ke satu Supabase Auth UUID. Mengganti Global Model v1 dengan v2 tidak
menghapus state personalisasi karena keduanya disimpan dan diberi versi secara
terpisah.

## Dependency boundary

```text
app -> models.prediction_interface
        -> models.model_registry -> promoted artifact
        -> models.personalization -> precomputed user state

ml.experiments -> ml.training + ml.evaluation + ml.datasets
ml.personalization -> offline personalization-state builder
```

Production `app/` dan `models/` tidak mengimpor `ml/`. App startup tidak
menjalankan experiment, CV, dataset construction, atau training. Pipeline
training memakai `offline_training_session()` dan dipanggil eksplisit dari CLI.

## Global Model and registry

Registry memiliki lifecycle `experimental`, `candidate`, `promoted`, dan
`retired`. Metadata menyimpan model/dataset version, dataset checksum, feature
configuration, seed, training configuration, metrics, creation time, artifact
path, dan artifact SHA-256. Versi yang sudah ada tidak boleh ditimpa.

- `ml/registry/`: metadata kandidat eksperimen. `production` masih `null`.
- `models/approved_models.json`: manifest production-facing; status Duration
  masih `experimental`.
- `models/model_registry.py`: hanya me-resolve status `promoted`, path dari
  environment, dan checksum yang cocok.
- Artifact binary diabaikan Git dan kelak dapat dipindah ke private object/model
  storage tanpa mengubah inference interface.
- Manifest juga mengunci `artifact_format`. Kandidat Phase 0–2 tetap
  experimental dan tidak otomatis kompatibel dengan loader runtime; promosi
  kelak memerlukan packaging ke format runtime yang ditinjau, tanpa training di
  proses aplikasi.

Belum ada Global Model production-ready. Phase 6 tidak mempromosikan model.

## Personalization and cold start

Runtime membaca `state.ml_personalization.duration` dari row Supabase user yang
sedang login. State wajib cocok dengan `current_user_id`; mismatch langsung
menjadi cold start. Tidak ada cache personal global yang mutable.

Threshold yang dipertahankan dari policy Phase 4 adalah minimal **30 eligible
completed task outcomes, 14 hari aktif, dan 3 kategori**. Jumlah outcome
dikonfigurasi melalui `FOCUSBUDDY_PERSONALIZATION_MIN_OUTCOMES`. Angka-angka ini
adalah proposed readiness gate terdokumentasi, bukan hasil optimasi atau klaim
akurasi. Environment boleh menaikkan jumlah outcome tetapi tidak menurunkannya.
Setelah data nyata tersedia, seluruh threshold
harus dievaluasi memakai holdout temporal per user, stabilitas faktor, coverage,
dan error global-vs-personalized.

- Di bawah salah satu threshold / state hilang / versi salah: Global Model saja.
- Di atas threshold: `global_prediction × median(actual/global_prediction)`;
  denominator memakai snapshot global, bukan prediksi final yang sudah personal.
- Factor dibatasi 0,5×–2,0×.
- Hanya outcome valid, task selesai, training-eligible, milik user yang sama,
  dan berakhir sebelum cutoff prediksi yang boleh masuk.
- Current task dan future outcome dikeluarkan eksplisit.
- Fixture synthetic hanya dapat membangun `test_only` state; runtime normal
  menolaknya.

Saat ini real-user eligible rows = 0. Jadi personalisasi production tetap
inactive dan tidak ada klaim real learning.

## Prediction provenance

Task dan `focus-outcome-v1` mempertahankan:

- final `predicted_duration_minutes` dan `prediction_source`;
- `global_prediction_minutes`;
- `global_model_version`, global dataset version, artifact SHA-256;
- `personalization_version` dan personalization dataset version;
- snapshot importance/deadline serta timestamp prediksi.

Outcome baru hanya dapat memengaruhi state yang dibuat untuk prediksi masa
depan, bukan prediksi task yang menghasilkan outcome tersebut.

## Production runtime policy

Render atau `FOCUSBUDDY_RUNTIME_MODE=production` bersifat inference-only.
Duration memuat artifact promoted yang checksum-valid; bila belum ada, fallback
statis dipakai. Semua legacy supervised `.fit()` berhenti sebelum fitting.
Personalization hanya menerapkan angka yang sudah dihitung; ia tidak memanggil
`.fit()` dan tidak memperbarui state saat request.

## How to train and promote a future Global Model

1. Export `{user_id, state}` dari Supabase ke lokasi private yang di-ignore Git.
2. Jalankan audit `ml.evaluation.real_user_data_audit`; jangan lanjut jika gate
   Phase 4/5 gagal.
3. Buat immutable dataset snapshot dengan version dan SHA-256.
4. Jalankan experiment secara eksplisit dalam offline training session.
5. Pilih kandidat lewat CV training split; buka locked test sekali setelah
   selection.
6. Tinjau MAE, RMSE, R2, long-task slice, leakage, dan reproducibility.
7. Bila promotion gate lolos, buat model version baru dan ubah status secara
   manual menjadi `promoted`; jangan overwrite version lama.
8. Sediakan artifact secara privat, set path environment, verifikasi checksum,
   lalu lakukan deployment terpisah. Phase 6 berhenti sebelum langkah ini.

## Migration path

Saat ini developer laptop adalah offline training environment. Kelak export,
training, evaluation, dan registry storage dapat diotomasi, tetapi promotion
tetap gated. Tidak diperlukan TensorFlow, TFLite, Kubernetes, feature store,
streaming bus, microservice, atau database ML baru untuk boundary ini.
