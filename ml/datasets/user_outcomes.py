"""Reproducible offline builder for real-user task-duration outcomes."""
from __future__ import annotations

import csv
import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ml.evaluation.user_outcomes import is_synthetic_outcome, validate_outcome_records


DATASET_VERSION = "focusbuddy-user-outcomes-v1"


@dataclass(frozen=True)
class OutcomeDataset:
    version: str
    records: tuple[dict[str, Any], ...]
    audit: dict[str, Any]


def _state_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def join_supabase_state_rows(
    cloud_rows: Iterable[dict[str, Any]],
    *,
    dataset_version: str = DATASET_VERSION,
) -> list[dict[str, Any]]:
    """Join the Supabase user envelope, task snapshot, and materialized session."""
    joined: list[dict[str, Any]] = []
    for envelope in cloud_rows:
        user_id = str(envelope.get("user_id") or "").strip()
        state = _state_dict(envelope.get("state"))
        tasks = {
            str(task.get("id") or ""): task
            for task in state.get("tasks", [])
            if isinstance(task, dict) and task.get("id")
        }
        for raw in state.get("ml_outcome_records", []):
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            task = tasks.get(str(row.get("task_id") or ""))
            prediction = (task or {}).get("duration_prediction") or {}
            row["user_id"] = user_id
            row["dataset_version"] = dataset_version
            row["task_text"] = str(
                row.get("task_text") or (task or {}).get("title") or ""
            )
            row["predicted_duration_minutes"] = row.get(
                "predicted_duration_minutes",
                prediction.get("estimated_duration_minutes"),
            )
            row["prediction_model_version"] = str(
                row.get("prediction_model_version")
                or prediction.get("model_version")
                or ""
            )
            row["prediction_source"] = str(
                row.get("prediction_source")
                or prediction.get("source")
                or ""
            )
            row["global_prediction_minutes"] = row.get(
                "global_prediction_minutes",
                prediction.get("global_prediction_minutes")
                or row.get("predicted_duration_minutes"),
            )
            row["global_model_version"] = str(
                row.get("global_model_version")
                or prediction.get("global_model_version")
                or row.get("prediction_model_version")
                or ""
            )
            row["global_dataset_version"] = str(
                row.get("global_dataset_version")
                or prediction.get("global_dataset_version")
                or ""
            )
            row["global_artifact_sha256"] = str(
                row.get("global_artifact_sha256")
                or prediction.get("global_artifact_sha256")
                or ""
            )
            row["personalization_version"] = str(
                row.get("personalization_version")
                or prediction.get("personalization_version")
                or ""
            )
            row["personalization_dataset_version"] = str(
                row.get("personalization_dataset_version")
                or prediction.get("personalization_dataset_version")
                or ""
            )
            row["data_provenance"] = str(
                row.get("data_provenance")
                or (task or {}).get("data_provenance")
                or ""
            )
            row["task_association_valid"] = bool(
                task is not None or row.get("task_snapshot_captured") is True
            )
            joined.append(row)
    return sorted(
        joined,
        key=lambda row: (
            str(row.get("user_id") or ""),
            str(row.get("task_id") or ""),
            str(row.get("occurrence_date") or ""),
            str(row.get("started_at") or ""),
            str(row.get("session_id") or ""),
        ),
    )


def _candidate_id(dataset_version: str, group_key: tuple[str, str, str]) -> str:
    stable = "|".join((dataset_version, *group_key))
    return str(uuid.uuid5(uuid.NAMESPACE_URL, stable))


def build_training_dataset(
    cloud_rows: Iterable[dict[str, Any]],
    *,
    dataset_version: str = DATASET_VERSION,
    allow_synthetic_for_testing: bool = False,
) -> OutcomeDataset:
    """Aggregate pause-aware sessions into completed task-occurrence candidates."""
    joined = join_supabase_state_rows(cloud_rows, dataset_version=dataset_version)
    validated = validate_outcome_records(joined)
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in validated:
        key = (
            str(row.get("user_id") or ""),
            str(row.get("task_id") or ""),
            str(row.get("occurrence_date") or ""),
        )
        grouped.setdefault(key, []).append(row)

    candidates: list[dict[str, Any]] = []
    rejected_groups: dict[str, int] = {}
    for key, sessions in sorted(grouped.items()):
        final_sessions = [
            row
            for row in sessions
            if row.get("task_completed") is True
            and row.get("outcome") == "completed"
        ]
        if not final_sessions:
            rejected_groups["task_not_completed"] = (
                rejected_groups.get("task_not_completed", 0) + 1
            )
            continue
        if not all(row.get("measurement_usable") for row in sessions):
            rejected_groups["incomplete_or_invalid_session_history"] = (
                rejected_groups.get("incomplete_or_invalid_session_history", 0) + 1
            )
            continue
        if (
            any(is_synthetic_outcome(row) for row in sessions)
            and not allow_synthetic_for_testing
        ):
            rejected_groups["synthetic"] = rejected_groups.get("synthetic", 0) + 1
            continue

        final = sorted(
            final_sessions,
            key=lambda row: (
                str(row.get("ended_at") or ""),
                str(row.get("session_id") or ""),
            ),
        )[-1]
        prediction_versions = {
            str(row.get("prediction_model_version") or "") for row in sessions
        }
        prediction_sources = {
            str(row.get("prediction_source") or "") for row in sessions
        }
        predictions = {
            float(row["predicted_duration_minutes"]) for row in sessions
        }
        global_predictions = {
            float(
                row.get("global_prediction_minutes")
                or row["predicted_duration_minutes"]
            )
            for row in sessions
        }
        global_versions = {
            str(
                row.get("global_model_version")
                or row.get("prediction_model_version")
                or ""
            )
            for row in sessions
        }
        global_dataset_versions = {
            str(row.get("global_dataset_version") or "") for row in sessions
        }
        global_artifact_checksums = {
            str(row.get("global_artifact_sha256") or "") for row in sessions
        }
        personalization_versions = {
            str(row.get("personalization_version") or "") for row in sessions
        }
        personalization_dataset_versions = {
            str(row.get("personalization_dataset_version") or "")
            for row in sessions
        }
        if (
            len(prediction_versions) != 1
            or len(prediction_sources) != 1
            or len(predictions) != 1
            or len(global_predictions) != 1
            or len(global_versions) != 1
            or len(global_dataset_versions) != 1
            or len(global_artifact_checksums) != 1
            or len(personalization_versions) != 1
            or len(personalization_dataset_versions) != 1
        ):
            rejected_groups["inconsistent_prediction_provenance"] = (
                rejected_groups.get("inconsistent_prediction_provenance", 0) + 1
            )
            continue

        source_session_ids = [str(row["session_id"]) for row in sessions]
        candidate = {
            "user_id": key[0],
            "task_id": key[1],
            "occurrence_date": key[2],
            "session_id": str(final.get("session_id") or ""),
            "source_session_ids": source_session_ids,
            "task_family_id": f"{key[0]}:{key[1]}:{key[2] or 'one-off'}",
            "task_text": str(final.get("task_text") or ""),
            "category": str(final.get("category") or ""),
            "importance": final.get("importance"),
            "has_deadline": bool(final.get("has_deadline")),
            "deadline_days_or_zero": float(final.get("deadline_days_or_zero") or 0),
            "predicted_duration_minutes": predictions.pop(),
            "prediction_model_version": prediction_versions.pop(),
            "prediction_source": prediction_sources.pop(),
            "global_prediction_minutes": global_predictions.pop(),
            "global_model_version": global_versions.pop(),
            "global_dataset_version": global_dataset_versions.pop(),
            "global_artifact_sha256": global_artifact_checksums.pop(),
            "personalization_version": personalization_versions.pop(),
            "personalization_dataset_version": personalization_dataset_versions.pop(),
            "started_at": min(str(row.get("started_at") or "") for row in sessions),
            "ended_at": str(final.get("ended_at") or ""),
            "actual_active_duration_minutes": round(
                sum(float(row["actual_active_duration_minutes"]) for row in sessions), 4
            ),
            "completion_status": "task_completed",
            "interruption_count": sum(
                int(row.get("interruption_count") or 0) for row in sessions
            ),
            "pause_duration_minutes": round(
                sum(float(row.get("pause_duration_minutes") or 0) for row in sessions), 4
            ),
            "created_at": str(
                final.get("task_created_at") or final.get("created_at") or ""
            ),
            "data_quality_status": "valid",
            "data_quality_reason": "aggregated_from_complete_valid_session_history",
            "data_provenance": str(final.get("data_provenance") or ""),
            "synthetic": any(is_synthetic_outcome(row) for row in sessions),
            "training_eligible": not any(
                is_synthetic_outcome(row) for row in sessions
            ),
        }
        candidates.append(candidate)

    content_canonical = json.dumps(
        candidates, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    content_sha256 = hashlib.sha256(content_canonical.encode("utf-8")).hexdigest()
    snapshot_version = f"{dataset_version}-sha256-{content_sha256[:12]}"
    versioned_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        versioned = dict(candidate)
        key = (
            str(versioned["user_id"]),
            str(versioned["task_id"]),
            str(versioned["occurrence_date"]),
        )
        versioned["record_id"] = _candidate_id(snapshot_version, key)
        versioned["dataset_version"] = snapshot_version
        versioned_candidates.append(versioned)
    snapshot_canonical = json.dumps(
        versioned_candidates,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    status_counts: dict[str, int] = {}
    for row in validated:
        quality = str(row.get("data_quality_status") or "unknown")
        status_counts[quality] = status_counts.get(quality, 0) + 1
    audit = {
        "dataset_schema_version": dataset_version,
        "dataset_version": snapshot_version,
        "content_sha256": content_sha256,
        "source_state_count": len(cloud_rows) if isinstance(cloud_rows, list) else None,
        "joined_session_count": len(joined),
        "quality_status_counts": dict(sorted(status_counts.items())),
        "task_occurrence_group_count": len(grouped),
        "candidate_count": len(versioned_candidates),
        "real_training_eligible_count": sum(
            row["training_eligible"] for row in versioned_candidates
        ),
        "rejected_groups": dict(sorted(rejected_groups.items())),
        "sha256": hashlib.sha256(snapshot_canonical.encode("utf-8")).hexdigest(),
    }
    return OutcomeDataset(snapshot_version, tuple(versioned_candidates), audit)


def write_training_dataset(dataset: OutcomeDataset, csv_path: Path, json_path: Path) -> None:
    """Write a versioned snapshot; reports should use counts, not user identifiers."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(dataset.records)
    fieldnames = list(rows[0]) if rows else []
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (list, dict))
                        else value
                        for key, value in row.items()
                    }
                )
    json_path.write_text(
        json.dumps(
            {"dataset_version": dataset.version, "audit": dataset.audit, "records": rows},
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
