"""Inference-only validation and application of per-user Duration calibration."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Mapping


PERSONALIZATION_VERSION = "duration-personalization-v1"
DEFAULT_MIN_ELIGIBLE_OUTCOMES = 30
DEFAULT_MIN_ACTIVE_DAYS = 14
DEFAULT_MIN_CATEGORIES = 3
MIN_FACTOR = 0.5
MAX_FACTOR = 2.0


def configured_min_outcomes() -> int:
    raw = os.getenv("FOCUSBUDDY_PERSONALIZATION_MIN_OUTCOMES", "")
    try:
        value = int(raw) if raw else DEFAULT_MIN_ELIGIBLE_OUTCOMES
    except ValueError:
        value = DEFAULT_MIN_ELIGIBLE_OUTCOMES
    return max(DEFAULT_MIN_ELIGIBLE_OUTCOMES, value)


@dataclass(frozen=True)
class DurationPersonalizationState:
    user_id: str
    version: str = PERSONALIZATION_VERSION
    factor: float = 1.0
    eligible_outcome_count: int = 0
    active_day_count: int = 0
    category_count: int = 0
    active: bool = False
    source_dataset_version: str = ""
    source_outcomes_sha256: str = ""
    cutoff_at: str = ""
    computed_at: str = ""
    test_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "version": self.version,
            "factor": self.factor,
            "eligible_outcome_count": self.eligible_outcome_count,
            "minimum_required": configured_min_outcomes(),
            "active_day_count": self.active_day_count,
            "minimum_active_days": DEFAULT_MIN_ACTIVE_DAYS,
            "category_count": self.category_count,
            "minimum_categories": DEFAULT_MIN_CATEGORIES,
            "active": self.active,
            "source_dataset_version": self.source_dataset_version,
            "source_outcomes_sha256": self.source_outcomes_sha256,
            "cutoff_at": self.cutoff_at,
            "computed_at": self.computed_at,
            "test_only": self.test_only,
        }


def cold_start(user_id: str = "") -> DurationPersonalizationState:
    return DurationPersonalizationState(user_id=str(user_id or ""))


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def state_for_user(
    payload: Mapping[str, Any] | None,
    *,
    expected_user_id: str,
    allow_test_state: bool = False,
) -> DurationPersonalizationState:
    """Reject mismatched, unversioned, test-only, or under-threshold state."""
    if not payload or not expected_user_id:
        return cold_start(expected_user_id)
    if str(payload.get("user_id") or "") != expected_user_id:
        return cold_start(expected_user_id)
    if str(payload.get("version") or "") != PERSONALIZATION_VERSION:
        return cold_start(expected_user_id)
    try:
        factor = float(payload.get("factor"))
        count = int(payload.get("eligible_outcome_count"))
        active_days = int(payload.get("active_day_count"))
        categories = int(payload.get("category_count"))
    except (TypeError, ValueError):
        return cold_start(expected_user_id)
    test_only = bool(payload.get("test_only"))
    dataset_version = str(payload.get("source_dataset_version") or "")
    checksum = str(payload.get("source_outcomes_sha256") or "").lower()
    cutoff_at = str(payload.get("cutoff_at") or "")
    computed_at = str(payload.get("computed_at") or "")
    eligible = (
        bool(payload.get("active"))
        and count >= configured_min_outcomes()
        and active_days >= DEFAULT_MIN_ACTIVE_DAYS
        and categories >= DEFAULT_MIN_CATEGORIES
        and MIN_FACTOR <= factor <= MAX_FACTOR
        and (allow_test_state or not test_only)
        and (allow_test_state or _is_uuid(expected_user_id))
        and bool(dataset_version and cutoff_at and computed_at)
        and _is_sha256(checksum)
    )
    if not eligible:
        return DurationPersonalizationState(
            user_id=expected_user_id,
            eligible_outcome_count=max(0, count),
            active_day_count=max(0, active_days),
            category_count=max(0, categories),
            source_dataset_version=dataset_version,
            cutoff_at=cutoff_at,
            computed_at=computed_at,
            test_only=test_only,
        )
    return DurationPersonalizationState(
        user_id=expected_user_id,
        factor=factor,
        eligible_outcome_count=count,
        active_day_count=active_days,
        category_count=categories,
        active=True,
        source_dataset_version=dataset_version,
        source_outcomes_sha256=checksum,
        cutoff_at=cutoff_at,
        computed_at=computed_at,
        test_only=test_only,
    )
