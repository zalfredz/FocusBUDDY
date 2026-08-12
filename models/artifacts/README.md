# Local Model Artifacts

Folder ini hanya untuk artifact lokal yang dapat dibangun ulang dan diabaikan
Git. `tools/train_duration_model.py` adalah tool legacy eksplisit, bukan jalur
startup aplikasi.

Production tidak mempercayai file di folder ini. Artifact production harus
melewati evaluasi dan promosi registry, tersedia melalui environment, lalu lolos
verifikasi checksum oleh `models/model_registry.py`.
