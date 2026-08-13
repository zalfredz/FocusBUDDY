# Registry Kandidat Model

Registry ini menyimpan indeks dan metadata kandidat hasil eksperimen offline. Ia bukan artifact store production.

## Isi folder

- `index.json`: daftar versi kandidat dan pointer status registry.
- `metadata/`: metadata JSON untuk setiap eksperimen.
- `artifacts/`: binary lokal hasil eksperimen; diabaikan Git.
- `metadata.py`: validasi dan penulisan metadata registry.

Field `production` pada `index.json` sengaja `null`. Runtime aplikasi tidak membaca kandidat experimental dari folder ini.

## Metadata wajib

Setiap kandidat harus mencatat:

- nama dan versi model;
- status registry;
- versi/hash dataset;
- feature schema;
- ukuran dan kebijakan split;
- seed dan hyperparameter;
- metric serta acceptance gate;
- versi framework/runtime;
- timestamp;
- path dan checksum artefak.

## Status

- `experimental`: hasil eksplorasi, belum boleh dipakai runtime.
- `candidate`: telah memenuhi gate eksperimen dan menunggu review.
- `promoted`: disetujui secara eksplisit untuk jalur production.
- `retired`: tidak lagi digunakan.

## Batas production

Artifact production disimpan di artifact store privat. Promosi dicatat terpisah pada [models/approved_models.json](../../models/approved_models.json). Runtime hanya menerima artifact jika:

1. entry berstatus `promoted`;
2. path diberikan melalui environment yang ditentukan entry;
3. file tersedia;
4. SHA-256 sama dengan checksum approval.

Jangan mengganti `production` atau menyalin binary ke runtime sebagai jalan pintas promosi.
