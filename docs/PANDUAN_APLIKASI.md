# Panduan Aplikasi FocusBuddy

Panduan ini menjelaskan alur aplikasi FocusBuddy versi saat ini dari sudut pandang pengguna. Nama pendamping di dalam aplikasi adalah KALEM.

FocusBuddy bukan alat diagnosis dan bukan pengganti tenaga medis.

## 1. Masuk ke aplikasi

1. Buka FocusBuddy melalui browser atau aplikasi desktop.
2. Pilih `Masuk dengan Google`.
3. Selesaikan login Google dan izinkan browser kembali ke FocusBuddy.
4. Data akun akan dimuat dari Supabase. Jika koneksi terganggu, aplikasi dapat memakai cache sesi dan mencoba sinkronisasi kembali.

Jika login terus kembali ke halaman awal, periksa koneksi internet dan pastikan alamat callback yang dibuka sama dengan domain FocusBuddy.

## 2. Onboarding pertama

Onboarding dimulai dengan dua data utama:

1. Isi nama pada `Mau dipanggil apa?`, lalu tekan `Selanjutnya`.
2. Pilih tanggal pada `Tanggal Lahir Kamu?`, lalu tekan `Selanjutnya`.

Pertanyaan berikutnya membantu KALEM mengenal ritme pengguna:

- kesibukan saat ini;
- jam yang biasanya produktif;
- pola tidur terakhir;
- obat atau suplemen rutin;
- hal yang membuat khawatir atau kewalahan.

Pertanyaan personalisasi ini tidak wajib. Tekan `Lewati` untuk lanjut tanpa menjawab. Semua jawaban dapat dilengkapi atau diubah lagi dari Pengaturan.

Tanggal lahir disimpan sebagai tanggal kalender. Usia dihitung otomatis saat diperlukan, sehingga tidak menjadi angka yang kedaluwarsa.

## 3. Navigasi utama

Navigation bar mempunyai tiga tab:

- `Tracker` untuk kalender, tugas, dan riwayat fokus;
- `Home` untuk saran tugas dan sesi fokus;
- `Mood` untuk check-in, insight, grafik, cerita, dan favorit.

Hanya tab yang sedang aktif menampilkan tulisan; tab lain hanya menampilkan ikon.

Selama sesi fokus berjalan, perpindahan tab ditahan. Pilih `Lanjut fokus` pada popup, lalu pause atau sudahi sesi dari Home jika memang ingin berpindah halaman.

## 4. Insight pagi

Insight pagi muncul sekali per hari sebelum Home.

### Ketika data belum cukup

KALEM menampilkan progress jumlah catatan yang diperlukan untuk mulai membaca pola. Pilih:

- `Oke, Mulai Aja` untuk lanjut ke Home;
- `Aku ngerasa beda` untuk mengisi kondisi hari ini sendiri.

### Ketika data sudah cukup

KALEM dapat menampilkan salah satu ringkasan:

- `Kemungkinan biasa aja`;
- `SEMANGAT!! Hari ini mungkin berat`;
- `Semangat kamu FULL hari ini`.

Di bawahnya ada alasan singkat dari pola yang terbaca serta saran sesi fokus. Prediksi ini hanya refleksi dari catatan pengguna, bukan diagnosis. Jika prediksi tidak sesuai, pilih `Aku ngerasa beda`.

## 5. Home

Bagian atas menampilkan `Hai! Nama` tanpa koma. Maskot dan bubble chat mengikuti energi terakhir:

- energi 1–3: `Kamu kelihatan capek. Istirahat juga termasuk progress loh...`;
- energi 4–6: `Semangat untuk Hari Ini!`.

### Jika ada tugas hari ini

KALEM memilih satu tugas yang paling masuk akal untuk dikerjakan sekarang. Card menampilkan nama tugas, asal tugas, progress, dan tombol memulai fokus.

Pilih `Tambah Tugas` jika ingin membuka form tugas dari keadaan Home yang mempunyai tugas.

### Jika tidak ada tugas hari ini

Home menampilkan:

```text
Nggak ada tugas hari ini [Nama],
Enjoy the Day!
```

Tidak ada tombol tambah tugas pada keadaan kosong. Di bawah teks langsung tersedia `Ada yang Keingat?` dan `Kewalahan? YUK AMBIL JEDA`.

## 6. Catatan cepat

Pilih `Ada yang Keingat?` untuk membuka form:

- judul: `Apapun yang kamu mau ingat`;
- isi dapat berupa tugas, cerita, atau hal lain yang ingin disimpan sementara.

Catatan masuk ke `Catatan Kamu`. Jika masih kosong, halaman menampilkan `Masih kosong nihh`.

Untuk merapikan catatan menjadi tugas:

1. buka `Catatan Kamu`;
2. pilih `Jadiin tugas` pada catatan;
3. periksa nama dan tambahkan konteks bila perlu;
4. gunakan rekam suara jika tersedia;
5. atur jam, tandai penting, atau pilih pecah otomatis;
6. tekan `Jadiin tugas`.

## 7. Tracker dan kalender

Tracker membuka kalender mingguan. Header kalender menampilkan nama bulan dan tahun lengkap, misalnya `Agustus 2026`.

- Pilih tanggal untuk melihat tugas aktif pada tanggal itu.
- Pilih `Bulan Ini` untuk membuka kalender bulanan lengkap.
- Gunakan Harian, Mingguan, atau Bulanan untuk mengubah ringkasan `Sebaran Tugas`.

Perubahan filter tidak mengganti daftar tugas aktif; daftar itu tetap mengikuti tanggal yang dipilih agar tidak mencampur terlalu banyak konteks.

Urutan utama Tracker adalah kalender, filter, tombol `Tambah Tugas` dan `Pecah Tugas`, Sebaran Tugas, daftar tugas, lalu Focus History.

## 8. Menambah tugas

Pilih `Tambah Tugas` di Tracker. Form dibagi menjadi tiga bagian agar mudah dibaca.

### Nama dan deskripsi

- Nama tugas wajib diisi.
- Deskripsi bersifat opsional dan dipakai sebagai konteks: hasil yang diinginkan, batasan, atau informasi pendukung.
- Deskripsi bukan tempat menuliskan langkah pecahan tugas. KALEM menyusun langkah ketika fitur Pecah Tugas dijalankan.
- Ikon microphone dapat mengubah suara menjadi teks jika provider transkripsi telah dikonfigurasi.

### Deadline

- Aktifkan `Tanpa deadline` bila tugas tidak mempunyai batas waktu.
- Jika ada deadline, pilih tanggal dan jam dari kontrol bertema gelap.
- Tanggal mengikuti pilihan kalender pengguna dan tidak dikurangi atau ditambah satu hari.

### Prioritas dan tingkat kesulitan

- Tandai `Penting` jika dampaknya besar.
- Pilih seberapa berat tugas untuk mulai: Gampang, Sedang, atau Berat.
- Pilih pengulangan dari dropdown: Sekali, Harian, Mingguan, atau Bulanan.

Tekan `Tambah` untuk menyimpan.

## 9. Pecah Tugas

Pilih `Pecah Tugas`, centang satu atau beberapa tugas, lalu jalankan proses pecah. Form ini dibuat ringkas dan hanya menampilkan tugas yang dapat diproses.

KALEM memakai nama dan deskripsi sebagai konteks, kemudian menyusun langkah kecil. Jika AI tidak tersedia, aplikasi dapat memakai retrieval atau aturan lokal yang sesuai.

Hasil muncul sebagai card tepat di bawah aksi utama Tracker. Buka card untuk:

- menandai langkah selesai;
- mulai fokus dari langkah tertentu;
- mengedit teks langkah;
- menghapus langkah;
- menambah langkah baru.

Gunakan nama tugas untuk tujuan utamanya dan deskripsi untuk konteks. Jangan menaruh daftar langkah manual di deskripsi jika ingin hasil pecahan yang bersih.

## 10. Sesi fokus

Mulai sesi dari tugas yang disarankan di Home atau dari langkah tugas.

Layar fokus menampilkan:

- tugas dan asalnya;
- timer berbentuk lingkaran;
- progress tugas;
- pause;
- ulang sesi;
- `Sudahi`;
- `Ada yang Keinget?` di bawah card.

### Mengubah durasi

Pilih `Edit` pada card fokus, lalu isi durasi 1–30 menit. Nilai di luar rentang tersebut tidak dapat disimpan.

### Jika mencoba membuka tab lain

FocusBuddy menampilkan popup bertema gelap bahwa sesi masih aktif. Pilih `Lanjut fokus` untuk kembali. Pause atau sudahi sesi jika ingin keluar dengan sengaja.

Saat timer selesai atau sesi disudahi, outcome disimpan untuk membantu rekomendasi berikutnya.

## 11. Mood

Halaman Mood memakai maskot yang sama dengan Home dan Tracker.

### Check-in pertama hari itu

Check-in harian pertama berjalan dalam dua layar singkat:

1. pilih salah satu maskot: Cemas, Sedih, Lelah, Tenang, atau Semangat;
2. tekan `Lanjut`;
3. geser slider tenaga dari 1 sampai 6;
4. tekan `Lanjut` untuk menyimpan.

Nilai tenaga dipilih dengan menggeser slider, bukan dengan menekan deretan angka.

### Mengubah check-in

Pilih `Ubah check-in`. Form edit menempatkan pilihan maskot, slider tenaga, dan pertanyaan opsional `Istirahat cukup semalam?` dalam satu halaman yang dapat di-scroll dengan lancar. Simpan perubahan untuk memperbarui ringkasan hari itu.

### Susunan halaman Mood

Setelah ringkasan check-in, urutannya adalah:

1. `Yang KALEM paling pelajarin tentang kamu`;
2. satu card `Rekomendasi personal kamu`;
3. `Grafik Bulanan`;
4. `Cerita Kamu`;
5. akses Favorit melalui ikon hati di kanan atas.

Grafik bulan ini dapat dilihat tanpa membuka bulan lama. Penelusuran bulan sebelumnya mengikuti status fitur Freemium.

## 12. Cerita Kamu

Buka `Cerita Kamu` dari halaman Mood.

1. Ketik cerita pada textbox yang memenuhi lebar card, atau tekan microphone untuk merekam.
2. Rekaman maksimal diproses menjadi teks oleh provider yang tersedia.
3. Periksa hasil transkripsi sebelum menyimpan.
4. Tekan `Kirim ke Kalem`.

Pesan hijau `Tersimpan` menandakan cerita berhasil disimpan. Cerita sebelumnya tampil di bagian bawah halaman.

Jika rekam suara belum dikonfigurasi, pengguna tetap dapat mengetik. Jangan menutup halaman saat audio sedang diproses.

## 13. Favorit Kamu

Favorit membantu KALEM mengenali dukungan yang disukai pengguna, misalnya:

- musik atau genre yang menenangkan;
- suara alam atau background untuk fokus;
- tempat yang membantu fokus;
- comfort food atau minuman favorit;
- kondisi ruangan yang nyaman;
- hal lain yang membantu fokus.

Placeholder berwarna lebih redup daripada isi yang sudah disimpan. Tekan `Simpan`; notifikasi hijau menandakan perubahan berhasil tersimpan.

## 14. Kewalahan dan latihan jeda

Tekan `Kewalahan? YUK AMBIL JEDA` dari Home. Alur tidak langsung melompat ke selesai.

### Langkah 1 — Grounding

KALEM mengajak pengguna memperhatikan hal yang dilihat, disentuh, didengar, dicium, dan disyukuri. Angka tidak ditulis pada instruksi agar pengguna tidak merasa dibebani target.

Tekan `Udah` setiap selesai memperhatikan satu kelompok.

### Langkah 2 — Napas 4–7–8

Halaman menampilkan `Yuk Hirup Udara Segar Dulu` dan `Ikutin Lingkarannya Yaaa`. Ikuti lingkaran untuk:

1. tarik napas selama 4 hitungan;
2. tahan selama 7 hitungan;
3. buang perlahan selama 8 hitungan.

### Langkah 3 — Selesai dan check-in

Setelah animasi selesai, muncul halaman `Selesai`, lalu `Sekarang rasanya gimana?` dengan teks `Nggak harus langsung pulih kok`.

- `Sedikit lebih baik` membuka halaman bantuan ringan.
- `Belum bisa` mengulang grounding dan latihan napas sebelum bertanya lagi.

### Pelan-pelan aja

Halaman `Pelan-pelan aja yaaa` menawarkan:

- `Sebut Sekitar` untuk mengulang grounding;
- `Latihan nafas` untuk mengulang latihan 4–7–8;
- Into The Light, Halodoc, dan Riliv;
- HEALING119.ID dari KEMENKES melalui nomor 119.

FocusBuddy bukan layanan krisis. Bila ada bahaya langsung, hubungi layanan darurat setempat atau orang tepercaya di sekitar.

## 15. Pengingat Obat

Buka Pengaturan lalu pilih `Pengingat Obat`.

1. Isi nama obat.
2. Pilih hasil BPOM yang cocok jika tersedia. Obat tetap dapat disimpan saat tidak ditemukan, karena ejaan, merek, atau data dapat berbeda.
3. Isi sisa pil dan jumlah pil per hari sesuai resep dokter.
4. Tekan `Simpan`.

KALEM menampilkan perkiraan stok: `Pil kamu sisa [jumlah] nihh. KALEM bakal ingetin kalau stok obat kamu ga cukup buat 3 hari kedepan`.

Fitur ini hanya pengingat stok. FocusBuddy tidak menentukan obat, dosis, jadwal medis, atau perubahan terapi.

## 16. Pengaturan

Halaman Pengaturan memuat:

- profil;
- Pengingat Obat;
- Favorit Kamu;
- ringkasan yang sudah KALEM pelajari;
- privasi dan data;
- akun dan cloud;
- Langganan KALEM.

### Profil

Profil utama hanya menampilkan nama. Pengantar KALEM mengingatkan pengguna untuk melengkapi personalisasi. Pilih ikon pengaturan profil untuk mengubah:

- Ulang Tahun Kamu;
- Kesibukan saat ini;
- Jam Produktif Kamu;
- Gimana tidur akhir-akhir ini?;
- Hal yang buat kamu khawatir.

### Keluar dan hapus data

- `Keluar dari akun` mengakhiri sesi FocusBuddy pada perangkat tersebut.
- `Hapus semua data` menghapus state aplikasi setelah konfirmasi.

Keduanya adalah tindakan berbeda. Keluar tidak sama dengan menghapus seluruh data.

## 17. Langganan KALEM

Halaman langganan memakai istilah `KALEM Freemium`. Tombol upgrade menampilkan harga demo `IDR 29.000/Bulan`.

Checkout hanya simulasi presentasi:

- kartu demo: `0000 0000 0000 0000`, lalu isi slot MM/YY dan CVC demo;
- GoPay demo: `081234567890`;
- centang persetujuan bahwa pembayaran tidak diproses sungguhan.

Jangan memasukkan data pembayaran asli. Tidak ada transaksi, OTP, atau penagihan nyata.

## 18. Data, privasi, dan keamanan

- Data dipisahkan berdasarkan akun Google yang login.
- Supabase RLS membatasi row agar hanya dapat diakses pemiliknya.
- Cache runtime juga dipisahkan per pengguna dan per sesi browser.
- API key dan secret tidak boleh dimasukkan ke form aplikasi atau dibagikan ke pengguna lain.
- Cerita, mood, tugas, dan outcome fokus dapat dipakai KALEM untuk personalisasi di dalam produk.

## 19. Pemecahan masalah singkat

### Halaman hanya menampilkan database belum dikonfigurasi

Administrator belum memasang `SUPABASE_URL` atau `SUPABASE_PUBLISHABLE_KEY`.

### Login Google gagal atau berputar

Periksa koneksi, coba refresh, dan pastikan domain/callback telah didaftarkan di Google serta Supabase.

### Microphone tidak bekerja

Izinkan akses microphone pada browser atau sistem operasi. Fitur transkripsi juga memerlukan Gemini atau OpenAI yang sudah dikonfigurasi.

### Tanggal bergeser satu hari

Pastikan aplikasi sudah memakai versi terbaru. Pilihan tanggal diproses sebagai tanggal kalender lokal, bukan timestamp UTC. Laporkan halaman, tanggal yang dipilih, dan tanggal yang tampil jika masalah masih terjadi.

### KALEM tidak menghasilkan pecahan AI

Periksa provider dan koneksi. Aplikasi dapat memakai retrieval atau fallback lokal, tetapi hasil generatif penuh memerlukan API key yang valid.

### Data tidak muncul setelah login ulang

Pastikan akun Google yang dipakai sama. Tunggu sinkronisasi, lalu refresh. Jangan memakai dua akun pada tab yang sama saat melakukan pengujian.

## 20. Ringkasan alur harian

```text
Login
  -> Insight pagi
  -> Check-in mood/energi bila diperlukan
  -> Home memilih satu hal
  -> Fokus 1–30 menit
  -> Outcome tersimpan
  -> Tracker, Mood, Cerita, dan Favorit memperkaya pola KALEM
```

Tujuan FocusBuddy bukan membuat semua hal selesai sekaligus. Tujuannya membantu pengguna menemukan langkah berikutnya yang cukup kecil untuk dimulai.
