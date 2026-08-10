"""MODEL PECAH TUGAS -- "tugas ini mirip yang pernah dipecah, pakai itu aja."

MASALAH YANG DIJAWAB
--------------------
Pecah Tugas satu-satunya fitur yang tiap dipakai NELPON API BERBAYAR. Makin
sering user pakai, makin mahal -- kebalikan dari model lain di paket ini yang
justru makin murah & makin pinter seiring data numpuk.

KENAPA RETRIEVAL, BUKAN MODEL YANG NGARANG SENDIRI
---------------------------------------------------
Ini beda mendasar dari `model_durasi`, dan penting dipahami sebelum ngoprek:

    model_durasi  output ANGKA (menit)   -> regresi, 549 contoh udah cukup
    model_pecah   output KALIMAT         -> butuh fine-tune LLM

RandomForest bisa nebak angka, tapi nggak bisa NGARANG kalimat baru. Bikin
model yang nulis langkah sendiri artinya fine-tune LLM kecil: butuh GPU,
ribuan contoh, dan infrastruktur latih yang di luar skala project ini.

Jalan yang realistis: JANGAN ngarang, PAKAI ULANG. Tiap pecahan sukses
disimpen (`storage.add_decompose_record`), dan tugas baru yang MIRIP mungut
hasil lama itu. Nol panggilan API, dan kualitasnya persis sebagus pecahan
aslinya -- karena emang itu barangnya.

Konsekuensinya jujur: ini cuma nolong buat tugas YANG POLANYA BERULANG
(quiz mingguan, laporan bulanan, tugas kuliah yang bentuknya sama). Tugas
yang bener-bener baru tetap butuh AI, dan itu wajar.

CARA NGUKUR MIRIP
-----------------
TF-IDF n-gram HURUF (char_wb 3-5), sama persis kayak `model_durasi` -- dan
alasannya sama: judul tugas pendek & penuh variasi bentuk ("bikin"/"buat"/
"ngerjain"), n-gram huruf nangkep akar katanya tanpa perlu stemmer bahasa
Indonesia. Deskripsi ikut dicocokin (dibobot lebih kecil dari judul), karena
dua tugas berjudul sama bisa isinya beda total.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

# Ambang kemiripan buat mungut hasil lama. DIUKUR, bukan ditebak -- lihat
# `tools/tes_manual_kalem.py` bagian "pecah" buat ngecek ulang kalau angkanya
# mau diubah.
#
# Sengaja TINGGI (0.72). Salah mungut itu ruginya besar & senyap: user dapet
# langkah yang nggak nyambung sama tugasnya, dan nggak ada yang ngasih tau
# itu hasil daur ulang. Kelewatan mungut ruginya cuma satu panggilan API.
AMBANG_MIRIP = 0.72

# Deskripsi dibobot lebih kecil dari judul pas dicocokin: judul itu identitas
# tugas, deskripsi itu konteks yang bisa beda-beda panjangnya. Tanpa bobot,
# deskripsi panjang bakal ngedominasi skor kemiripan.
BOBOT_DESKRIPSI = 0.6

# Minimal catatan sebelum retrieval dicoba. SATU, bukan lebih -- dan ini
# hasil koreksi dari uji, bukan tebakan awal:
#
# Versi pertama nyetel 3 dengan alasan "TF-IDF butuh beberapa dokumen biar
# IDF-nya berarti". Kedengeran masuk akal, TAPI diuji ternyata itu MEMATIKAN
# kasus yang paling berharga: tugas yang SAMA diulang tiap minggu (quiz
# mingguan, laporan bulanan). `add_decompose_record` nge-dedupe judul+
# deskripsi yang sama, jadi ngulang tugas yang sama nggak pernah nambah
# jumlah catatan -- mentok di 1 selamanya, retrieval nggak pernah nyala.
#
# Yang beneran njaga dari salah-pungut itu AMBANG_MIRIP, bukan jumlah
# catatan: diukur, tugas nggak nyambung dapet skor 0.01-0.23, jauh di bawah
# 0.72. Jumlah dokumen cuma bikin IDF lebih kasar, nggak bikin salah cocok.
MIN_RECORDS = 1

# Bahasa yang dipakai app ini. Retrieval cuma mungut pola SEBAHASA -- lihat
# catatan di `cari()`. Kalau nanti app-nya multi-bahasa, ini yang diganti
# jadi ikut setelan user, bukan konstanta.
BAHASA_UTAMA = "id"
DATASET_BAWAAN = Path(__file__).resolve().parents[2] / "DATASET" / "focusbuddy_dekomposisi_id.csv"


@dataclass
class HasilPecah:
    ketemu: bool
    langkah: list[str]
    skor: float = 0.0
    dari_judul: str = ""        # tugas lama yang dipungut
    sumber_asli: str = ""       # "ai" | "manual" -- asal pecahan lama itu
    n_dibanding: int = 0


def _teks(judul: str, deskripsi: str) -> str:
    """Gabung judul+deskripsi jadi satu dokumen buat dicocokin.

    Judul diulang biar bobotnya lebih besar dari deskripsi -- lihat catatan
    di BOBOT_DESKRIPSI. Cara paling sederhana yang nggak butuh dua vectorizer
    terpisah.
    """
    judul = (judul or "").strip()
    deskripsi = (deskripsi or "").strip()
    if not deskripsi:
        return judul
    # Judul 2x + deskripsi 1x -> rasio bobot ~2:1 (mendekati 1/BOBOT_DESKRIPSI).
    return f"{judul} {judul} {deskripsi}"


@lru_cache(maxsize=1)
def _pola_bawaan() -> tuple[dict, ...]:
    """Pola Indonesia siap pakai untuk user baru, tanpa menulis storage.

    Dataset bukan riwayat personal. Menyuntikkannya saat retrieval menjaga
    fresh install tetap offline-first sekaligus menghindari duplikasi 212
    record ke setiap `data.json` pengguna.
    """
    if not DATASET_BAWAAN.exists():
        return ()
    try:
        with DATASET_BAWAAN.open(encoding="utf-8-sig", newline="") as handle:
            return tuple(
                {
                    "title": (row.get("judul") or "").strip(),
                    "description": (row.get("deskripsi") or "").strip(),
                    "steps": [s.strip() for s in (row.get("langkah") or "").split("|") if s.strip()],
                    "language": (row.get("language") or BAHASA_UTAMA).strip(),
                    "source": "dataset",
                }
                for row in csv.DictReader(handle)
                if (row.get("judul") or "").strip() and (row.get("langkah") or "").strip()
            )
    except OSError:
        return ()


def _gabung_records(user_records: list[dict]) -> list[dict]:
    """Pola personal menang atas dataset bila identitas tugasnya sama."""
    by_identity = {
        (r.get("title", ""), r.get("description", ""), r.get("language", BAHASA_UTAMA)): dict(r)
        for r in _pola_bawaan()
    }
    for record in user_records:
        key = (record.get("title", ""), record.get("description", ""),
               record.get("language", BAHASA_UTAMA))
        by_identity[key] = record
    return list(by_identity.values())


def cari(
    judul: str,
    deskripsi: str = "",
    records: Optional[list[dict]] = None,
    ambang: float = AMBANG_MIRIP,
    bahasa: str = BAHASA_UTAMA,
) -> HasilPecah:
    """Cari pecahan lama yang cukup mirip. Return HasilPecah(ketemu=False)
    kalau nggak ada yang lewat ambang -- pemanggil lanjut ke AI.

    `records` dioper eksplisit biar fungsi ini murni & gampang dites (pola
    yang sama kayak model lain di paket ini). None = baca storage.

    `bahasa` nyaring kolam pencarian. Catatan TANPA penanda bahasa ikut
    kepakai -- itu pecahan hasil user sendiri, yang emang bahasanya ngikut
    user. Yang disaring cuma pola dataset yang bahasanya JELAS beda: user
    Indonesia nulis "beresin kamar" nggak boleh dapet langkah berbahasa
    Inggris cuma gara-gara maknanya kebetulan deket.
    """
    if records is None:
        from app import storage

        records = _gabung_records(storage.get_decompose_records())

    kandidat = [
        r for r in (records or [])
        if r.get("steps") and r.get("title")
        and r.get("language", bahasa) == bahasa
    ]
    if len(kandidat) < MIN_RECORDS:
        return HasilPecah(ketemu=False, langkah=[], n_dibanding=len(kandidat))

    if not _teks(judul, deskripsi).strip():
        return HasilPecah(ketemu=False, langkah=[], n_dibanding=len(kandidat))

    # DUA perbandingan, diambil yang tertinggi: judul-saja, dan judul+deskripsi.
    #
    # Kenapa nggak cukup satu (judul+deskripsi doang) -- ini hasil uji, bukan
    # teori: catatan lama yang deskripsinya panjang bikin skor JATUH pas
    # dicocokin sama tugas baru yang deskripsinya kosong, walaupun judulnya
    # sama persis. Terukur 0.63-0.69, nyempil DI BAWAH ambang 0.72 -- jadi
    # "Quiz Kalkulus 1" nggak kena sama catatan "Quiz Kalkulus 1" sendiri
    # cuma gara-gara yang lama punya deskripsi.
    #
    # Nurunin ambang biar kena itu solusi yang salah: 0.63 udah kedeketan
    # sama derau. Yang bener bandingin di dua tingkat, biar judul yang sama
    # persis tetap kebaca sebagai sama persis.
    def _skor(korpus: list[str], kueri: str) -> np.ndarray:
        try:
            vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
            X = vec.fit_transform(korpus + [kueri])
        except ValueError:
            # Korpus terlalu miskin buat bikin vocabulary (mis. semua string
            # 1-2 huruf). Bukan error yang perlu diteriakin -- anggap nol.
            return np.zeros(len(korpus))
        # Baris terakhir = kueri. TF-IDF sklearn udah L2-normalized, jadi dot
        # product = cosine similarity, nggak perlu bagi norma lagi.
        return (X[:-1] @ X[-1].T).toarray().ravel()

    skor_judul = _skor([r.get("title", "") for r in kandidat], judul or "")
    skor_penuh = _skor(
        [_teks(r.get("title", ""), r.get("description", "")) for r in kandidat],
        _teks(judul, deskripsi),
    )
    skor = np.maximum(skor_judul, skor_penuh)
    idx = int(np.argmax(skor))
    tertinggi = float(skor[idx])

    if tertinggi < ambang:
        return HasilPecah(
            ketemu=False, langkah=[], skor=tertinggi, n_dibanding=len(kandidat)
        )

    cocok = kandidat[idx]
    return HasilPecah(
        ketemu=True,
        langkah=list(cocok["steps"]),
        skor=tertinggi,
        dari_judul=cocok.get("title", ""),
        sumber_asli=cocok.get("source", ""),
        n_dibanding=len(kandidat),
    )


def status() -> dict:
    """Ringkasan buat halaman Pengaturan & tes."""
    from app import storage

    records = storage.get_decompose_records()
    n_bawaan = len(_pola_bawaan())
    dari_ai = sum(1 for r in records if r.get("source") == "ai")
    return {
        "n_tersimpan": len(records),
        "n_bawaan": n_bawaan,
        "dari_ai": dari_ai,
        "dari_manual": len(records) - dari_ai,
        "siap": (len(records) + n_bawaan) >= MIN_RECORDS,
        "min_records": MIN_RECORDS,
    }
