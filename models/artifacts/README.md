# Artefak Model Lokal

Folder ini hanya untuk binary model lokal yang dapat dibangun ulang dan tidak dilacak Git.

## Yang boleh disimpan

- artefak hasil eksperimen lokal;
- output sementara untuk inspeksi;
- model legacy yang sengaja dibangun lewat tool pengembang.

## Yang tidak boleh disimpan

- secret atau credential;
- export data pengguna;
- artifact production tanpa kontrol akses;
- binary yang dianggap aktif hanya karena berada di folder ini.

`tools/train_duration_model.py` adalah tool legacy eksplisit, bukan jalur startup aplikasi. Runtime production tidak mempercayai file di folder ini secara otomatis.

Artifact yang akan dipakai production harus:

1. melewati evaluasi dan review;
2. dicatat sebagai `promoted` di `models/approved_models.json`;
3. tersedia melalui environment path, misalnya `FOCUSBUDDY_DURATION_MODEL_PATH`;
4. lolos verifikasi SHA-256 oleh `models/model_registry.py`.

Lihat [ml/registry/README.md](../../ml/registry/README.md) untuk lifecycle kandidat.
