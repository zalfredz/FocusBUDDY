"""PII-safe offline audit command for exported Supabase FocusBuddy states."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from ml.datasets.user_outcomes import build_training_dataset, join_supabase_state_rows
from ml.evaluation.real_user_readiness import (
    DEFAULT_POLICY,
    evaluate_readiness,
    policy_document,
)
from ml.evaluation.user_outcomes import (
    REAL_USER,
    is_synthetic_outcome,
    outcome_provenance,
    validate_outcome_records,
)


AUDIT_VERSION = "duration-real-user-audit-v1"


def _state(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def load_export(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = next(
            (
                payload[key]
                for key in ("rows", "records", "data")
                if isinstance(payload.get(key), list)
            ),
            None,
        )
        if rows is None and "user_id" in payload and "state" in payload:
            rows = [payload]
    else:
        rows = None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(
            "Export must be a list of {user_id, state} rows or an object containing rows"
        )
    return rows


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _numeric_distribution(values: Iterable[float]) -> dict[str, Any]:
    numbers = [float(value) for value in values]
    if not numbers:
        return {
            "count": 0,
            "min": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "max": None,
            "mean": None,
        }
    return {
        "count": len(numbers),
        "min": min(numbers),
        "p25": _percentile(numbers, 0.25),
        "median": _percentile(numbers, 0.50),
        "p75": _percentile(numbers, 0.75),
        "p90": _percentile(numbers, 0.90),
        "p95": _percentile(numbers, 0.95),
        "max": max(numbers),
        "mean": statistics.mean(numbers),
    }


def _rejection_counts(validated: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in validated:
        if row.get("data_quality_status") == "valid":
            continue
        for reason in str(row.get("data_quality_reason") or "unknown").split(";"):
            if reason:
                counts[reason] += 1
    return dict(sorted(counts.items()))


def _task_occurrence_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("user_id") or ""),
        str(row.get("task_id") or ""),
        str(row.get("occurrence_date") or ""),
    )


def audit_export_rows(
    cloud_rows: list[dict[str, Any]], *, source_sha256: str = ""
) -> dict[str, Any]:
    joined = join_supabase_state_rows(cloud_rows)
    validated = validate_outcome_records(joined)
    dataset = build_training_dataset(cloud_rows)
    candidates = [row for row in dataset.records if row.get("training_eligible")]

    user_ids = {
        str(row.get("user_id") or "") for row in cloud_rows if row.get("user_id")
    }
    task_keys: set[tuple[str, str]] = set()
    tasks_by_user: Counter[str] = Counter()
    for envelope in cloud_rows:
        user_id = str(envelope.get("user_id") or "")
        for task in _state(envelope.get("state")).get("tasks", []):
            if isinstance(task, dict) and task.get("id"):
                task_keys.add((user_id, str(task["id"])))
                tasks_by_user[user_id] += 1

    quality = Counter(
        str(row.get("data_quality_status") or "unknown") for row in validated
    )
    real_session_rows = [
        row for row in joined if outcome_provenance(row) == REAL_USER
    ]
    real_validated_rows = [
        row for row in validated if outcome_provenance(row) == REAL_USER
    ]
    real_quality = Counter(
        str(row.get("data_quality_status") or "unknown")
        for row in real_validated_rows
    )
    real_user_ids = {
        str(row.get("user_id") or "")
        for row in real_session_rows
        if row.get("user_id")
    }
    completed_keys = {
        _task_occurrence_key(row)
        for row in validated
        if row.get("task_completed") is True and row.get("outcome") == "completed"
    }
    real_completed_keys = {
        _task_occurrence_key(row)
        for row in validated
        if row.get("task_completed") is True
        and row.get("outcome") == "completed"
        and not is_synthetic_outcome(row)
    }
    model_versions = Counter(
        str(row.get("prediction_model_version") or "<missing>") for row in joined
    )
    occurrences_by_user = Counter(str(row["user_id"]) for row in candidates)
    real_completed_by_user = Counter(key[0] for key in real_completed_keys)
    active_days_by_user: dict[str, set[str]] = {}
    categories_by_user: dict[str, set[str]] = {}
    for row in candidates:
        user_id = str(row["user_id"])
        ended_date = str(row.get("ended_at") or "")[:10]
        if ended_date:
            active_days_by_user.setdefault(user_id, set()).add(ended_date)
        category = str(row.get("category") or "").strip()
        if category:
            categories_by_user.setdefault(user_id, set()).add(category)

    candidate_users = {
        user_id
        for user_id, count in occurrences_by_user.items()
        if count >= DEFAULT_POLICY.personalization_min_occurrences
        and len(active_days_by_user.get(user_id, set()))
        >= DEFAULT_POLICY.personalization_min_active_days
        and len(categories_by_user.get(user_id, set()))
        >= DEFAULT_POLICY.personalization_min_categories
    }
    durations = [float(row["actual_active_duration_minutes"]) for row in candidates]
    duration_buckets = {
        "0_to_15": sum(0 < value <= 15 for value in durations),
        "16_to_30": sum(15 < value <= 30 for value in durations),
        "31_to_60": sum(30 < value <= 60 for value in durations),
        "61_to_120": sum(60 < value <= 120 for value in durations),
        "121_to_300": sum(120 < value <= 300 for value in durations),
        "over_300": sum(value > 300 for value in durations),
    }
    synthetic_training_rows = sum(is_synthetic_outcome(row) for row in candidates)
    real_completed_sessions = sum(
        row.get("outcome") == "completed" for row in real_validated_rows
    )
    users_below_personalization_threshold = real_user_ids - candidate_users
    summary = {
        "total_users": len(user_ids),
        "real_users_with_outcomes": len(real_user_ids),
        "total_tasks": len(task_keys),
        "total_sessions": len(joined),
        "real_outcome_sessions": len(real_session_rows),
        "real_completed_sessions": real_completed_sessions,
        "real_valid_sessions": real_quality.get("valid", 0),
        "real_suspicious_sessions": real_quality.get("suspicious", 0),
        "real_invalid_sessions": real_quality.get("invalid", 0),
        "real_unknown_sessions": real_quality.get("unknown", 0),
        "valid_sessions": quality.get("valid", 0),
        "suspicious_sessions": quality.get("suspicious", 0),
        "invalid_sessions": quality.get("invalid", 0),
        "unknown_sessions": quality.get("unknown", 0),
        "completed_task_occurrences": len(completed_keys),
        "real_completed_task_occurrences": len(real_completed_keys),
        "training_eligible_task_occurrences": len(candidates),
        "eligible_users": len(occurrences_by_user),
        "synthetic_rows": sum(is_synthetic_outcome(row) for row in joined),
        "demo_rows": sum(bool(row.get("is_demo")) for row in joined),
        "synthetic_training_rows": synthetic_training_rows,
        "users_with_at_least_5_occurrences": sum(
            value >= 5 for value in occurrences_by_user.values()
        ),
        "users_with_at_least_10_occurrences": sum(
            value >= 10 for value in occurrences_by_user.values()
        ),
        "users_with_enough_observations": len(candidate_users),
        "personalization_candidate_users": len(candidate_users),
        "users_below_personalization_threshold": len(
            users_below_personalization_threshold
        ),
        "long_task_occurrences_over_300": duration_buckets["over_300"],
    }
    report = {
        "audit_version": AUDIT_VERSION,
        "source_export_sha256": source_sha256,
        "privacy": {
            "contains_raw_task_text": False,
            "contains_user_ids": False,
            "contains_names_or_emails": False,
        },
        "summary": summary,
        "rows_rejected_by_session_reason": _rejection_counts(validated),
        "task_occurrence_groups_rejected": dataset.audit["rejected_groups"],
        "prediction_model_version_distribution": dict(sorted(model_versions.items())),
        "task_duration_minutes": {
            "distribution": _numeric_distribution(durations),
            "buckets": duration_buckets,
            "source": "real training-eligible completed task occurrences only",
        },
        "tasks_per_user": _numeric_distribution(tasks_by_user.values()),
        "completed_task_occurrences_per_user": _numeric_distribution(
            real_completed_by_user.values()
        ),
        "training_eligible_task_occurrences_per_user": _numeric_distribution(
            occurrences_by_user.values()
        ),
        "dataset_snapshot": {
            "dataset_version": dataset.version,
            "dataset_sha256": dataset.audit["sha256"],
            "content_sha256": dataset.audit["content_sha256"],
            "candidate_count": dataset.audit["candidate_count"],
        },
        "readiness": evaluate_readiness(summary),
        "proposed_gate_policy": policy_document(),
    }
    report["real_user_retraining_status"] = report["readiness"]["status"]
    return report


def run(input_path: Path, output_path: Path) -> dict[str, Any]:
    raw = input_path.read_bytes()
    rows = load_export(input_path)
    report = audit_export_rows(
        rows, source_sha256=hashlib.sha256(raw).hexdigest()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit an offline Supabase state export without printing PII"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = run(args.input, args.output)
    summary = report["summary"]
    print(f"REAL USER RETRAINING STATUS: {report['real_user_retraining_status']}")
    print(
        "users={total_users} tasks={total_tasks} sessions={total_sessions} "
        "eligible_occurrences={training_eligible_task_occurrences}".format(**summary)
    )
    print(f"aggregate_report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
