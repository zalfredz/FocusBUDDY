# Phase 6 Results — Global Model + User Personalization Architecture

## Result

Phase 6 membangun architecture dan mechanical contracts. Tidak ada model baru
yang dilatih untuk artifact, dipromosikan, atau dideploy. Real-user retraining
dan production personalization tetap **NOT READY** karena eligible real-user
outcome masih 0.

## Implemented architecture

```text
Supabase Auth UUID + state
  |                             OFFLINE ONLY
  +-> focus-outcome-v1 --------> validation -> dataset snapshot
  |                              -> train/evaluate -> registry candidate
  |
  +-> duration personalization state --+
                                        |
task -> Prediction interface -> Global Model + calibration -> prediction
```

Core App hanya mengenal `DurationPredictionService`. Training, CV, dataset
builder, experiment, dan fixture tetap di `ml/` dan tidak diimpor production.
Render dikenali sebagai inference-only dan tidak dapat mengeksekusi legacy fit.

## Global Model boundary

Ada satu slot `duration` pada production manifest. Resolver hanya menerima
artifact berstatus `promoted`, version lengkap, path environment, dan SHA-256
cocok. Saat ini statusnya `experimental`, sehingga tidak ada promosi terselubung.
Fallback statis mempertahankan kemampuan estimasi tanpa runtime training.

## Personalization boundary

- State kecil per Supabase Auth UUID; bukan full model per user.
- Version: `duration-personalization-v1`.
- Gate Phase 4: 30 eligible outcomes, 14 hari aktif, dan 3 kategori; jumlah
  outcome configurable untuk dinaikkan.
- Formula mekanis: bounded median ratio `actual/global_prediction`, 0,5×–2,0×.
- Di bawah threshold, user baru, mismatched UUID, invalid version, atau test-only
  state: Global Model only.
- Offline builder menolak other-user, current-task, future, incomplete, unknown,
  suspicious, invalid, dan synthetic data production.
- State tidak berubah ketika Global Model v1 diganti v2.

Gate ini adalah safety guard provisional, bukan angka yang sudah terbukti
optimal. Evaluasinya menunggu data nyata dan harus membandingkan error global
dengan global+personal untuk holdout temporal user yang sama.

## Setting Demo provenance

Mode yang menampilkan alat demo tidak otomatis membuat aktivitas orang asli
synthetic. Task normal memakai `real_user`; skenario developer memakai
`synthetic_scenario`; fixture memakai `synthetic_fixture`. Legacy record tanpa
provenance eksplisit tidak diasumsikan real. Fixture hanya menguji mechanics dan
tidak bisa mengaktifkan state production.

## Verified data flow

```text
Google Auth UUID
 -> create task
 -> Global/personal prediction + version snapshot
 -> Focus lifecycle
 -> focus-outcome-v1
 -> storage.save_state()
 -> existing Supabase enqueue/upsert
 -> restricted export
 -> validation + multi-session aggregation
 -> readiness / future training candidate
```

Target tetap `actual_active_duration_minutes`; multiple Focus sessions untuk
task occurrence yang sama dijumlahkan. Nama, email, phone, Google profile, dan
payment data tidak ditambahkan ke outcome schema atau aggregate report.

## Registry

Lifecycle yang diformalkan: `experimental`, `candidate`, `promoted`, `retired`.
Metadata artifact eksperimen lama diberi SHA-256. Persistence baru menolak
overwrite model version yang sudah ada. Production manifest tetap tidak promoted.

## Runtime fit audit

Tujuh legacy runtime paths masih ada dalam source untuk local regression
compatibility: Duration, Energy, dua Mood, Overwhelm, ML_KALEM, dan TF-IDF
retrieval. Semua diblokir atau diganti stateless transform ketika mode
production. Offline `.fit()` hanya ada pada `ml/training`; tool Duration lama
tetap explicit CLI dan dicatat sebagai legacy. Detail ada di
`RUNTIME_TRAINING_LOCATIONS.md`.

## Production behavior

UI/task/focus/cloud behavior tidak diubah. Boundary inference berubah secara
sengaja: production tidak lagi boleh melatih model dari request, dan
personalization hanya aktif dari state versioned yang lolos aturan. Karena state
real belum ada, semua user saat ini berada pada cold start/global-only.

## Main files

- Runtime: `app/runtime_policy.py`, `app/data_provenance.py`, `app/storage.py`
- Inference: `models/prediction_interface.py`, `models/personalization.py`,
  `models/model_registry.py`, `models/approved_models.json`
- Offline: `ml/personalization/duration.py`, dataset/evaluation/registry modules
- Integration: `app/views/tracker.py`, `app/focus_session.py`, demo scenarios
- Tests: `tests/test_ml_phase3.py` through `tests/test_ml_phase6.py`
- Docs: `ML_ARCHITECTURE.md`, `ML_USER_OUTCOME_DATA_SCHEMA.md`,
  `ML_OUTCOME_DATA_FLOW.md`, `RUNTIME_TRAINING_LOCATIONS.md`

## Remaining risks

- No real eligible outcomes, so neither personalization quality nor a new Global
  Model can be evaluated.
- Legacy local runtime fits remain technical debt, though production guards are
  active.
- No controlled Supabase backfill job exists yet for personalization state;
  Phase 6 deliberately does not invent credentials or automation.
- Timer quality remains pause-aware without browser visibility signal.
- TF-IDF vs stateless production retrieval needs a parity benchmark.

## Verification

- Seluruh 19 file `tests/test_*.py` lulus melalui interpreter project.
- ML Foundation/Phase 1: 11; Phase 2: 6; Phase 3: 11; Phase 4: 10;
  Phase 5: 5; Phase 6: 11.
- Cloud/Auth: 18 unit tests lulus sebagai bagian full suite.
- Compile check untuk `app`, `models`, `ml`, `tests`, dan `tools` lulus.
- `git diff --check` lulus.

Environment tidak menyediakan package `pytest`, sehingga suite dijalankan lewat
entrypoint mandiri yang memang disediakan setiap file test. Tidak ada dependency
baru yang diunduh untuk Phase 6.

## Recommended next phase

Collect real outcomes, export them privately, rerun Phase 4/5 readiness, then
evaluate the proposed personalization threshold and factor bounds temporally.
Only after gates pass should a candidate Global Model or real personalization
state be created. Promotion/deployment must remain a separate manual decision.
