"""Retrieval pola pecah tugas Indonesia dengan fallback saat tidak yakin."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer, TfidfVectorizer

from app.runtime_policy import runtime_training_allowed

AMBANG_MIRIP = 0.72
AMBANG_SELISIH = 0.03

BOBOT_DESKRIPSI = 0.6

MIN_RECORDS = 1

BAHASA_UTAMA = "id"
DATASET_BAWAAN = Path(__file__).resolve().parent.parent / "datasets" / "task_decomposition_id.csv"


@dataclass
class HasilPecah:
    ketemu: bool
    langkah: list[str]
    skor: float = 0.0
    dari_judul: str = ""
    sumber_asli: str = ""
    n_dibanding: int = 0
    alasan: str = ""
    skor_kedua: float = 0.0


def _teks(judul: str, deskripsi: str) -> str:
    judul = (judul or "").strip()
    deskripsi = (deskripsi or "").strip()
    if not deskripsi:
        return judul
    return f"{judul} {judul} {deskripsi}"


def _kode_bahasa(value: object) -> str:
    """Normalize an explicit language code; unknown values stay unsupported."""
    raw = str(value or "").strip().casefold().replace("_", "-")
    return raw.split("-", 1)[0]


def _pola_indonesia(record: dict) -> bool:
    return bool(
        record.get("title")
        and record.get("steps")
        and _kode_bahasa(record.get("language")) == BAHASA_UTAMA
    )


@lru_cache(maxsize=1)
def _pola_bawaan() -> tuple[dict, ...]:
    if not DATASET_BAWAAN.exists():
        return ()
    try:
        with DATASET_BAWAAN.open(encoding="utf-8-sig", newline="") as handle:
            return tuple(
                {
                    "title": (row.get("judul") or "").strip(),
                    "description": (row.get("deskripsi") or "").strip(),
                    "steps": [s.strip() for s in (row.get("langkah") or "").split("|") if s.strip()],
                    "language": _kode_bahasa(row.get("language")),
                    "source": "dataset",
                }
                for row in csv.DictReader(handle)
                if (row.get("judul") or "").strip()
                and (row.get("langkah") or "").strip()
                and _kode_bahasa(row.get("language")) == BAHASA_UTAMA
            )
    except OSError:
        return ()


def _gabung_records(user_records: list[dict]) -> list[dict]:
    by_identity = {
        (r.get("title", ""), r.get("description", ""), BAHASA_UTAMA): dict(r)
        for r in _pola_bawaan()
    }
    for record in user_records:
        if not _pola_indonesia(record):
            continue
        key = (record.get("title", ""), record.get("description", ""), BAHASA_UTAMA)
        by_identity[key] = dict(record, language=BAHASA_UTAMA)
    return list(by_identity.values())


def cari(
    judul: str,
    deskripsi: str = "",
    records: Optional[list[dict]] = None,
    ambang: float = AMBANG_MIRIP,
    bahasa: str = BAHASA_UTAMA,
) -> HasilPecah:
    bahasa = _kode_bahasa(bahasa)
    if bahasa != BAHASA_UTAMA:
        return HasilPecah(
            ketemu=False,
            langkah=[],
            alasan="bahasa_retrieval_tidak_didukung",
        )
    if records is None:
        from app import storage

        records = _gabung_records(storage.get_decompose_records())

    kandidat = [
        r for r in (records or [])
        if _pola_indonesia(r)
    ]
    if len(kandidat) < MIN_RECORDS:
        return HasilPecah(
            ketemu=False,
            langkah=[],
            n_dibanding=len(kandidat),
            alasan="corpus_indonesia_kosong",
        )

    if not _teks(judul, deskripsi).strip():
        return HasilPecah(
            ketemu=False,
            langkah=[],
            n_dibanding=len(kandidat),
            alasan="query_kosong",
        )

    def _skor(korpus: list[str], kueri: str) -> np.ndarray:
        try:
            if runtime_training_allowed():
                vec = TfidfVectorizer(
                    analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True
                )
                X = vec.fit_transform(korpus + [kueri])
            else:
                vec = HashingVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    n_features=2**14,
                    alternate_sign=False,
                    norm="l2",
                )
                X = vec.transform(korpus + [kueri])
        except ValueError:
            return np.zeros(len(korpus))
        return (X[:-1] @ X[-1].T).toarray().ravel()

    skor_judul = _skor([r.get("title", "") for r in kandidat], judul or "")
    skor_penuh = _skor(
        [_teks(r.get("title", ""), r.get("description", "")) for r in kandidat],
        _teks(judul, deskripsi),
    )
    skor = np.maximum(skor_judul, skor_penuh)
    idx = int(np.argmax(skor))
    tertinggi = float(skor[idx])
    urut = np.sort(skor)
    kedua = float(urut[-2]) if len(urut) > 1 else 0.0

    if tertinggi < ambang:
        return HasilPecah(
            ketemu=False,
            langkah=[],
            skor=tertinggi,
            skor_kedua=kedua,
            n_dibanding=len(kandidat),
            alasan="confidence_di_bawah_ambang",
        )
    if tertinggi - kedua < AMBANG_SELISIH:
        return HasilPecah(
            ketemu=False,
            langkah=[],
            skor=tertinggi,
            skor_kedua=kedua,
            n_dibanding=len(kandidat),
            alasan="dua_pola_terlalu_ambigu",
        )

    cocok = kandidat[idx]
    return HasilPecah(
        ketemu=True,
        langkah=list(cocok["steps"]),
        skor=tertinggi,
        dari_judul=cocok.get("title", ""),
        sumber_asli=cocok.get("source", ""),
        n_dibanding=len(kandidat),
        alasan="retrieval_confident",
        skor_kedua=kedua,
    )


def status() -> dict:
    from app import storage

    try:
        records = storage.get_decompose_records()
    except OSError:
        # Status is diagnostic only; unavailable per-user storage must not make
        # the static Indonesian corpus unavailable.
        records = []
    n_bawaan = len(_pola_bawaan())
    records_id = [r for r in records if _pola_indonesia(r)]
    dari_ai = sum(1 for r in records_id if r.get("source") == "ai")
    return {
        "n_tersimpan": len(records_id),
        "n_diabaikan_bukan_indonesia": len(records) - len(records_id),
        "n_bawaan": n_bawaan,
        "dari_ai": dari_ai,
        "dari_manual": len(records_id) - dari_ai,
        "siap": (len(records_id) + n_bawaan) >= MIN_RECORDS,
        "min_records": MIN_RECORDS,
        "ambang_mirip": AMBANG_MIRIP,
        "ambang_selisih": AMBANG_SELISIH,
    }
