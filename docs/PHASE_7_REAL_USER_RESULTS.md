# Phase 7 — Real User Data Collection & Personalization Validation

## Final status

```text
REAL USER DATA STATUS: NOT READY
PERSONALIZATION STATUS: NOT READY — NEED MORE REAL USER DATA
GLOBAL RETRAINING STATUS: NOT READY
```

Repository ini tidak menerima restricted export Supabase berisi outcome nyata
pada Phase 7. Run reproducible yang disimpan memakai fixture sintetis hanya untuk
memvalidasi mekanisme pipeline. Karena itu:

- real users detected: 0;
- real sessions detected: 0;
- training-eligible task occurrences: 0;
- personalized users eligible: 0;
- tidak ada Global Model yang dilatih;
- `reports/personalization_evaluation.json` tidak dibuat.

Angka tersebut hanya menggambarkan input audit yang tercantum di report, bukan
hasil query atau perkiraan isi Supabase live.

## Outcome pipeline audit

Satu Focus session nyata menyimpan `focus-outcome-v1` dengan:

- session, task, step, dan recurring-occurrence identity;
- task text pada restricted state, tanpa nama, email, telepon, atau profil
  Google;
- final dan Global Duration prediction, source, model/dataset/artifact version,
  serta personalization version;
- importance, deadline snapshot, dan planned Focus duration;
- active duration, explicit pause duration, interruption count, completion,
  outcome, serta timestamps;
- runtime quality placeholders dan provenance.

`user_id` tidak disalin ke setiap outcome. Offline join mengambil Supabase Auth
UUID dari envelope `{user_id, state}`. UUID hanya menjadi batas identitas dan
split; ia tidak pernah menjadi feature model.

Validator Phase 7 sekarang juga mewajibkan `prediction_source`,
`planned_session_minutes`, `collection_context`, dan runtime data-quality fields.
Legacy record yang provenance-nya ambigu tidak dihitung sebagai real session.
Prediction provenance yang berubah di tengah beberapa session untuk task
occurrence yang sama membuat group ditolak.

## Setting Demo provenance

Setting Demo tetap merupakan pengalaman pengguna nyata:

```text
human creates normal task while Setting Demo is available
  -> data_provenance=real_user
  -> collection_context=setting_demo
  -> may become eligible after offline validation

developer scenario / generated fixture
  -> data_provenance=synthetic_scenario or synthetic_fixture
  -> always excluded from training and personalization
```

Context UI tidak dipakai untuk menebak provenance. Provenance melekat pada task
yang membuat session tersebut.

## Personalization evaluation

Evaluasi offline baru membandingkan prediksi Global dengan
`Global × personal calibration` secara terpisah untuk setiap Auth UUID.

Current runtime threshold tetap:

- 30 eligible completed task outcomes;
- 14 distinct active days;
- 3 task categories.

Untuk evaluasi Phase 7, diperlukan minimal lima outcome yang terjadi **setelah**
history mencapai threshold. Itu adalah guard evaluasi, bukan perubahan threshold
runtime. Calibration dihitung hanya dari record dengan `ended_at` sebelum cutoff
holdout. Current/future outcome dan data pengguna lain tidak dapat ikut menghitung
factor.

Report evaluasi hanya berisi subject anonim, jumlah baris, factor, dan metrics.
Raw UUID serta task text tidak ditulis. Artifact atau state personalisasi tidak
diaktifkan otomatis meskipun kelak evaluasi dapat dijalankan.

## Data-safety result

- Unfinished/crashed session tetap `unknown`, bukan durasi nol.
- Duplicate `record_id` atau `session_id` ditolak.
- Timestamp rusak, waktu selesai sebelum mulai, atau active time melebihi elapsed
  time ditolak.
- Task-level duration label hanya dibuat setelah task benar-benar selesai.
- Seluruh valid session untuk satu task occurrence dijumlahkan.
- Synthetic record tidak dapat menjadi training candidate.
- Aggregate report tidak memuat raw UUID, task text, nama, atau email.

## Running with a future restricted export

Simpan export di folder private/ignored, lalu jalankan dari root repository:

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/python \
  -m ml.experiments.phase7_real_user_validation \
  --input datasets/private/supabase-focusbuddy-states.json \
  --report-dir reports
```

Expected input adalah list row `{user_id, state}` atau object yang mempunyai
field `rows`. Command ini tidak melakukan `.fit()`, tidak memperbarui Supabase,
tidak mengaktifkan personalisasi, dan tidak mempromosikan model.

## Production impact

Core Focus flow, UI, Supabase Auth, cloud save, prediction interface, dan Render
inference tidak diubah. Phase 7 menambah validasi serta evaluasi offline dan
memperketat metadata yang memang sudah ditulis collector produksi.

## Generated output

- `reports/real_user_data_readiness.json`
- `reports/personalization_readiness.json`
- `reports/personalization_evaluation.json` hanya jika data temporal nyata cukup

Current reports menggunakan `synthetic_fixture_pipeline_validation` dan berhenti
sesuai stop condition.
