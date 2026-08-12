# PECAH TUGAS: Retrieval Indonesia

PECAH TUGAS bukan model supervised dan tidak memiliki proses training. Dataset
`datasets/task_decomposition_id.csv` adalah corpus/knowledge base berisi 212
pola Indonesia. Ia dipakai untuk mencocokkan tugas baru, bukan untuk melatih
classifier atau neural network.

## Alur produksi

```text
Tugas pengguna
  -> cek bahasa/corpus: hanya record berlabel `id`
  -> retrieval terhadap 212 pola Indonesia
  -> confidence >= 0.72 dan selisih kandidat pertama-kedua >= 0.03
  -> langkah hasil retrieval
  -> bila tidak lolos: KALEM bila tersedia, atau template manual/rule-based
```

Deskripsi pengguna yang berisi dua baris atau lebih tetap menjadi prioritas:
langkah diambil langsung dari deskripsi tersebut. Ini bukan retrieval dan tidak
memakai kuota penyusunan KALEM.

Pada runtime produksi pencocokan memakai cosine similarity char n-gram dengan
`HashingVectorizer`, sehingga tidak ada `fit()` pada saat aplikasi berjalan.
Mode pengembangan boleh memakai TF-IDF untuk eksperimen retrieval saja; itu
bukan training supervised dan tidak dipakai di Render.

## Batas keamanan

- Corpus produksi dan record pengguna yang dipakai retrieval harus memiliki
  `language: id` secara eksplisit. Record legacy tanpa label bahasa diabaikan
  daripada berisiko tercampur dengan bahasa lain.
- Ambang dan margin ambigu bersifat konservatif. Jika ragu, hasil ditolak dan
  tidak dipaksakan menjadi pola yang salah.
- Kuota hanya mengatur apakah panggilan KALEM dapat dilakukan. Retrieval,
  langkah dari deskripsi pengguna, dan fallback rule-based tetap berjalan saat
  kuota habis atau provider belum terkonfigurasi.
- Provenance agregat memakai `lokal`, `ai`, `fallback`, atau `campuran`.
  `campuran` wajib dipakai bila satu rencana memuat kombinasi retrieval/manual,
  KALEM, atau fallback. Per tugas, `task_sources` menyimpan asalnya.
- Respons KALEM parsial tidak boleh membuat tugas lain hilang: tugas yang tidak
  mendapat langkah mendapat fallback rule-based dan sumber `fallback`.

## Evaluasi offline

Dataset evaluasi terpisah: `datasets/task_decomposition_eval_id.csv`.
Dataset ini tidak mengubah corpus dan tidak berisi data pengguna. Komposisinya:

- 20 query exact/easy;
- 30 parafrase bahasa Indonesia;
- 20 query negatif di luar corpus.

Jalankan dari root proyek:

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/python tools/evaluate_retrieval.py
```

Tool menulis `reports/task_decomposition_retrieval_eval.json` dengan retrieval
accuracy, precision, coverage, false/wrong retrieval rate, dan fallback rate.
Laporan tidak menyimpan raw query evaluasi. Hasil harus dibaca terutama dengan
wrong retrieval rate: fallback aman lebih baik daripada mengembalikan langkah
yang tidak relevan.

## Status

Retrieval ini siap dipakai sebagai baseline produksi yang konservatif untuk
query yang sangat dekat dengan pola Indonesia. Ia belum dapat disebut matang
secara semantik: banyak parafrase aman-fallback karena TF-IDF/char n-gram tidak
memahami makna. Peningkatan semantik, bila dibutuhkan kelak, harus dievaluasi
terpisah terhadap benchmark yang sama sebelum mengubah ambang atau perilaku
produksi.
