"""Validasi dan loading dataset Duration tanpa bergantung pada runtime app."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path(__file__).with_name("task_duration_id_v1.json")


@dataclass(frozen=True)
class DurationRecord:
    task: str
    due_days: float
    importance: float
    duration_minutes: float


@dataclass(frozen=True)
class DurationDataset:
    records: tuple[DurationRecord, ...]
    version: str
    source_path: Path
    sha256: str
    validation: dict[str, Any]
    manifest: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return float(ordered[index])


def load_duration_dataset(manifest_path: Path = DEFAULT_MANIFEST) -> DurationDataset:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_path = ROOT / manifest["source_path"]
    if not source_path.exists():
        raise FileNotFoundError(f"Dataset Duration tidak ditemukan: {source_path}")

    actual_hash = _sha256(source_path)
    if actual_hash != manifest["sha256"]:
        raise ValueError(
            "Checksum dataset Duration berubah. Buat versi manifest baru sebelum training."
        )

    required = set(manifest["required_columns"])
    records: list[DurationRecord] = []
    titles: list[str] = []
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Kolom dataset Duration hilang: {sorted(missing)}")
        for row_number, row in enumerate(reader, start=2):
            task = (row.get("tugas") or "").strip()
            try:
                due_days = float(row["jatuh_tempo_hari"])
                importance = float(row["tingkat_kepentingan_1_10"])
                duration_minutes = float(row["durasi_jam"]) * 60.0
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Baris {row_number} tidak valid: {exc}") from exc
            if not task:
                raise ValueError(f"Baris {row_number}: judul tugas kosong")
            if duration_minutes <= 0:
                raise ValueError(f"Baris {row_number}: durasi harus positif")
            if not 1 <= importance <= 10:
                raise ValueError(f"Baris {row_number}: importance harus 1..10")
            records.append(DurationRecord(task, due_days, importance, duration_minutes))
            titles.append(task.casefold())

    if len(records) != int(manifest["row_count"]):
        raise ValueError(
            f"Row count berubah: manifest={manifest['row_count']}, aktual={len(records)}"
        )

    durations = [record.duration_minutes for record in records]
    duplicate_count = len(titles) - len(set(titles))
    validation = {
        "row_count": len(records),
        "duplicate_title_rows": duplicate_count,
        "duration_minutes": {
            "min": min(durations),
            "p25": _percentile(durations, 0.25),
            "median": _percentile(durations, 0.50),
            "p75": _percentile(durations, 0.75),
            "p95": _percentile(durations, 0.95),
            "max": max(durations),
            "over_300_count": sum(value > 300 for value in durations),
        },
    }
    return DurationDataset(
        records=tuple(records),
        version=manifest["dataset_version"],
        source_path=source_path,
        sha256=actual_hash,
        validation=validation,
        manifest=manifest,
    )
