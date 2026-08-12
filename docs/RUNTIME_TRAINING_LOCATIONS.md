# Runtime Training Locations

Audit Phase 6 mencari `fit`, `fit_transform`, `partial_fit`, `train`,
`retrain`, dan `fine_tune` di source aplikasi, model, tool, dan pipeline ML.

## Runtime production

`app.runtime_policy.runtime_mode()` mengenali Render dari `RENDER` /
`RENDER_SERVICE_ID`, atau menerima `FOCUSBUDDY_RUNTIME_MODE=production`.
Semua jalur berikut masih dipertahankan untuk kompatibilitas pengembangan,
tetapi sekarang berhenti sebelum fitting ketika proses adalah production.

| File / function | Trigger | Model | Klasifikasi | Guard Phase 6 | Pengganti produksi |
|---|---|---|---|---|---|
| `models/model_durasi.py::_latih()` | estimasi/status pertama | TF-IDF + Random Forest | legacy runtime training | Ya | Muat artifact Duration yang promoted dan checksum-valid; bila belum ada gunakan static fallback. |
| `app/core/energy_predictor.py::_get_model()` | prediksi energi pertama | Decision Tree sintetis | legacy runtime training | Ya | Rule deterministik yang ekuivalen dengan prior tanpa noise. |
| `models/model_mood.py::_latih()` | Morning Brief/status | Random Forest personal | legacy runtime training | Ya | Fallback rata-rata hari; global model perlu eksperimen terpisah. |
| `app/core/mood_model.py::_predict_today()` | halaman Mood, ≥10 log | Decision Tree personal | legacy runtime training | Ya | Tidak menghasilkan prediksi model; insight deskriptif tetap berjalan. |
| `models/model_overwhelm.py::_latih()` | Home/status | Logistic Regression personal | legacy runtime training | Ya | Prior rule-based yang sudah ada. |
| `models/model_kalem.py::_latih()` | rekomendasi/status | Logistic Regression personal | legacy runtime training | Ya | Sinyal `belum_cukup_data`; decision rules tetap berjalan. |
| `models/model_pecah.py::cari()` | retrieval setiap query | TF-IDF corpus fit | fitting retrieval, bukan supervised outcome training | Ya | `HashingVectorizer.transform()` stateless di production. |

Guard ini menghapus risiko model global di RAM berubah karena satu pengguna.
Mode lokal/development masih dapat menjalankan legacy behavior untuk regression
parity; itu adalah utang migrasi, bukan arsitektur akhir.

## Offline-only

| Lokasi | Klasifikasi | Batas |
|---|---|---|
| `ml/training/duration.py` | legitimate offline experiment | Wajib berada dalam `offline_training_session()`. |
| `ml/training/duration_clean.py` | legitimate offline experiment | Wajib berada dalam `offline_training_session()`. |
| `ml/experiments/*.py` | experiment controller | Dijalankan eksplisit dari CLI; tidak diimpor `app/` atau `models/`. |
| `tools/train_duration_model.py` | legacy explicit offline tool | Bukan startup/request path; kelak diganti penuh oleh pipeline `ml/`. |
| `tests/*.py` | test-only fitting/mocking | Tidak termasuk runtime aplikasi. |

Tidak ditemukan `partial_fit`, `fine_tune`, atau retraining otomatis baru.

## Risiko tersisa

- Artifact promoted belum ada karena Phase 5 berstatus NOT READY. Production
  Duration karena itu menggunakan fallback statis, bukan melatih model diam-diam.
- Jalur legacy fitting masih ada untuk pengembangan. Penghapusannya perlu parity
  test per model pada fase migrasi berikutnya.
- Artifact eksperimen lokal masih dapat dibuat ulang, tetapi diabaikan Git dan
  tidak boleh dipromosikan hanya dengan menaruh file di server.
- `HashingVectorizer` production dapat memberi skor retrieval sedikit berbeda
  dari TF-IDF lokal; ambang konservatif dan fallback KALEM tetap berlaku.
