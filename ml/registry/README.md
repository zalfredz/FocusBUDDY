# Experimental Model Registry

Registry ini hanya menyimpan metadata kandidat hasil eksperimen offline. Field
`production` pada `index.json` sengaja tetap `null`; runtime aplikasi tidak
membaca kandidat eksperimen ini.

Setiap artefak harus mempunyai metadata pendamping yang berisi versi model,
versi dataset, feature schema, ukuran split, timestamp, seed, hyperparameter,
metrics, versi framework, dan path artefak.

Binary di `ml/registry/artifacts/` diabaikan Git. Artifact production harus
disimpan di artifact store privat. Promosi dicatat terpisah di
`models/approved_models.json`; runtime baru menerima file bila statusnya
`promoted`, path diberikan lewat environment, dan SHA-256 cocok.
