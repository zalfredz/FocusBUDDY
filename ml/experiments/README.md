# Experiments

Semua eksperimen harus mempunyai seed tetap, dataset manifest, split policy,
metrics, dan output report. Entry point eksperimen bertanggung jawab membuka
`offline_training_session()`; fungsi training akan menolak call dari luar sesi
tersebut.
## Phase 5 real-user guard

Phase 5 harus selalu dimulai dari export outcome yang sudah diaudit:

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/python \
  -m ml.experiments.real_user_duration_v1 \
  --input path/ke/supabase-export.json \
  --report reports/phase5-real-user-retraining.json
```

Pada repository saat ini, satu-satunya input adalah fixture sintetis. Controller
berhenti dengan `REAL USER RETRAINING STATUS: NOT READY` sebelum split atau
training. Ia tidak membuat artifact maupun metrics palsu. Jika suatu export nyata
kelak melewati seluruh gate Phase 4, training candidate tetap memerlukan reviewed
controlled run baru; controller tidak otomatis menyeberangi boundary tersebut.

## Phase 7 personalization validation

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/python \
  -m ml.experiments.phase7_real_user_validation \
  --input datasets/private/supabase-focusbuddy-states.json \
  --report-dir reports
```

Phase 7 memakai prior-only temporal holdout per user. Global prediction dan
Global + calibration dibandingkan tanpa `.fit()`, tanpa activation, dan tanpa
promotion. Raw UUID serta task text tidak ditulis ke aggregate report.
