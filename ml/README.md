# Machine Learning Offline FocusBuddy

Folder `ml/` memisahkan training dan evaluasi offline dari runtime aplikasi. Modul di `app/` dan `models/` tidak boleh melatih model saat startup, request, check-in, atau sesi fokus.

## Pipeline

```text
dataset tervalidasi
  -> manifest + feature schema
  -> split train/locked test
  -> cross-validation pada train
  -> pemilihan kandidat
  -> evaluasi sekali pada locked test
  -> artefak experimental + metadata + report
  -> review dan promosi eksplisit bila seluruh gate lolos
```

## Struktur

```text
ml/
├── datasets/       # fixture dan utilitas dataset khusus pipeline
├── evaluation/     # readiness, retrieval, dan personalisasi
├── experiments/    # entry point eksperimen terkontrol
├── registry/       # indeks serta metadata kandidat offline
└── training/       # guard yang mewajibkan offline_training_session()
```

## Baseline durasi

Jalankan dari root repository:

```powershell
python -m ml.experiments.duration_baseline
```

Output yang diharapkan:

- `reports/duration_baseline.csv`;
- `reports/duration_baseline.json`;
- `ml/registry/artifacts/duration-baseline-v1.joblib`;
- `ml/registry/metadata/duration-baseline-v1.json`.

Status artefak baseline adalah experimental, bukan production-ready.

## Audit outcome pengguna

Audit export Supabase tanpa training:

```powershell
python -m ml.evaluation.real_user_data_audit `
  --input path\ke\supabase-export.json `
  --output reports\real-user-readiness.json
```

Input adalah array row `{user_id, state}` dari export offline yang dibatasi aksesnya. Report hanya memuat agregat; UID dan teks tugas tidak ditulis kembali. Command tidak memanggil `.fit()` dan menghasilkan `NOT READY FOR RETRAINING` jika gate belum terpenuhi.

## Validasi personalisasi Phase 7

```powershell
python -m ml.experiments.phase7_real_user_validation `
  --input datasets\private\supabase-focusbuddy-states.json `
  --report-dir reports
```

Validasi memakai temporal holdout dan membandingkan Global dengan Global + calibration. Proses ini tidak melatih Global Model, mengubah state pengguna, mengaktifkan model, atau mempromosikan artefak.

## Guardrail

- Training hanya boleh berjalan di dalam `offline_training_session()`.
- Runtime production harus inference-only.
- Fixture sintetis menguji pipeline, bukan membuktikan performa pada pengguna nyata.
- Report tidak boleh dianggap klaim production-ready tanpa gate, review, dan promosi eksplisit.
- Artefak production harus tercatat di `models/approved_models.json`, berstatus `promoted`, disuplai melalui environment, dan lolos SHA-256.

Detail lanjutan ada di [docs/ML_ARCHITECTURE.md](../docs/ML_ARCHITECTURE.md) dan [docs/ML_OUTCOME_DATA_COLLECTION.md](../docs/ML_OUTCOME_DATA_COLLECTION.md).
