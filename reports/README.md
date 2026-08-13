# Laporan Eksperimen

Folder ini berisi output eksperimen dan evaluasi yang dapat direproduksi. Keberadaan report tidak berarti model siap production.

## Kelompok report

### Estimasi durasi

- `duration_baseline.csv` dan `.json`;
- `duration-clean-v2.csv` dan `.json`;
- `duration-features-v3.csv` dan `.json`.

Jalankan entry point terkait dari root repository, misalnya:

```powershell
python -m ml.experiments.duration_baseline
```

### Readiness dan personalisasi

- `real_user_data_readiness.json`;
- `personalization_readiness.json`;
- `personalization_evaluation.json` hanya jika temporal holdout nyata cukup;
- `phase5-real-user-retraining.json`.

Report yang berasal dari fixture sintetis harus ditandai oleh `audited_input.scope`. Angkanya hanya memvalidasi pipeline dan tidak boleh dipresentasikan sebagai hasil query database live atau performa pengguna nyata.

### Retrieval Pecah Tugas

`task_decomposition_retrieval_eval.json` dibuat melalui:

```powershell
python tools/evaluate_retrieval.py
```

Report mengukur perilaku corpus Indonesia terhadap query exact, paraphrase, dan negative. Ini benchmark correctness retrieval, bukan artefak training.

## Cara membaca report

Periksa minimal:

1. commit dan versi dataset;
2. scope input: synthetic, restricted export, atau lainnya;
3. split policy dan kemungkinan leakage;
4. metric utama serta baseline pembanding;
5. acceptance gate;
6. status akhir dan alasan bila `NOT READY`;
7. pernyataan apakah inference production berubah.

## Aturan penyimpanan

- Report boleh dilacak Git jika hanya berisi agregat aman dan ukurannya wajar.
- Jangan menyimpan UUID, email, token, teks tugas, cerita, atau data mentah pengguna.
- Binary model disimpan di artifact store/registry yang sesuai, bukan di folder report.
- Jangan mengedit angka report secara manual; jalankan ulang pipeline yang membuatnya.
