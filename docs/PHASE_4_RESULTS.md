# Phase 4 — Real User Data Audit & Retraining Pipeline Design

## Status

**REAL USER RETRAINING STATUS: NOT READY**

Repository tidak berisi export Supabase dengan outcome pengguna nyata yang dapat
diaudit. Satu-satunya input outcome yang tersedia adalah fixture dengan 1 user,
1 task, dan 2 session yang semuanya bertanda `synthetic=true`. Audit smoke test
menemukan 0 training-eligible task occurrence. Karena itu Phase 4 tidak
menjalankan training dan tidak menghasilkan klaim accuracy.

Laporan agregat fixture tersedia di
`reports/real_user_data_readiness.synthetic.json`. Ia adalah tes pipeline, bukan
ringkasan populasi pengguna.

## Audit Phase 3

Fondasi Phase 3 memenuhi boundary penting berikut:

- session `started`/`paused` tanpa end dan active duration diklasifikasikan
  `unknown`; ia tidak menjadi nol dan tidak masuk builder;
- setiap task occurrence baru menjadi candidate setelah ada outcome
  `completed`, `task_completed=true`, dan seluruh session history-nya valid;
- demo records invalid di validator dan synthetic groups ditolak builder;
- positive prediction serta `prediction_model_version` wajib tersedia;
- `invalid`, `unknown`, dan `suspicious` bukan `measurement_usable`;
- beberapa Focus session dijumlahkan menjadi satu target task occurrence;
- `source_session_ids`, task/session identity, prediction version, dan source
  user dipertahankan untuk provenance;
- `user_id` hanya dipakai join, grouping, split, dan audit. Ia tidak berada pada
  feature schema Duration dan tidak boleh diberikan ke preprocessor/model.

Phase 4 memperkuat versioning dataset. Snapshot outcome sekarang
content-addressed: canonical candidate content menghasilkan
`focusbuddy-user-outcomes-v1-sha256-<12 hex>`. Input yang sama menghasilkan
version, candidate UUID, dan checksum yang sama; perubahan outcome mengubah
version. Ini mencegah dua isi berbeda memakai label versi yang sama.

Tidak ditemukan bug Phase 3 yang memerlukan perubahan behavior produksi. Phase 4
hanya mengubah pipeline offline dan dokumentasi.

## Offline audit command

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/python \
  -m ml.evaluation.real_user_data_audit \
  --input path/ke/supabase-export.json \
  --output reports/real-user-readiness.json
```

Input adalah list `{user_id, state}` atau object dengan key `rows`, `records`,
atau `data`. `state` boleh object atau serialized JSON. Command menghasilkan:

- total user, task, dan Focus session;
- status valid/suspicious/invalid/unknown;
- completed dan training-eligible task occurrences;
- synthetic/demo counts dan alasan penolakan session/group;
- distribusi prediction model version;
- distribusi/percentile durasi task valid;
- jumlah observation per user tanpa menampilkan user-nya;
- jumlah user yang memenuhi gate personalization;
- content-addressed dataset version/checksum;
- keputusan readiness dan hasil setiap check.

Report tidak berisi raw task text, UID, nama, atau email. Source export dikenali
hanya dengan SHA-256. Command tidak mengimpor training module atau memanggil
`.fit()`.

## Proposed minimum-data gates

Semua threshold di bawah bersifat **proposed engineering gates**, tercatat dalam
`duration-real-user-readiness-v1`, dan harus direview setelah melihat collection
rate. Lolos gate hanya mengizinkan eksperimen offline, bukan deployment.

### A. Dataset-level offline experiment

- minimal 200 eligible completed task occurrences;
- minimal 20 eligible users;
- minimal 10 user masing-masing memiliki sedikitnya 5 outcome;
- maksimal 20% session suspicious/invalid/unknown;
- nol synthetic training row.

200 rows memberi screening holdout/CV awal tetapi belum otomatis cukup untuk
promotion. Dua puluh user menjaga beberapa group untuk holdout sekaligus 5-fold
CV; repeated-user gate mencegah satu pengguna mendominasi. Telemetry yang lebih
dari 20% unusable harus diperbaiki sebelum perbandingan model dipercaya.

### B. Per-user calibration experiment

- minimal 30 eligible outcomes untuk user tersebut;
- tersebar pada minimal 14 hari aktif;
- memiliki minimal 3 kategori task non-kosong.

Threshold ini mengurangi risiko calibration menghafal satu minggu atau satu jenis
tugas. Ia belum scientifically validated dan **tidak mengizinkan separate model
per user**.

### C. Global retraining candidate

- minimal 1.000 eligible task occurrences;
- minimal 50 eligible users;
- minimal 30 user memiliki sedikitnya 10 outcome;
- expected 20% locked test minimal 200 rows;
- minimal 50 task occurrences di slice >300 menit;
- seluruh dataset-level gate lulus.

Long-task gate wajib karena slice >300 menit adalah kegagalan terbesar Phase 2.
Actual group holdout tetap harus diperiksa; expected 200 tidak menjamin komposisi
test memadai.

## Leakage-safe evaluation

Primary evaluation adalah **80/20 user-group holdout, seed 42**. Seluruh row satu
user hanya boleh berada di train atau locked test. Ini mengukur generalisasi ke
pengguna baru dan mencegah kebiasaan personal yang sangat mirip bocor ke test.
Candidate selection dan 5-fold group CV hanya berjalan pada 80% training users.
Locked test tidak boleh dipakai untuk preprocessing, hyperparameter selection,
feature selection, atau model choice.

Secondary evaluation adalah temporal holdout: task families terbaru per user
menjadi test, dan history sebelumnya menjadi train. Seluruh occurrence dari satu
task family harus berada di sisi yang sama. Ini menjawab generalisasi ke task
masa depan milik user yang sudah dikenal, tetapi bukan pengganti primary split
karena user sengaja muncul pada kedua sisi.

`real_user_splits.py` mengaudit overlap `user_id`, `task_id`, `task_family_id`,
`record_id`, dan source session. Primary split menolak semuanya. Temporal split
memperbolehkan user overlap saja. Identifiers dipakai sebagai split metadata,
bukan fitur.

## Intended retraining architecture

```text
Supabase offline export
  -> PII-safe aggregate audit
  -> quality validation
  -> completed task-occurrence aggregation
  -> content-addressed dataset snapshot + manifest
  -> 80/20 user-group locked split
  -> preprocessing fit on training rows only
  -> 5-fold user-group CV on training users only
  -> candidate selection from CV
  -> one locked-test evaluation
  -> compare frozen baselines and important slices
  -> experimental registry entry
  -> manual promotion review
```

The forbidden path remains:

```text
Supabase -> runtime model.fit() -> model replacement
```

Registry audit shows `production: null`. `duration-features-v3` is the latest
experimental entry and intentionally retains the Phase 1 configuration after
Phase 2 failed its improvement gate. Runtime still uses the separate legacy
`models/artifacts/task_duration_model.joblib` path, with runtime-fit fallback.
A future real-user experiment must compare against both a frozen deployed legacy
behavior baseline and the registered Phase 1 experimental baseline on comparable
rows; it must not describe either as a promoted registry production model.

## Model promotion policy

`duration-promotion-v1` requires all of the following before a candidate is even
eligible for **manual** review:

- real-user dataset gate passed;
- mean CV RMSE improves by at least 2%;
- locked-test RMSE improves by at least 2%;
- locked-test MAE does not regress;
- no shared important slice RMSE regresses more than 10%;
- long-task slice is included;
- locked test remained untouched until selection;
- run is reproducible;
- dataset version and model version exist;
- feature schema is runtime-compatible;
- baseline uses a comparable split/dataset.

CV improvement alone is explicitly insufficient. Passing returns `ELIGIBLE FOR
MANUAL PROMOTION REVIEW`, never automatic promotion. Any failed check returns
`KEEP EXISTING MODEL`. These values are proposed policy boundaries and must be
recorded with every future decision.

## Personalization design—prepared, not implemented

```text
fewer than 30 valid outcomes
  -> global model prediction

30+ outcomes, 14+ active days, 3+ categories
  -> candidate for offline calibration experiment
  -> global prediction plus a small, bounded personal residual/ratio adjustment
  -> calibration version stored separately
```

The future calibration should use shrinkage toward 1.0, clipping, minimum sample
checks, and temporal evaluation. It must fall back to the global prediction when
uncertain. No per-user estimator, fine-tuning, or runtime `.fit()` is implemented
in Phase 4.

## Legacy runtime-training migration plan

Phase 4 found the same seven production-runtime fit paths documented earlier:

| Runtime location | Classification | Phase 5 action |
|---|---|---|
| Duration Random Forest | must remove | Load required versioned artifact; use static fallback on failure. |
| Energy Decision Tree | must remove | Freeze synthetic prior offline as artifact/rules. |
| personal Mood Random Forest | must remove | Global artifact plus non-training calibration. |
| Mood-page Decision Tree | must remove | Consolidate duplicate Mood contract. |
| Overwhelm Logistic Regression | must remove | Global offline classifier plus persisted calibration. |
| ML_KALEM Logistic Regression | must remove | Global offline model; outcomes exported for periodic training. |
| Pecah Tugas TF-IDF per-query fit | safe fallback temporarily | Prefit built-in corpus and fingerprint-cache user index. |

All `.fit()` calls under `ml/training/` are intentionally experimental and
protected by `offline_training_session()`. They are not production inference.
Detailed functions/triggers/replacements remain in
`docs/RUNTIME_TRAINING_LOCATIONS.md`.

## Exact Phase 5 next steps

1. Obtain a privacy-approved Supabase export containing only internal UID and
   state; keep it outside Git.
2. Run the aggregate audit command and review status/rejection distributions.
3. Fix collection reliability if unusable sessions exceed the proposed gate.
4. Do not train until dataset-level gate passes.
5. When the global gate eventually passes, freeze the content-addressed snapshot,
   create primary and secondary split manifests, and rerun them for checksum
   parity.
6. Implement a real-user **experimental** training entrypoint reusing the offline
   guard, existing candidate models, metrics, and registry metadata.
7. Compare against both frozen baselines using the promotion policy; keep the
   current model if any required check fails.
8. Separately migrate legacy runtime fits, starting with Duration, with inference
   parity tests and no automatic promotion.

## Stop condition confirmation

Phase 4 trained no model, created no production artifact, changed no inference,
added no TensorFlow/TFLite, implemented no fine-tuning/personal model, and made no
accuracy claim. Its successful output is a reproducible audit/evaluation decision
foundation with an honest `NOT READY` result.
