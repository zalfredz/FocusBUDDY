"""Validasi dataset dekomposisi tanpa melatih atau mengubah retrieval produksi."""
from __future__ import annotations

import csv
import hashlib
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "datasets" / "task_decomposition_id_v2.csv"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", value.casefold()).split())


def _existing_first_step_check(rows: list[dict[str, str]]) -> dict[str, Any]:
    try:
        from tests.test_low_friction import SKOR_MANUAL
    except ImportError:
        return {"available": False, "reason": "Existing manual rubric could not be imported"}
    by_title = {
        row["judul"].strip(): next(
            (step.strip() for step in row["langkah"].split("|") if step.strip()), ""
        )
        for row in rows
    }
    stale = [
        title
        for title, expected_step, _, _ in SKOR_MANUAL
        if by_title.get(title) != expected_step
    ]
    if stale:
        return {
            "available": True,
            "valid_for_dataset": False,
            "evaluated_patterns": len(SKOR_MANUAL),
            "stale_titles": stale,
            "note": "Scores were not reused because the reviewed first steps changed.",
        }
    scores = [score for _, _, score, _ in SKOR_MANUAL]
    return {
        "available": True,
        "valid_for_dataset": True,
        "method": "existing manually scored 0..2 low-friction rubric",
        "evaluated_patterns": len(scores),
        "mean_score": float(statistics.mean(scores)),
        "score_distribution": dict(sorted(Counter(scores).items())),
        "target_mean": 1.8,
        "passed_existing_target": statistics.mean(scores) >= 1.8,
    }


def validate_decomposition_dataset(path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        rows = list(reader)
    required = {"judul", "langkah", "kategori", "source_group_id", "quality_flag"}
    missing_columns = required - set(columns)
    if missing_columns:
        raise ValueError(f"Kolom dataset dekomposisi hilang: {sorted(missing_columns)}")

    normalised_titles = [_normalise(row["judul"]) for row in rows]
    full_rows = [tuple(row.get(column, "") for column in columns) for row in rows]
    step_counts: list[int] = []
    empty_steps = 0
    count_mismatches = 0
    for row in rows:
        steps = [step.strip() for step in row["langkah"].split("|") if step.strip()]
        step_counts.append(len(steps))
        empty_steps += not steps
        try:
            declared = int(float(row.get("jumlah_langkah") or "0"))
        except ValueError:
            declared = -1
        count_mismatches += declared != len(steps)

    group_sizes = Counter(row["source_group_id"].strip() for row in rows)
    translated = sum("translated" in (row.get("source_dataset") or "").casefold() for row in rows)
    augmented = sum((row.get("data_source") or "").casefold() not in {"", "original"} for row in rows)
    contaminated = [
        row["judul"]
        for row in rows
        if "kontaminasi_inggris" in (row.get("quality_flag") or "").casefold()
    ]
    independent_indonesian_eval = ROOT / "datasets" / "task_decomposition_eval_id.csv"
    excluded_eval = ROOT / "datasets" / "task_decomposition_queries.csv"
    retrieval_benchmark = {
        "run": False,
        "reason": (
            "This historical v2 dataset audit does not execute retrieval. Current "
            "production retrieval is evaluated separately with the frozen Indonesian "
            "task_decomposition_eval_id.csv benchmark."
        ),
        "production_pattern_count": len(rows),
        "indonesian_evaluation_dataset": str(independent_indonesian_eval.relative_to(ROOT)),
        "excluded_old_english_benchmark": str(excluded_eval.relative_to(ROOT)),
    }
    return {
        "source_path": str(path.relative_to(ROOT)),
        "sha256": _sha256(path),
        "total_patterns": len(rows),
        "columns": list(columns),
        "categories": dict(sorted(Counter(row["kategori"].strip() for row in rows).items())),
        "duplicate_rows": len(full_rows) - len(set(full_rows)),
        "duplicate_titles": len(normalised_titles) - len(set(normalised_titles)),
        "semantic_duplicates": {
            "count": None,
            "reason": "No independent semantic-duplicate detector exists in the repository.",
            "source_group_related_row_excess": len(rows) - len(group_sizes),
            "groups_with_multiple_rows": sum(size > 1 for size in group_sizes.values()),
            "note": "Source-group relationships are reported, not mislabeled as semantic matches.",
        },
        "translated_rows": translated,
        "augmented_rows": augmented,
        "source_groups": {
            "count": len(group_sizes),
            "groups_with_multiple_rows": sum(size > 1 for size in group_sizes.values()),
            "max_group_size": max(group_sizes.values()),
        },
        "steps_per_pattern": {
            "min": min(step_counts),
            "median": float(statistics.median(step_counts)),
            "mean": float(statistics.mean(step_counts)),
            "max": max(step_counts),
            "distribution": dict(sorted(Counter(step_counts).items())),
        },
        "english_contamination": {
            "flagged_count": len(contaminated),
            "flagged_titles": contaminated,
            "method": "existing quality_flag=kontaminasi_inggris:review",
        },
        "missing_or_empty_steps": empty_steps,
        "declared_step_count_mismatches": count_mismatches,
        "first_step_quality": _existing_first_step_check(rows),
        "retrieval_benchmark": retrieval_benchmark,
    }
