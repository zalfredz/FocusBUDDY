# FocusBuddy ML Offline

Folder ini memisahkan eksperimen dan training dari runtime aplikasi.

```text
raw dataset
-> validation + dataset manifest
-> 80/20 holdout split
-> cross-validation pada 80% train
-> pilih kandidat dari hasil CV
-> evaluasi sekali pada 20% locked test
-> experimental artifact + metadata
```

Jalankan baseline Duration dari root repository:

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/python -m ml.experiments.duration_baseline
```

Output utama:

- `reports/duration_baseline.csv`
- `reports/duration_baseline.json`
- `ml/registry/artifacts/duration-baseline-v1.joblib`
- `ml/registry/metadata/duration-baseline-v1.json`

Tidak ada modul di folder ini yang boleh dipakai langsung oleh `app/` atau
`models/`. Artefak yang dibuat masih berstatus **experimental**, bukan model
produksi.

Audit export outcome user tanpa training:

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/python \
  -m ml.evaluation.real_user_data_audit \
  --input path/ke/supabase-export.json \
  --output reports/real-user-readiness.json
```

Input harus berisi row `{user_id, state}` dari export offline Supabase. Report
hanya memuat agregat; UID dan teks tugas tidak ditulis ke report. Command ini
tidak memanggil `.fit()` dan akan menghasilkan `NOT READY FOR RETRAINING` jika
gate data nyata belum terpenuhi.

Validasi Phase 7 untuk Global versus personal calibration:

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/python \
  -m ml.experiments.phase7_real_user_validation \
  --input datasets/private/supabase-focusbuddy-states.json \
  --report-dir reports
```

Command hanya mengevaluasi secara offline dan hanya membuat
`personalization_evaluation.json` ketika ada history serta temporal holdout nyata
yang cukup. Ia tidak melatih Global Model, memperbarui state user, atau melakukan
promotion.
