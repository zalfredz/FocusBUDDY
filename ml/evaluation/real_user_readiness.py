"""Explicit, reviewable gates for future real-user Duration experiments."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


NOT_READY = "NOT READY FOR RETRAINING"
READY_FOR_OFFLINE_EXPERIMENT = "READY FOR OFFLINE EXPERIMENT ONLY"


@dataclass(frozen=True)
class ReadinessPolicy:
    policy_version: str = "duration-real-user-readiness-v1"
    dataset_min_eligible_occurrences: int = 200
    dataset_min_eligible_users: int = 20
    dataset_min_users_with_five_occurrences: int = 10
    dataset_max_unusable_session_fraction: float = 0.20
    personalization_min_occurrences: int = 30
    personalization_min_active_days: int = 14
    personalization_min_categories: int = 3
    global_min_eligible_occurrences: int = 1_000
    global_min_eligible_users: int = 50
    global_min_users_with_ten_occurrences: int = 30
    global_min_expected_locked_test_rows: int = 200
    global_min_long_task_occurrences: int = 50


DEFAULT_POLICY = ReadinessPolicy()


POLICY_RATIONALE = {
    "dataset_min_eligible_occurrences": (
        "A 200-row floor is a conservative screening gate, not a claim of statistical "
        "sufficiency; below it, a 20% holdout and 5-fold CV are too small for stable "
        "Duration error slices."
    ),
    "dataset_min_eligible_users": (
        "Twenty users leave multiple held-out user groups while preserving enough "
        "training groups for 5-fold group-aware CV."
    ),
    "dataset_min_users_with_five_occurrences": (
        "Repeated observations are needed to audit within-user dependence without "
        "letting one prolific user dominate the dataset."
    ),
    "dataset_max_unusable_session_fraction": (
        "If more than 20% of sessions are invalid/unknown/suspicious, telemetry quality "
        "must be fixed before model comparison; the value is an explicit review gate."
    ),
    "personalization_min_occurrences": (
        "Thirty outcomes is the Phase 3 provisional floor for estimating a lightweight "
        "personal residual/calibration; it does not authorize a per-user model."
    ),
    "personalization_min_active_days": (
        "Fourteen distinct days reduces the risk of calibrating to one short-lived week."
    ),
    "personalization_min_categories": (
        "Three categories provide a minimal check that a calibration is not a single-task "
        "memorization. Missing category values do not count."
    ),
    "global_min_eligible_occurrences": (
        "One thousand outcomes support a more useful locked test and duration slices than "
        "the exploratory 200-row dataset gate."
    ),
    "global_min_eligible_users": (
        "Fifty users reduce dependence on a small set of behavioral profiles and normally "
        "leave about ten users for a 20% user-group holdout."
    ),
    "global_min_users_with_ten_occurrences": (
        "Thirty users with repeated observations limit domination by a few heavy users."
    ),
    "global_min_expected_locked_test_rows": (
        "At least 200 expected locked-test rows are proposed for stable aggregate metrics; "
        "the actual user-group split must still be inspected."
    ),
    "global_min_long_task_occurrences": (
        "Tasks above 300 minutes were the worst Phase 2 slice. At least 50 are required "
        "before claiming that a replacement does not regress that slice."
    ),
}


def policy_document(policy: ReadinessPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    return {
        "policy": asdict(policy),
        "rationale": POLICY_RATIONALE,
        "status": "proposed_for_review",
        "note": "These gates permit offline evaluation only, never automatic promotion.",
    }


def evaluate_readiness(
    summary: dict[str, Any], policy: ReadinessPolicy = DEFAULT_POLICY
) -> dict[str, Any]:
    sessions = int(summary.get("total_sessions", 0))
    unusable = sum(
        int(summary.get(f"{status}_sessions", 0))
        for status in ("suspicious", "invalid", "unknown")
    )
    unusable_fraction = unusable / sessions if sessions else 1.0
    dataset_checks = {
        "eligible_occurrences": int(summary.get("training_eligible_task_occurrences", 0))
        >= policy.dataset_min_eligible_occurrences,
        "eligible_users": int(summary.get("eligible_users", 0))
        >= policy.dataset_min_eligible_users,
        "users_with_five_occurrences": int(
            summary.get("users_with_at_least_5_occurrences", 0)
        )
        >= policy.dataset_min_users_with_five_occurrences,
        "session_quality": unusable_fraction
        <= policy.dataset_max_unusable_session_fraction,
        "no_synthetic_training_rows": int(summary.get("synthetic_training_rows", 0)) == 0,
    }
    global_checks = {
        "eligible_occurrences": int(summary.get("training_eligible_task_occurrences", 0))
        >= policy.global_min_eligible_occurrences,
        "eligible_users": int(summary.get("eligible_users", 0))
        >= policy.global_min_eligible_users,
        "users_with_ten_occurrences": int(
            summary.get("users_with_at_least_10_occurrences", 0)
        )
        >= policy.global_min_users_with_ten_occurrences,
        "expected_locked_test_rows": int(
            summary.get("training_eligible_task_occurrences", 0) * 0.20
        )
        >= policy.global_min_expected_locked_test_rows,
        "long_task_occurrences": int(summary.get("long_task_occurrences_over_300", 0))
        >= policy.global_min_long_task_occurrences,
        "dataset_gate": all(dataset_checks.values()),
    }
    dataset_ready = all(dataset_checks.values())
    global_ready = all(global_checks.values())
    return {
        "policy_version": policy.policy_version,
        "status": READY_FOR_OFFLINE_EXPERIMENT if dataset_ready else NOT_READY,
        "dataset_level_training_gate": {
            "ready": dataset_ready,
            "checks": dataset_checks,
        },
        "global_retraining_gate": {
            "ready_for_candidate_experiment": global_ready,
            "checks": global_checks,
            "automatic_promotion": False,
        },
        "personalization_gate": {
            "architecture_implemented": True,
            "production_ready": int(
                summary.get("personalization_candidate_users", 0)
            ) > 0,
            "automatic_activation": False,
            "candidate_users": int(summary.get("personalization_candidate_users", 0)),
            "minimum_occurrences": policy.personalization_min_occurrences,
            "minimum_active_days": policy.personalization_min_active_days,
            "minimum_categories": policy.personalization_min_categories,
        },
        "observed_unusable_session_fraction": unusable_fraction,
    }
