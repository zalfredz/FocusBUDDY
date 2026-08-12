"""Coverage dan manual targeted audit untuk fitur teks Duration v3."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

from ml.datasets.duration_clean import CleanDurationRecord
from ml.features.duration_text import MISSING_CATEGORY, feature_rules_metadata


DEFAULT_AUDIT = Path(__file__).with_name("duration_feature_audit_v3.json")
FEATURE_GROUP_FIELDS = {
    "quantity": ("quantity_value",),
    "unit_type": ("unit_type",),
    "action_type": ("action_type",),
    "task_category": ("task_category",),
    "complexity_indicator": (
        "complexity_analysis",
        "complexity_research",
        "complexity_revision",
        "complexity_long_form",
        "complexity_completion",
        "complexity_learning",
    ),
    "scope_indicators": (
        "scope_all",
        "scope_multiple",
        "scope_each",
        "scope_complete",
    ),
    "n_token": ("n_token",),
}


def _actual_value(record: CleanDurationRecord, field: str) -> Any:
    if field == "quantity_value":
        if int(record.structured["quantity_available"]) == 0:
            return None
        return float(record.structured[field])
    value = record.structured[field]
    if field.startswith(("complexity_", "scope_", "n_token")):
        return int(float(value))
    return None if value == MISSING_CATEGORY else value


def _coverage(records: Sequence[CleanDurationRecord], feature: str) -> dict[str, Any]:
    total = len(records)
    if feature == "quantity":
        values = [
            float(record.structured["quantity_value"])
            for record in records
            if int(record.structured["quantity_available"])
        ]
        examples = [
            {"task": record.task, "value": float(record.structured["quantity_value"])}
            for record in records
            if int(record.structured["quantity_available"])
        ][:8]
    elif feature in {"unit_type", "action_type"}:
        values = [
            record.structured[feature]
            for record in records
            if record.structured[feature] != MISSING_CATEGORY
        ]
        examples = [
            {"task": record.task, "value": record.structured[feature]}
            for record in records
            if record.structured[feature] != MISSING_CATEGORY
        ][:8]
    elif feature == "task_category":
        values = [
            record.structured[feature]
            for record in records
            if record.structured[feature] != "lainnya"
        ]
        examples = [
            {"task": record.task, "value": record.structured[feature]}
            for record in records
            if record.structured[feature] != "lainnya"
        ][:8]
    elif feature == "complexity_indicator":
        values = [
            record.structured[feature]
            for record in records
            if record.structured[feature] != MISSING_CATEGORY
        ]
        examples = [
            {"task": record.task, "value": record.structured[feature]}
            for record in records
            if record.structured[feature] != MISSING_CATEGORY
        ][:8]
    elif feature == "scope_indicators":
        fields = FEATURE_GROUP_FIELDS[feature]
        values = [
            "|".join(field for field in fields if int(record.structured[field]))
            for record in records
            if any(int(record.structured[field]) for field in fields)
        ]
        examples = [
            {"task": record.task, "value": value}
            for record, value in zip(
                [
                    record
                    for record in records
                    if any(int(record.structured[field]) for field in fields)
                ],
                values,
            )
        ][:8]
    else:
        values = [int(record.structured["n_token"]) for record in records]
        examples = [
            {"task": record.task, "value": int(record.structured["n_token"])}
            for record in records[:8]
        ]
    count = len(values)
    return {
        "coverage_count": count,
        "coverage_percent": count / total * 100.0,
        "missing_count": total - count,
        "missing_percent": (total - count) / total * 100.0,
        "unique_values": sorted(set(values), key=str),
        "value_distribution": dict(sorted(Counter(values).items(), key=lambda item: str(item[0]))),
        "examples": examples,
    }


def evaluate_duration_feature_quality(
    records: Sequence[CleanDurationRecord], audit_path: Path = DEFAULT_AUDIT
) -> dict[str, Any]:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    by_task = {record.task: record for record in records}
    field_to_group = {
        field: group for group, fields in FEATURE_GROUP_FIELDS.items() for field in fields
    }
    findings: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "audited_assertions": 0,
            "correct": 0,
            "false_positives": [],
            "false_negatives": [],
            "value_errors": [],
        }
    )
    for case in audit["cases"]:
        task = case["task"]
        if task not in by_task:
            raise ValueError(f"Manual feature audit case tidak ditemukan: {task}")
        record = by_task[task]
        for field, expected in case["expected"].items():
            group = field_to_group[field]
            finding = findings[group]
            finding["audited_assertions"] += 1
            actual = _actual_value(record, field)
            if actual == expected:
                finding["correct"] += 1
            elif expected is None and actual is not None:
                finding["false_positives"].append(
                    {"task": task, "field": field, "expected": expected, "actual": actual}
                )
            elif expected is not None and actual is None:
                finding["false_negatives"].append(
                    {"task": task, "field": field, "expected": expected, "actual": actual}
                )
            else:
                finding["value_errors"].append(
                    {"task": task, "field": field, "expected": expected, "actual": actual}
                )

    feature_reports: dict[str, Any] = {}
    for feature in FEATURE_GROUP_FIELDS:
        quality = findings[feature]
        assertions = quality["audited_assertions"]
        errors = (
            len(quality["false_positives"])
            + len(quality["false_negatives"])
            + len(quality["value_errors"])
        )
        accuracy = quality["correct"] / assertions if assertions else None
        # n_token is defined algorithmically; the other groups need targeted manual evidence.
        passes = feature == "n_token" or (
            assertions >= 5 and accuracy is not None and accuracy >= 0.85
        )
        feature_reports[feature] = {
            **_coverage(records, feature),
            "manual_audit": {
                **quality,
                "accuracy": accuracy,
                "error_count": errors,
                "scope": audit["review_scope"],
            },
            "passes_reliability_gate": passes,
            "gate": "targeted audit accuracy >=85% with >=5 assertions",
        }
    return {
        "audit_version": audit["audit_version"],
        "target_or_duration_used": audit["target_or_duration_used"],
        "rules": feature_rules_metadata(),
        "features": feature_reports,
        "reliable_feature_groups": [
            feature
            for feature, report in feature_reports.items()
            if report["passes_reliability_gate"]
        ],
    }
