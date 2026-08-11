"""Retrieval pecahan tugas dengan ambang konservatif untuk mencegah salah pungut."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

AMBANG_MIRIP = 0.72

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


def _teks(judul: str, deskripsi: str) -> str:
    judul = (judul or "").strip()
    deskripsi = (deskripsi or "").strip()
    if not deskripsi:
        return judul
    return f"{judul} {judul} {deskripsi}"


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
                    "language": (row.get("language") or BAHASA_UTAMA).strip(),
                    "source": "dataset",
                }
                for row in csv.DictReader(handle)
                if (row.get("judul") or "").strip() and (row.get("langkah") or "").strip()
            )
    except OSError:
        return ()


def _gabung_records(user_records: list[dict]) -> list[dict]:
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

    def _skor(korpus: list[str], kueri: str) -> np.ndarray:
        try:
            vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
            X = vec.fit_transform(korpus + [kueri])
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
