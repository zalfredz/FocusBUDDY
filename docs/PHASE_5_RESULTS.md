# Phase 5 — Real-User Retraining Experiment

## Final status

**REAL USER RETRAINING STATUS: NOT READY**

Critical stop condition `no_real_user_training_eligible_data` terpicu. Phase 5
berhenti sebelum splitting, model fitting, model selection, locked-test access,
artifact creation, atau promotion evaluation.

## 1. Data readiness

Workspace diaudit untuk export outcome dan hanya menemukan
`ml/datasets/fixtures/user_outcomes_v1.synthetic.json`. Tidak ada export Supabase
outcome nyata yang tersedia.

| Item | Hasil |
|---|---:|
| Real users with outcomes | 0 |
| Raw outcome sessions | 2 |
| Real outcome sessions | 0 |
| Valid sessions | 2 synthetic sessions |
| Suspicious sessions | 0 |
| Invalid sessions | 0 |
| Unknown sessions | 0 |
| Real completed task-occurrence candidates | 0 |
| Training-eligible real-user rows | 0 |
| Synthetic rows | 2 |
| Duplicate record IDs | 0 |
| Duplicate session IDs | 0 |

`valid_sessions=2` hanya berarti fixture konsisten dengan schema. Synthetic
provenance membuat task group tersebut tetap ditolak untuk training.

Gate yang gagal:

- dataset eligible occurrences;
- dataset eligible users;
- users dengan minimal 5 occurrences;
- global eligible occurrences dan users;
- users dengan minimal 10 occurrences;
- expected locked-test row count;
- long-task occurrence coverage;
- keseluruhan global dataset gate.

Gate session quality dan `no_synthetic_training_rows` lulus, tetapi itu tidak
menggantikan ketiadaan data nyata.

## 2. Number of real-user training rows

**0 rows.** Fixture synthetic menghasilkan satu completed task occurrence untuk
tes aggregation, tetapi builder menolaknya dengan alasan
`task_group:synthetic`. Tidak ada row yang diteruskan ke training.

## 3. Dataset version and checksum

Audit terhadap set candidate nyata yang kosong menghasilkan:

- dataset version:
  `focusbuddy-user-outcomes-v1-sha256-4f53cda18c2b`;
- candidate dataset checksum:
  `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`;
- synthetic source checksum:
  `bcd167f50a268d7957bf93521c6cbb5e8024bb4da864539c9046738d1d37ffea`.

Ini checksum empty eligible-candidate set, bukan real-user dataset artifact.
Karena stop condition terpicu, tidak dibuat training CSV/JSON snapshot baru.

## 4. Models evaluated

Tidak ada. Median baseline, Decision Tree, Random Forest, Extra Trees, Gradient
Boosting, dan HistGradientBoosting **tidak dijalankan**. Menjalankannya pada
fixture synthetic akan melanggar Phase 5.

## 5. CV results

Tidak dievaluasi. Tidak ada 80% training-user partition dan tidak ada 5-fold CV.

## 6. Locked-test results

Tidak dievaluasi. Locked test tidak dibentuk atau diakses.

## 7. Comparison against Phase 1/2

Tidak dapat dievaluasi tanpa real-user candidate dan comparable split. Phase 1
HistGradientBoosting tetap baseline experimental yang dipilih; Phase 2 tetap
tidak melewati improvement gate. Tidak ada angka Phase 5 yang dibandingkan atau
digabungkan dengan angka human-estimated dataset lama.

## 8. Long-task performance

Tidak dapat dievaluasi. Ada 0 real task occurrence, termasuk 0 task >300 menit.

## 9. Leakage results

Duplicate audit menemukan 0 duplicate record dan 0 duplicate session pada
fixture. User-group dan temporal/task-family split **tidak dijalankan**, sehingga
hasil leakage split adalah `NOT EVALUATED — ZERO ELIGIBLE REAL-USER ROWS`, bukan
klaim “0 leakage”.

## 10. Promotion decision

`NOT EVALUATED`. Tidak ada candidate metrics untuk menjalankan
`duration-promotion-v1`. Status model adalah `NO MODEL TRAINED`, bukan
production-ready dan bukan candidate for promotion. Production behavior tetap.

## 11. Artifacts created

Hanya control-plane report:

- `reports/phase5-real-user-retraining.json`;
- dokumen ini;
- guarded controller `ml/experiments/real_user_duration_v1.py`;
- Phase 5 regression contracts `tests/test_ml_phase5.py`.

Tidak dibuat:

- model artifact;
- model metadata/registry entry;
- metrics CSV/JSON;
- training dataset snapshot;
- split manifest;
- production configuration.

## 12. Reproducibility and tests

Controller menggunakan Phase 4 validator, aggregation, content-addressed dataset
version, readiness policy, dan source checksum. Input yang sama menghasilkan
report byte-identical. Aggregate report tidak memuat raw task text, UID, nama,
atau email.

Phase 5 tests memastikan:

- zero-real-data critical stop;
- failed gate names tersimpan;
- synthetic group ditolak;
- split/metrics/artifact tidak dikarang;
- report reproducible dan PII-safe;
- controller tidak berisi `.fit()`, training session, TensorFlow, atau TFLite.

Hasil final:

- ML Foundation: 11/11;
- Phase 2: 6/6;
- Phase 3: 11/11;
- Phase 4: 10/10;
- Phase 5: 5/5;
- 13 application acceptance scripts: seluruhnya lulus;
- Cloud/Auth: 18/18;
- compile checks: lulus;
- `git diff --check`: lulus.

## 13. Production-code changes

Phase 5 tidak mengubah `app/`, `models/`, production inference, Supabase schema,
atau runtime behavior. Perubahan Phase 5 hanya berada di offline `ml/`, tests,
reports, dan docs. Perubahan production logging dari Phase 3 masih terdapat pada
working tree sebagai pekerjaan fase sebelumnya, tetapi Phase 5 tidak
menambah/mengubahnya.

## Next required input

Phase 5 hanya dapat dilanjutkan setelah tersedia export Supabase yang:

1. telah disetujui untuk penggunaan ML offline;
2. berisi internal user UUID dan state tanpa PII tambahan;
3. melewati Phase 4 global retraining gate;
4. reproducible sebagai content-addressed snapshot;
5. memungkinkan 80/20 user-group locked split tanpa task/session leakage.

Sampai itu tersedia, hasil yang benar tetap **NOT READY** dan tidak ada model
yang boleh dilatih.
