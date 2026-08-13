# Eksperimen ML

Folder ini berisi entry point eksperimen offline yang reproducible. Eksperimen bukan bagian dari startup aplikasi dan tidak boleh dipanggil dari UI.

## Kontrak eksperimen

Setiap eksperimen wajib mempunyai:

- seed tetap;
- manifest dan versi dataset;
- feature schema;
- kebijakan split yang terdokumentasi;
- metric dan acceptance gate;
- report yang dapat diaudit;
- metadata artefak;
- status yang jelas: experimental, candidate, promoted, atau retired.

Entry point yang melakukan training harus membuka `offline_training_session()`. Guard akan menolak `.fit()` dari luar sesi offline.

## Eksperimen durasi

```powershell
python -m ml.experiments.duration_baseline
python -m ml.experiments.duration_clean_v2
python -m ml.experiments.duration_features_v3
```

Masing-masing menghasilkan report di `reports/` dan metadata di `ml/registry/metadata/`. Hasil tidak otomatis dipakai runtime.

## Phase 5 — real-user retraining guard

```powershell
python -m ml.experiments.real_user_duration_v1 `
  --input path\ke\supabase-export.json `
  --report reports\phase5-real-user-retraining.json
```

Controller memerlukan export outcome yang sudah diaudit. Jika gate data nyata belum terpenuhi, proses berhenti dengan `REAL USER RETRAINING STATUS: NOT READY` sebelum split atau training dan tidak membuat metric/artefak palsu.

Lolos audit belum berarti boleh langsung training. Kandidat baru tetap memerlukan controlled run serta review terpisah.

## Phase 7 — validasi personalisasi

```powershell
python -m ml.experiments.phase7_real_user_validation `
  --input datasets\private\supabase-focusbuddy-states.json `
  --report-dir reports
```

Phase 7 memakai prior-only temporal holdout per pengguna. Global prediction dan Global + calibration dibandingkan tanpa `.fit()`, activation, atau promotion. Raw UUID dan teks tugas tidak masuk report agregat.

## Checklist sebelum menjalankan

1. Pastikan input berasal dari lokasi privat yang benar.
2. Catat commit dan hash dataset.
3. Jangan memakai test set untuk memilih hyperparameter.
4. Periksa report terhadap acceptance gate.
5. Simpan artefak privat; jangan commit binary besar.
6. Jangan mengubah `models/approved_models.json` tanpa review promosi.
