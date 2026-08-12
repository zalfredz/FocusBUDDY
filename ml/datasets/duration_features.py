"""Derived Duration v3 records; source CSV stays immutable."""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

from ml.datasets.duration_clean import CleanDurationDataset, CleanDurationRecord, load_clean_duration_dataset
from ml.features.duration_text import EXTRACTOR_VERSION, extract_duration_text_features


ROOT = Path(__file__).resolve().parents[2]
DERIVED_PATH = ROOT / "datasets" / "generated" / "task_duration_features_v3.csv"
DATASET_VERSION = "task-duration-features-v3"
DERIVED_COLUMNS = (
    "row_id",
    "tugas",
    "source_group_id",
    "has_deadline",
    "deadline_days_or_zero",
    "importance",
    "estimated_duration_minutes",
    "quantity_available",
    "quantity_value",
    "unit_type",
    "action_type",
    "task_category",
    "complexity_indicator",
    "complexity_analysis",
    "complexity_research",
    "complexity_revision",
    "complexity_long_form",
    "complexity_completion",
    "complexity_learning",
    "scope_all",
    "scope_multiple",
    "scope_each",
    "scope_complete",
    "n_token",
    "extractor_version",
)


@dataclass(frozen=True)
class DurationFeatureDataset:
    records: tuple[CleanDurationRecord, ...]
    version: str
    source_dataset: CleanDurationDataset
    derived_path: Path
    derived_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derive_duration_feature_records(
    source: CleanDurationDataset | None = None,
) -> tuple[CleanDurationDataset, tuple[CleanDurationRecord, ...]]:
    source = source or load_clean_duration_dataset()
    records = []
    for record in source.records:
        features = extract_duration_text_features(record.task).as_dict()
        records.append(replace(record, structured=features))
    return source, tuple(records)


def write_derived_duration_dataset(path: Path = DERIVED_PATH) -> DurationFeatureDataset:
    source, records = derive_duration_feature_records()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DERIVED_COLUMNS)
        writer.writeheader()
        for record in records:
            row = {
                "row_id": record.row_id,
                "tugas": record.task,
                "source_group_id": record.source_group_id,
                "has_deadline": int(record.has_deadline),
                "deadline_days_or_zero": (
                    record.deadline_days if record.deadline_days is not None else 0.0
                ),
                "importance": record.importance,
                "estimated_duration_minutes": record.estimated_duration_minutes,
                **record.structured,
                "extractor_version": EXTRACTOR_VERSION,
            }
            writer.writerow(row)
    return DurationFeatureDataset(
        records=records,
        version=DATASET_VERSION,
        source_dataset=source,
        derived_path=path,
        derived_sha256=_sha256(path),
    )
