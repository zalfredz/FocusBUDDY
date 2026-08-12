"""Loading dan validasi dataset durasi bersih untuk eksperimen offline."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path(__file__).with_name("task_duration_id_clean_v2.json")
STRUCTURED_FEATURE_COLUMNS = (
    "task_category",
    "action_type",
    "complexity_indicator",
    "n_token",
)


@dataclass(frozen=True)
class CleanDurationRecord:
    row_id: str
    task: str
    raw_due_days: float
    has_deadline: bool
    deadline_days: float | None
    importance: float
    estimated_duration_minutes: float
    source_group_id: str
    structured: dict[str, str]
    audit_texts: dict[str, str]
    data_source: str


@dataclass(frozen=True)
class CleanDurationDataset:
    records: tuple[CleanDurationRecord, ...]
    version: str
    source_path: Path
    sha256: str
    columns: tuple[str, ...]
    validation: dict[str, Any]
    manifest: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return float(ordered[index])


def _distribution(rows: list[dict[str, str]], column: str) -> dict[str, int] | None:
    if column not in rows[0]:
        return None
    counts = Counter((row.get(column) or "").strip() or "<missing>" for row in rows)
    return dict(sorted(counts.items()))


def _parse_flag(value: str, *, row_number: int, column: str) -> bool:
    normalised = value.strip().casefold()
    if normalised in {"1", "true", "yes"}:
        return True
    if normalised in {"0", "false", "no"}:
        return False
    raise ValueError(f"Baris {row_number}: {column} harus boolean/0/1")


def load_clean_duration_dataset(
    manifest_path: Path = DEFAULT_MANIFEST,
) -> CleanDurationDataset:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_path = ROOT / manifest["source_path"]
    if not source_path.exists():
        raise FileNotFoundError(f"Dataset durasi bersih tidak ditemukan: {source_path}")

    actual_hash = _sha256(source_path)
    if actual_hash != manifest["sha256"]:
        raise ValueError("Checksum dataset durasi bersih berubah; buat versi manifest baru")

    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        missing_columns = set(manifest["required_columns"]) - set(columns)
        if missing_columns:
            raise ValueError(f"Kolom dataset durasi bersih hilang: {sorted(missing_columns)}")
        raw_rows = list(reader)

    if len(raw_rows) != int(manifest["row_count"]):
        raise ValueError(
            f"Row count berubah: manifest={manifest['row_count']}, aktual={len(raw_rows)}"
        )

    records: list[CleanDurationRecord] = []
    for row_number, row in enumerate(raw_rows, start=2):
        task = (row["tugas"] or "").strip()
        row_id = (row["row_id"] or "").strip()
        source_group_id = (row["source_group_id"] or "").strip()
        if not task or not row_id or not source_group_id:
            raise ValueError(f"Baris {row_number}: row_id/tugas/source_group_id wajib terisi")
        try:
            raw_due_days = float(row["jatuh_tempo_hari"])
            importance = float(row["tingkat_kepentingan_1_10"])
            estimated_duration = float(row["durasi_menit"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Baris {row_number}: nilai numerik tidak valid") from exc
        has_deadline = _parse_flag(
            row["ada_tenggat"], row_number=row_number, column="ada_tenggat"
        )
        deadline_raw = (row["tenggat_hari"] or "").strip()
        if has_deadline:
            if not deadline_raw:
                raise ValueError(f"Baris {row_number}: deadline aktif tanpa tenggat_hari")
            try:
                deadline_days: float | None = float(deadline_raw)
            except ValueError as exc:
                raise ValueError(f"Baris {row_number}: tenggat_hari tidak valid") from exc
            if deadline_days == -1:
                raise ValueError(f"Baris {row_number}: -1 bukan deadline numerik yang valid")
        else:
            if deadline_raw:
                raise ValueError(
                    f"Baris {row_number}: tanpa deadline tetapi tenggat_hari masih terisi"
                )
            deadline_days = None
        if estimated_duration <= 0 or not math.isfinite(estimated_duration):
            raise ValueError(f"Baris {row_number}: estimasi durasi harus positif")
        if not 1 <= importance <= 10:
            raise ValueError(f"Baris {row_number}: importance harus 1..10")
        structured = {
            column: (row.get(column) or "").strip()
            for column in STRUCTURED_FEATURE_COLUMNS
            if column in columns
        }
        records.append(
            CleanDurationRecord(
                row_id=row_id,
                task=task,
                raw_due_days=raw_due_days,
                has_deadline=has_deadline,
                deadline_days=deadline_days,
                importance=importance,
                estimated_duration_minutes=estimated_duration,
                source_group_id=source_group_id,
                structured=structured,
                audit_texts={
                    column: (row.get(column) or "").strip()
                    for column in ("tugas", "task_en", "tugas_raw", "task_en_raw")
                    if column in columns
                },
                data_source=(row.get("data_source") or "").strip(),
            )
        )

    durations = [record.estimated_duration_minutes for record in records]
    normalised_titles = [_normalise_text(record.task) for record in records]
    row_tuples = [tuple(row.get(column, "") for column in columns) for row in raw_rows]
    group_sizes = Counter(record.source_group_id for record in records)
    validation: dict[str, Any] = {
        "row_count": len(records),
        "columns": list(columns),
        "missing_values": {
            column: sum(not (row.get(column) or "").strip() for row in raw_rows)
            for column in columns
        },
        "duplicate_rows": len(row_tuples) - len(set(row_tuples)),
        "duplicate_title_rows": len(normalised_titles) - len(set(normalised_titles)),
        "duplicate_model_rows": len(records)
        - len(
            {
                (
                    _normalise_text(record.task),
                    record.raw_due_days,
                    record.importance,
                    record.estimated_duration_minutes,
                )
                for record in records
            }
        ),
        "target": {
            "source_column": "durasi_menit",
            "internal_name": "estimated_duration_minutes",
            "meaning": "human_estimated_duration",
            "min": min(durations),
            "median": float(statistics.median(durations)),
            "mean": float(statistics.mean(durations)),
            "standard_deviation": float(statistics.stdev(durations)),
            "p25": _percentile(durations, 0.25),
            "p75": _percentile(durations, 0.75),
            "p95": _percentile(durations, 0.95),
            "max": max(durations),
            "over_300_count": sum(value > 300 for value in durations),
            "over_600_count": sum(value > 600 for value in durations),
            "histogram_minutes": {
                "(0,15]": sum(0 < value <= 15 for value in durations),
                "(15,30]": sum(15 < value <= 30 for value in durations),
                "(30,60]": sum(30 < value <= 60 for value in durations),
                "(60,120]": sum(60 < value <= 120 for value in durations),
                "(120,300]": sum(120 < value <= 300 for value in durations),
                "(300,600]": sum(300 < value <= 600 for value in durations),
                ">600": sum(value > 600 for value in durations),
            },
        },
        "label_review_needed_count": sum(
            _parse_flag(
                row["label_review_needed"],
                row_number=index,
                column="label_review_needed",
            )
            for index, row in enumerate(raw_rows, start=2)
        ),
        "distributions": {
            "ada_tenggat": _distribution(raw_rows, "ada_tenggat"),
            "tenggat_hari": _distribution(raw_rows, "tenggat_hari"),
            "task_category": _distribution(raw_rows, "task_category"),
            "action_type": _distribution(raw_rows, "action_type"),
            "complexity_indicator": _distribution(raw_rows, "complexity_indicator"),
        },
        "source_groups": {
            "count": len(group_sizes),
            "groups_with_multiple_rows": sum(size > 1 for size in group_sizes.values()),
            "rows_in_multirow_groups": sum(size for size in group_sizes.values() if size > 1),
            "max_group_size": max(group_sizes.values()),
        },
        "available_structured_feature_columns": [
            column for column in STRUCTURED_FEATURE_COLUMNS if column in columns
        ],
        "missing_requested_structured_feature_columns": [
            column for column in STRUCTURED_FEATURE_COLUMNS if column not in columns
        ],
    }
    return CleanDurationDataset(
        records=tuple(records),
        version=manifest["dataset_version"],
        source_path=source_path,
        sha256=actual_hash,
        columns=columns,
        validation=validation,
        manifest=manifest,
    )
