"""Leakage-safe offline comparison of Global versus personalized Duration."""
from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from ml.evaluation.metrics import regression_metrics
from ml.personalization.duration import (
    PersonalizationBuildPolicy,
    build_duration_personalization,
)


EVALUATION_VERSION = "duration-personalization-temporal-v1"
MINIMUM_HOLDOUT_OUTCOMES = 5
READY = "READY FOR EVALUATION"
NOT_READY = "NOT READY — NEED MORE REAL USER DATA"


def _timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value or ""))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _eligible_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    row = dict(raw)
    if row.get("training_eligible") is not True:
        return None
    if row.get("data_quality_status") != "valid":
        return None
    if row.get("completion_status") != "task_completed":
        return None
    if row.get("data_provenance") != "real_user" or row.get("synthetic"):
        return None
    if not _is_uuid(row.get("user_id")):
        return None
    ended = _timestamp(row.get("ended_at"))
    actual = _positive(row.get("actual_active_duration_minutes"))
    global_prediction = _positive(
        row.get("global_prediction_minutes")
        or row.get("predicted_duration_minutes")
    )
    if ended is None or actual is None or global_prediction is None:
        return None
    row["_ended"] = ended
    row["_actual"] = actual
    row["_global"] = global_prediction
    return row


def _thresholds(rows: list[dict[str, Any]]) -> tuple[int, int, int]:
    days = {str(row.get("ended_at") or "")[:10] for row in rows}
    categories = {
        str(row.get("category") or "").strip()
        for row in rows
        if str(row.get("category") or "").strip()
    }
    return len(rows), len(days - {""}), len(categories)


def _passes(
    rows: list[dict[str, Any]], policy: PersonalizationBuildPolicy
) -> bool:
    outcomes, days, categories = _thresholds(rows)
    return (
        outcomes >= policy.minimum_outcomes
        and days >= policy.minimum_active_days
        and categories >= policy.minimum_categories
    )


def _first_temporal_boundary(
    rows: list[dict[str, Any]],
    policy: PersonalizationBuildPolicy,
    minimum_holdout_outcomes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Find the first timestamp boundary with eligible prior-only history."""
    timestamps = sorted({row["_ended"] for row in rows})
    for cutoff in timestamps:
        history = [row for row in rows if row["_ended"] < cutoff]
        holdout = [row for row in rows if row["_ended"] >= cutoff]
        if _passes(history, policy) and len(holdout) >= minimum_holdout_outcomes:
            return history, holdout
    return None


def _safe_metrics(actual: list[float], predicted: list[float]) -> dict[str, Any]:
    metrics = regression_metrics(actual, predicted)
    return {
        key: value if math.isfinite(value) else None
        for key, value in metrics.items()
    }


def _calibrated_minutes(global_minutes: float, factor: float) -> float:
    return float(max(5, min(round(global_minutes * factor), 300)))


def evaluate_duration_personalization(
    records: Iterable[dict[str, Any]],
    *,
    dataset_version: str,
    policy: PersonalizationBuildPolicy | None = None,
    minimum_holdout_outcomes: int = MINIMUM_HOLDOUT_OUTCOMES,
) -> dict[str, Any]:
    """Compare fixed prior-only calibration with Global predictions per user."""
    policy = policy or PersonalizationBuildPolicy()
    policy.validate()
    if minimum_holdout_outcomes < 1:
        raise ValueError("minimum_holdout_outcomes harus positif")

    by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in records:
        eligible = _eligible_row(raw)
        if eligible is not None:
            by_user[str(eligible["user_id"])].append(eligible)
    for rows in by_user.values():
        rows.sort(
            key=lambda row: (
                row["_ended"],
                str(row.get("record_id") or ""),
            )
        )

    currently_eligible = {
        user_id for user_id, rows in by_user.items() if _passes(rows, policy)
    }
    aggregate_actual: list[float] = []
    aggregate_global: list[float] = []
    aggregate_personal: list[float] = []
    private_results: list[tuple[str, dict[str, Any]]] = []

    for user_id, rows in by_user.items():
        boundary = _first_temporal_boundary(
            rows, policy, minimum_holdout_outcomes
        )
        if boundary is None:
            continue
        history, holdout = boundary
        cutoff_at = min(row["_ended"] for row in holdout).isoformat()
        state = build_duration_personalization(
            user_id,
            rows,
            dataset_version=dataset_version,
            cutoff_at=cutoff_at,
            computed_at=cutoff_at,
            policy=policy,
        )
        if not state.active or state.eligible_outcome_count != len(history):
            continue

        actual = [float(row["_actual"]) for row in holdout]
        global_predictions = [float(row["_global"]) for row in holdout]
        personalized = [
            _calibrated_minutes(value, state.factor)
            for value in global_predictions
        ]
        global_metrics = _safe_metrics(actual, global_predictions)
        personal_metrics = _safe_metrics(actual, personalized)
        global_mae = float(global_metrics["mae"])
        personal_mae = float(personal_metrics["mae"])
        private_results.append(
            (
                user_id,
                {
                    "history_outcomes": len(history),
                    "holdout_outcomes": len(holdout),
                    "history_active_days": _thresholds(history)[1],
                    "history_categories": _thresholds(history)[2],
                    "calibration_factor": state.factor,
                    "global_metrics": global_metrics,
                    "personalized_metrics": personal_metrics,
                    "mae_change_minutes": personal_mae - global_mae,
                    "mae_relative_improvement": (
                        (global_mae - personal_mae) / global_mae
                        if global_mae > 0
                        else None
                    ),
                    "personalization_improved_mae": personal_mae < global_mae,
                },
            )
        )
        aggregate_actual.extend(actual)
        aggregate_global.extend(global_predictions)
        aggregate_personal.extend(personalized)

    anonymized_results = []
    for index, (_, result) in enumerate(sorted(private_results), start=1):
        anonymized_results.append({"subject": f"user_{index:03d}", **result})

    ready = bool(anonymized_results)
    aggregate = None
    if ready:
        global_metrics = _safe_metrics(aggregate_actual, aggregate_global)
        personal_metrics = _safe_metrics(aggregate_actual, aggregate_personal)
        aggregate = {
            "holdout_outcomes": len(aggregate_actual),
            "global_metrics": global_metrics,
            "personalized_metrics": personal_metrics,
            "mae_change_minutes": (
                float(personal_metrics["mae"]) - float(global_metrics["mae"])
            ),
            "mae_relative_improvement": (
                (float(global_metrics["mae"]) - float(personal_metrics["mae"]))
                / float(global_metrics["mae"])
                if float(global_metrics["mae"]) > 0
                else None
            ),
            "users_improved_mae": sum(
                result["personalization_improved_mae"]
                for result in anonymized_results
            ),
            "users_not_improved_mae": sum(
                not result["personalization_improved_mae"]
                for result in anonymized_results
            ),
        }

    return {
        "evaluation_version": EVALUATION_VERSION,
        "status": READY if ready else NOT_READY,
        "dataset_version": dataset_version,
        "method": {
            "strategy": "per_user_prior_only_temporal_holdout",
            "calibration": "bounded_median_actual_over_global",
            "calibration_factor_bounds": [
                policy.minimum_factor,
                policy.maximum_factor,
            ],
            "minimum_history_outcomes": policy.minimum_outcomes,
            "minimum_history_active_days": policy.minimum_active_days,
            "minimum_history_categories": policy.minimum_categories,
            "minimum_holdout_outcomes": minimum_holdout_outcomes,
            "current_and_future_outcomes_excluded": True,
            "user_id_used_as_feature": False,
            "cross_user_calibration": False,
        },
        "summary": {
            "real_users_with_eligible_outcomes": len(by_user),
            "users_currently_personalization_eligible": len(currently_eligible),
            "users_ready_for_temporal_evaluation": len(anonymized_results),
            "users_below_personalization_threshold": len(by_user)
            - len(currently_eligible),
            "eligible_but_without_sufficient_future_holdout": len(
                currently_eligible
            )
            - len(anonymized_results),
        },
        "aggregate": aggregate,
        "per_user": anonymized_results,
        "automatic_activation": False,
        "automatic_promotion": False,
        "global_model_trained": False,
        "privacy": {
            "contains_user_ids": False,
            "contains_raw_task_text": False,
            "contains_names_or_emails": False,
        },
    }
