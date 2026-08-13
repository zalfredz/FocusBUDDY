# Dataset FocusBuddy

Folder ini berisi dataset yang dipakai untuk runtime lokal, eksperimen offline, dan evaluasi. Jangan menaruh export pengguna atau data rahasia di folder yang dilacak Git.

## Daftar file

| File | Peran |
| --- | --- |
| `task_decomposition_id.csv` | Corpus pola pecah tugas produksi berbahasa Indonesia. |
| `task_decomposition_id_v2.csv` | Iterasi corpus Indonesia untuk pengembangan/evaluasi. |
| `task_decomposition_id_v3.csv` | Iterasi lanjutan corpus Indonesia. |
| `task_decomposition_en.csv` | Dataset pembanding berbahasa Inggris. |
| `task_decomposition_queries.csv` | Query berlabel untuk evaluasi retrieval. |
| `task_decomposition_eval_id.csv` | Benchmark offline Indonesia: exact, paraphrase, dan negative. Tidak dipakai sebagai corpus runtime. |
| `task_duration_id.csv` | Dataset awal estimasi durasi tugas. |
| `task_duration_id_clean.csv` | Dataset durasi yang sudah dibersihkan. |
| `task_duration_features_v3.csv` | Dataset fitur untuk eksperimen durasi v3. |
| `bpom_products_2026-08-01.csv` | Snapshot mentah produk obat BPOM bertanggal 1 Agustus 2026. |
| `generated/bpom_index.json` | Indeks BPOM ringkas yang dibaca aplikasi. |

## Aturan penggunaan

- Pisahkan data train, validation, test, dan benchmark agar tidak terjadi leakage.
- Dataset evaluasi tidak boleh dimasukkan ke corpus atau training.
- Setiap eksperimen harus mencatat versi/hash dataset, seed, split policy, dan feature schema.
- Data outcome pengguna nyata harus disimpan di lokasi privat, diaudit, dan diagregasi sebelum dipakai untuk evaluasi.
- Jangan commit UUID, email, token, teks cerita, atau teks tugas pengguna nyata.
- Pembaruan snapshot BPOM harus menyertakan tanggal sumber dan membangun ulang `generated/bpom_index.json`.

## Perintah terkait

Audit dataset pecah tugas:

```powershell
python tools/inspect_task_decomposition_dataset.py
```

Evaluasi retrieval produksi:

```powershell
python tools/evaluate_retrieval.py
```

Bangun ulang indeks BPOM setelah snapshot sumber diperbarui:

```powershell
python tools/build_bpom_index.py
```

Lihat [ml/README.md](../ml/README.md) untuk pipeline eksperimen dan [docs/TASK_DECOMPOSITION_RETRIEVAL.md](../docs/TASK_DECOMPOSITION_RETRIEVAL.md) untuk kontrak retrieval.
