"""Derive bounded Duration calibration from prior eligible task outcomes."""
from __future__ import annotations

import hashlib
import json
import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from models.personalization import (
    DEFAULT_MIN_ACTIVE_DAYS,
    DEFAULT_MIN_CATEGORIES,
    MAX_FACTOR,
    MIN_FACTOR,
    DurationPersonalizationState,
    configured_min_outcomes,
)


@dataclass(frozen=True)
class PersonalizationBuildPolicy:
    minimum_outcomes: int = 30
    minimum_active_days: int = DEFAULT_MIN_ACTIVE_DAYS
    minimum_categories: int = DEFAULT_MIN_CATEGORIES
    minimum_factor: float = MIN_FACTOR
    maximum_factor: float = MAX_FACTOR

    def validate(self) -> None:
        if self.minimum_outcomes < configured_min_outcomes():
            raise ValueError("Threshold offline tidak boleh di bawah threshold runtime")
        if self.minimum_active_days < DEFAULT_MIN_ACTIVE_DAYS:
            raise ValueError("Minimum hari aktif tidak boleh di bawah policy runtime")
        if self.minimum_categories < DEFAULT_MIN_CATEGORIES:
            raise ValueError("Minimum kategori tidak boleh di bawah policy runtime")
        if not 0 < self.minimum_factor <= 1 <= self.maximum_factor:
            raise ValueError("Batas faktor personalisasi tidak valid")


def _timestamp(value: Any) -> datetime | None:
    raw = str(value or "")
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def build_duration_personalization(
    user_id: str,
    candidates: Iterable[dict[str, Any]],
    *,
    dataset_version: str,
    cutoff_at: str,
    computed_at: str,
    exclude_task_id: str = "",
    exclude_occurrence_date: str = "",
    policy: PersonalizationBuildPolicy | None = None,
    allow_synthetic_for_testing: bool = False,
) -> DurationPersonalizationState:
    """Build state offline; current/future outcomes and other users are excluded."""
    policy = policy or PersonalizationBuildPolicy()
    policy.validate()
    cutoff = _timestamp(cutoff_at)
    if cutoff is None:
        raise ValueError("cutoff_at harus ISO timestamp valid")
    if not allow_synthetic_for_testing and not _is_uuid(user_id):
        raise ValueError("Produksi memerlukan Supabase Auth UUID")

    accepted: list[dict[str, Any]] = []
    for raw in candidates:
        row = dict(raw)
        if str(row.get("user_id") or "") != user_id:
            continue
        if exclude_task_id and str(row.get("task_id") or "") == exclude_task_id:
            if not exclude_occurrence_date or str(row.get("occurrence_date") or "") == exclude_occurrence_date:
                continue
        ended = _timestamp(row.get("ended_at"))
        if ended is None:
            continue
        try:
            is_prior = ended < cutoff
        except TypeError:
            continue
        if not is_prior:
            continue
        provenance = str(row.get("data_provenance") or "")
        synthetic = bool(row.get("synthetic")) or provenance in {
            "synthetic_scenario",
            "synthetic_fixture",
        }
        if synthetic and not allow_synthetic_for_testing:
            continue
        if not allow_synthetic_for_testing and provenance != "real_user":
            continue
        if not synthetic and row.get("training_eligible") is not True:
            continue
        if row.get("data_quality_status") != "valid":
            continue
        if row.get("completion_status") != "task_completed":
            continue
        try:
            predicted = float(
                row.get("global_prediction_minutes")
                or row.get("predicted_duration_minutes")
            )
            actual = float(row.get("actual_active_duration_minutes"))
        except (TypeError, ValueError):
            continue
        if predicted <= 0 or actual <= 0:
            continue
        row["_ratio"] = max(
            policy.minimum_factor,
            min(actual / predicted, policy.maximum_factor),
        )
        accepted.append(row)

    canonical = json.dumps(
        [
            {
                "record_id": row.get("record_id"),
                "ended_at": row.get("ended_at"),
                "ratio": row["_ratio"],
            }
            for row in sorted(accepted, key=lambda item: str(item.get("record_id") or ""))
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    count = len(accepted)
    active_days = {
        str(row.get("ended_at") or "")[:10]
        for row in accepted
        if str(row.get("ended_at") or "")[:10]
    }
    categories = {
        str(row.get("category") or "").strip()
        for row in accepted
        if str(row.get("category") or "").strip()
    }
    active = (
        count >= policy.minimum_outcomes
        and len(active_days) >= policy.minimum_active_days
        and len(categories) >= policy.minimum_categories
    )
    factor = statistics.median(row["_ratio"] for row in accepted) if active else 1.0
    test_only = allow_synthetic_for_testing
    return DurationPersonalizationState(
        user_id=user_id,
        factor=float(factor),
        eligible_outcome_count=count,
        active_day_count=len(active_days),
        category_count=len(categories),
        active=active,
        source_dataset_version=dataset_version,
        source_outcomes_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        cutoff_at=cutoff_at,
        computed_at=computed_at,
        test_only=test_only,
    )
