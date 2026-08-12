"""Offline quality classification for versioned Focus outcome records."""
from __future__ import annotations

import math
import uuid
from collections import Counter
from datetime import datetime
from typing import Any, Iterable


SUSPICIOUS_SESSION_MINUTES = 8 * 60
IMPOSSIBLE_SESSION_MINUTES = 24 * 60
IN_PROGRESS_STATUSES = {"started", "paused"}
UNRELIABLE_STATUSES = {"abandoned", "crashed", "background_unknown"}
REAL_USER = "real_user"
SYNTHETIC_PROVENANCE = {"synthetic_scenario", "synthetic_fixture"}
ALLOWED_PROVENANCE = {REAL_USER, *SYNTHETIC_PROVENANCE}
ALLOWED_COLLECTION_CONTEXTS = {"production", "setting_demo", "test_fixture"}


def outcome_provenance(record: dict[str, Any]) -> str:
    """Return explicit provenance, with conservative labels for legacy rows."""
    explicit = str(record.get("data_provenance") or "").strip()
    if explicit in ALLOWED_PROVENANCE:
        return explicit
    if record.get("synthetic") is True:
        return "synthetic_fixture"
    if record.get("is_demo") is True or record.get("is_test") is True:
        return "legacy_demo_or_test"
    return "legacy_unspecified"


def is_synthetic_outcome(record: dict[str, Any]) -> bool:
    return outcome_provenance(record) in SYNTHETIC_PROVENANCE


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value or ""))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _iso_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def validate_outcome_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classify records without deleting or mutating their provenance."""
    materialized = [dict(record) for record in records]
    record_counts = Counter(
        str(record.get("record_id") or "") for record in materialized
    )
    session_counts = Counter(
        str(record.get("session_id") or "") for record in materialized
    )
    validated: list[dict[str, Any]] = []

    for record in materialized:
        reasons: list[str] = []
        status = "valid"
        record_id = str(record.get("record_id") or "")
        session_id = str(record.get("session_id") or "")
        completion = str(record.get("completion_status") or "")

        missing_identity = [
            field
            for field in (
                "schema_version",
                "record_id",
                "user_id",
                "task_id",
                "session_id",
                "task_text",
                "completion_status",
                "prediction_source",
                "collection_context",
                "data_quality_status",
                "data_quality_reason",
                "task_created_at",
                "created_at",
            )
            if not str(record.get(field) or "").strip()
        ]
        if missing_identity:
            status = "invalid"
            reasons.append("missing_fields:" + ",".join(missing_identity))
        if record.get("schema_version") not in {None, "focus-outcome-v1"}:
            status = "invalid"
            reasons.append("unsupported_schema_version")
        if record_id and record_counts[record_id] > 1:
            status = "invalid"
            reasons.append("duplicate_record_id")
        if session_id and session_counts[session_id] > 1:
            status = "invalid"
            reasons.append("duplicate_session_id")
        if record.get("task_association_valid") is not True:
            status = "invalid"
            reasons.append("invalid_task_session_relationship")
        provenance = outcome_provenance(record)
        if provenance not in ALLOWED_PROVENANCE:
            status = "invalid"
            reasons.append("missing_or_legacy_data_provenance")
        if provenance == REAL_USER and not _is_uuid(record.get("user_id")):
            status = "invalid"
            reasons.append("real_user_id_must_be_supabase_auth_uuid")
        if record.get("is_test"):
            status = "invalid"
            reasons.append("test_record")
        if record.get("is_demo") and provenance != "synthetic_scenario":
            status = "invalid"
            reasons.append("ambiguous_demo_record")
        if bool(record.get("synthetic")) != (provenance in SYNTHETIC_PROVENANCE):
            status = "invalid"
            reasons.append("inconsistent_synthetic_provenance")

        collection_context = str(record.get("collection_context") or "")
        if collection_context not in ALLOWED_COLLECTION_CONTEXTS:
            status = "invalid"
            reasons.append("invalid_collection_context")
        elif provenance == REAL_USER and collection_context not in {
            "production",
            "setting_demo",
        }:
            status = "invalid"
            reasons.append("real_user_invalid_collection_context")

        predicted = _positive_number(record.get("predicted_duration_minutes"))
        if predicted is None:
            status = "invalid"
            reasons.append("missing_or_invalid_prediction")
        if not str(record.get("prediction_model_version") or "").strip():
            status = "invalid"
            reasons.append("missing_prediction_model_version")
        if not str(
            record.get("global_model_version")
            or record.get("prediction_model_version")
            or ""
        ).strip():
            status = "invalid"
            reasons.append("missing_global_model_version")
        try:
            importance = float(record.get("importance"))
        except (TypeError, ValueError):
            importance = None
        if importance is None or not 1 <= importance <= 10:
            status = "invalid"
            reasons.append("missing_or_invalid_importance")
        try:
            deadline_days = float(record.get("deadline_days_or_zero"))
        except (TypeError, ValueError):
            deadline_days = None
        if deadline_days is None or not math.isfinite(deadline_days) or deadline_days < 0:
            status = "invalid"
            reasons.append("missing_or_invalid_deadline_days")
        elif record.get("has_deadline") is False and deadline_days != 0:
            status = "invalid"
            reasons.append("no_deadline_must_encode_zero")

        planned = _positive_number(record.get("planned_session_minutes"))
        if planned is None:
            status = "invalid"
            reasons.append("missing_or_invalid_planned_session_duration")

        for field in ("task_created_at", "created_at"):
            raw_timestamp = str(record.get(field) or "").strip()
            if raw_timestamp and _iso_datetime(raw_timestamp) is None:
                status = "invalid"
                reasons.append(f"invalid_{field}")

        try:
            interruptions = int(record.get("interruption_count") or 0)
            pause_minutes = float(record.get("pause_duration_minutes") or 0)
        except (TypeError, ValueError):
            interruptions = -1
            pause_minutes = -1
        if interruptions < 0 or pause_minutes < 0:
            status = "invalid"
            reasons.append("invalid_pause_or_interruption_count")

        started_raw = str(record.get("started_at") or "").strip()
        ended_raw = str(record.get("ended_at") or "").strip()
        started = _iso_datetime(started_raw)
        ended = _iso_datetime(ended_raw)
        if not started_raw:
            status = "invalid"
            reasons.append("missing_start_timestamp")
        elif started is None:
            status = "invalid"
            reasons.append("invalid_start_timestamp")
        if not ended_raw:
            if status != "invalid" and completion in IN_PROGRESS_STATUSES | UNRELIABLE_STATUSES:
                status = "unknown"
                reasons.append("session_not_finalized")
            else:
                status = "invalid"
                reasons.append("missing_end_timestamp")
        elif ended is None:
            status = "invalid"
            reasons.append("invalid_end_timestamp")
        elif started is not None:
            try:
                elapsed_minutes = (ended - started).total_seconds() / 60.0
            except TypeError:
                status = "invalid"
                reasons.append("timestamp_timezone_mismatch")
            else:
                if elapsed_minutes < 0:
                    status = "invalid"
                    reasons.append("end_before_start")

        raw_active = record.get("actual_active_duration_minutes")
        try:
            active = float(raw_active)
        except (TypeError, ValueError):
            active = None
        if active is None:
            if status != "invalid" and completion in IN_PROGRESS_STATUSES | UNRELIABLE_STATUSES:
                status = "unknown"
                reasons.append("active_duration_unknown")
            else:
                status = "invalid"
                reasons.append("missing_active_duration")
        elif active <= 0:
            status = "invalid"
            reasons.append("non_positive_active_duration")
        elif active > IMPOSSIBLE_SESSION_MINUTES:
            status = "invalid"
            reasons.append("impossible_active_duration")
        elif active > SUSPICIOUS_SESSION_MINUTES and status == "valid":
            status = "suspicious"
            reasons.append("suspiciously_long_session")

        if active is not None and started is not None and ended is not None:
            try:
                elapsed_minutes = (ended - started).total_seconds() / 60.0
            except TypeError:
                pass
            else:
                if active > elapsed_minutes + 1.0:
                    status = "invalid"
                    reasons.append("active_duration_exceeds_elapsed")

        timing_quality = str(record.get("timing_quality") or "")
        if (
            status not in {"invalid", "suspicious"}
            and (completion in UNRELIABLE_STATUSES or "unreliable" in timing_quality)
        ):
            status = "unknown"
            reasons.append("timing_reliability_unknown")

        synthetic = is_synthetic_outcome(record)
        measurement_usable = status == "valid" and active is not None and active > 0
        training_eligible = bool(
            measurement_usable
            and record.get("task_completed") is True
            and str(record.get("outcome") or "") == "completed"
            and not synthetic
        )
        output = dict(record)
        output["data_provenance"] = provenance
        output["synthetic"] = synthetic
        output["data_quality_status"] = status
        output["data_quality_reason"] = ";".join(dict.fromkeys(reasons)) or "ok"
        output["measurement_usable"] = measurement_usable
        output["training_eligible_session"] = training_eligible
        validated.append(output)

    return validated
