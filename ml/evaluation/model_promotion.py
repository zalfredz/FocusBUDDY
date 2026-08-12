"""Manual promotion decision gate; this module never persists a model."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PromotionPolicy:
    policy_version: str = "duration-promotion-v1"
    minimum_cv_rmse_improvement_fraction: float = 0.02
    minimum_locked_rmse_improvement_fraction: float = 0.02
    maximum_locked_mae_regression_fraction: float = 0.00
    maximum_slice_rmse_regression_fraction: float = 0.10
    required_slices: tuple[str, ...] = ("over_300_minutes",)


DEFAULT_POLICY = PromotionPolicy()


def _improvement(baseline: float, candidate: float) -> float:
    if baseline <= 0:
        raise ValueError("Baseline metric must be positive")
    return (baseline - candidate) / baseline


def evaluate_promotion(
    *,
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    evidence: dict[str, Any],
    policy: PromotionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    """Return a recommendation; promotion itself always remains a manual action."""
    cv_gain = _improvement(float(baseline["cv_rmse"]), float(candidate["cv_rmse"]))
    locked_rmse_gain = _improvement(
        float(baseline["locked_test"]["rmse"]),
        float(candidate["locked_test"]["rmse"]),
    )
    locked_mae_change = (
        float(candidate["locked_test"]["mae"])
        - float(baseline["locked_test"]["mae"])
    ) / float(baseline["locked_test"]["mae"])

    baseline_slices = baseline.get("slices") or {}
    candidate_slices = candidate.get("slices") or {}
    shared_slices = sorted(set(baseline_slices) & set(candidate_slices))
    slice_regressions = {
        name: (
            float(candidate_slices[name]["rmse"])
            - float(baseline_slices[name]["rmse"])
        )
        / float(baseline_slices[name]["rmse"])
        for name in shared_slices
        if float(baseline_slices[name]["rmse"]) > 0
    }
    worst_slice_regression = max(slice_regressions.values(), default=0.0)

    evidence_checks = {
        "real_user_dataset_gate_passed": bool(
            evidence.get("real_user_dataset_gate_passed")
        ),
        "locked_test_was_untouched_until_selection": bool(
            evidence.get("locked_test_was_untouched_until_selection")
        ),
        "reproducible_run": bool(evidence.get("reproducible_run")),
        "dataset_version_present": bool(evidence.get("dataset_version")),
        "model_version_present": bool(evidence.get("model_version")),
        "feature_schema_compatible": bool(
            evidence.get("feature_schema_compatible")
        ),
        "baseline_is_comparable": bool(evidence.get("baseline_is_comparable")),
        "important_slices_present": all(
            name in shared_slices for name in policy.required_slices
        ),
    }
    metric_checks = {
        "cv_rmse_improvement": cv_gain
        >= policy.minimum_cv_rmse_improvement_fraction,
        "locked_rmse_improvement": locked_rmse_gain
        >= policy.minimum_locked_rmse_improvement_fraction,
        "locked_mae_no_regression": locked_mae_change
        <= policy.maximum_locked_mae_regression_fraction,
        "no_major_slice_regression": worst_slice_regression
        <= policy.maximum_slice_rmse_regression_fraction,
    }
    accepted_for_manual_review = all(evidence_checks.values()) and all(
        metric_checks.values()
    )
    return {
        "policy": asdict(policy),
        "accepted_for_manual_promotion_review": accepted_for_manual_review,
        "automatic_promotion": False,
        "recommendation": (
            "ELIGIBLE FOR MANUAL PROMOTION REVIEW"
            if accepted_for_manual_review
            else "KEEP EXISTING MODEL"
        ),
        "metric_checks": metric_checks,
        "evidence_checks": evidence_checks,
        "observed": {
            "cv_rmse_improvement_fraction": cv_gain,
            "locked_rmse_improvement_fraction": locked_rmse_gain,
            "locked_mae_change_fraction": locked_mae_change,
            "slice_rmse_regression_fraction": slice_regressions,
            "worst_slice_rmse_regression_fraction": worst_slice_regression,
        },
    }
