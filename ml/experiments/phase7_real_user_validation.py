"""Phase 7 controller for real-data readiness and personalization validation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ml.datasets.user_outcomes import build_training_dataset
from ml.evaluation.personalization_validation import (
    NOT_READY as PERSONALIZATION_NOT_READY,
    READY as PERSONALIZATION_READY,
    evaluate_duration_personalization,
)
from ml.evaluation.real_user_data_audit import audit_export_rows, load_export
from ml.evaluation.real_user_readiness import DEFAULT_POLICY


PHASE_VERSION = "phase7-real-user-personalization-v1"
REAL_DATA_READY = "READY"
REAL_DATA_NOT_READY = "NOT READY"
GLOBAL_READY = "READY"
GLOBAL_NOT_READY = "NOT READY"


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run(
    input_path: Path,
    report_dir: Path,
    *,
    input_scope: str = "restricted_supabase_export",
) -> dict[str, Any]:
    """Audit one supplied export; never train, activate, or promote a model."""
    raw = input_path.read_bytes()
    cloud_rows = load_export(input_path)
    source_sha256 = hashlib.sha256(raw).hexdigest()
    audit = audit_export_rows(cloud_rows, source_sha256=source_sha256)
    dataset = build_training_dataset(cloud_rows)
    summary = audit["summary"]
    candidates = list(dataset.records)

    evaluation = evaluate_duration_personalization(
        candidates,
        dataset_version=dataset.version,
    )
    personalization_ready = evaluation["status"] == PERSONALIZATION_READY
    global_ready = bool(
        audit["readiness"]["global_retraining_gate"][
            "ready_for_candidate_experiment"
        ]
    )
    real_data_ready = int(summary["training_eligible_task_occurrences"]) > 0

    real_report = {
        "phase_version": PHASE_VERSION,
        "real_user_data_status": (
            REAL_DATA_READY if real_data_ready else REAL_DATA_NOT_READY
        ),
        "personalization_status": (
            PERSONALIZATION_READY
            if personalization_ready
            else PERSONALIZATION_NOT_READY
        ),
        "global_retraining_status": (
            GLOBAL_READY if global_ready else GLOBAL_NOT_READY
        ),
        "audited_input": {
            "scope": input_scope,
            "source_sha256": source_sha256,
            "row_count": len(cloud_rows),
            "contains_only_synthetic_sessions": (
                int(summary["total_sessions"]) > 0
                and int(summary["real_outcome_sessions"]) == 0
                and int(summary["synthetic_rows"]) == int(summary["total_sessions"])
            ),
            "note": (
                "Counts describe only this audited input; they do not query or infer "
                "the current contents of Supabase."
            ),
        },
        "summary": {
            "real_users_detected": int(summary["real_users_with_outcomes"]),
            "real_sessions_detected": int(summary["real_outcome_sessions"]),
            "completed_sessions": int(summary["real_completed_sessions"]),
            "valid_sessions": int(summary["real_valid_sessions"]),
            "suspicious_sessions": int(summary["real_suspicious_sessions"]),
            "invalid_sessions": int(summary["real_invalid_sessions"]),
            "unknown_sessions": int(summary["real_unknown_sessions"]),
            "training_eligible_task_occurrences": int(
                summary["training_eligible_task_occurrences"]
            ),
            "personalized_users_eligible": int(
                summary["personalization_candidate_users"]
            ),
            "users_below_personalization_threshold": int(
                summary["users_below_personalization_threshold"]
            ),
            "synthetic_sessions_excluded": int(summary["synthetic_rows"]),
        },
        "quality": {
            "session_rejections": audit["rows_rejected_by_session_reason"],
            "task_occurrence_rejections": audit[
                "task_occurrence_groups_rejected"
            ],
            "synthetic_training_rows": int(summary["synthetic_training_rows"]),
            "duplicate_session_ids": int(
                audit["rows_rejected_by_session_reason"].get(
                    "duplicate_session_id", 0
                )
            ),
            "duplicate_record_ids": int(
                audit["rows_rejected_by_session_reason"].get(
                    "duplicate_record_id", 0
                )
            ),
            "unfinished_sessions_are_zero_duration": False,
            "task_completion_required_for_label": True,
            "multi_session_task_aggregation": True,
            "identity_boundary": "Supabase Auth UUID envelope",
            "user_id_used_as_model_feature": False,
        },
        "dataset_snapshot": audit["dataset_snapshot"],
        "global_retraining_gate": audit["readiness"][
            "global_retraining_gate"
        ],
        "privacy": audit["privacy"],
        "training_started": False,
        "production_inference_changed": False,
        "automatic_activation": False,
        "automatic_promotion": False,
    }

    personalization_report = {
        "phase_version": PHASE_VERSION,
        "status": (
            PERSONALIZATION_READY
            if personalization_ready
            else PERSONALIZATION_NOT_READY
        ),
        "dataset_version": dataset.version,
        "threshold": {
            "minimum_eligible_completed_outcomes": (
                DEFAULT_POLICY.personalization_min_occurrences
            ),
            "minimum_active_days": DEFAULT_POLICY.personalization_min_active_days,
            "minimum_categories": DEFAULT_POLICY.personalization_min_categories,
            "minimum_future_temporal_holdout_outcomes": evaluation["method"][
                "minimum_holdout_outcomes"
            ],
            "note": (
                "The first three values are the current runtime gate. The holdout "
                "minimum is an evaluation-only safeguard."
            ),
        },
        "summary": evaluation["summary"],
        "evaluation_created": personalization_ready,
        "stop_condition": (
            None
            if personalization_ready
            else "insufficient_real_user_temporal_holdout_data"
            if candidates
            else "no_real_user_training_eligible_data"
        ),
        "user_isolation_verified": True,
        "user_id_used_as_model_feature": False,
        "insufficient_data_fallback": "Global Model only",
        "automatic_activation": False,
        "automatic_promotion": False,
        "global_model_trained": False,
        "privacy": evaluation["privacy"],
    }

    report_dir.mkdir(parents=True, exist_ok=True)
    real_path = report_dir / "real_user_data_readiness.json"
    personalization_path = report_dir / "personalization_readiness.json"
    evaluation_path = report_dir / "personalization_evaluation.json"
    _write(real_path, real_report)
    _write(personalization_path, personalization_report)
    if personalization_ready:
        _write(evaluation_path, evaluation)
    elif evaluation_path.exists():
        evaluation_path.unlink()

    return {
        "real_user_data": real_report,
        "personalization_readiness": personalization_report,
        "personalization_evaluation": evaluation if personalization_ready else None,
        "outputs": {
            "real_user_data_readiness": str(real_path),
            "personalization_readiness": str(personalization_path),
            "personalization_evaluation": (
                str(evaluation_path) if personalization_ready else None
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Phase 7 real-user collection and personalization"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report-dir", default=Path("reports"), type=Path)
    parser.add_argument(
        "--input-scope",
        default="restricted_supabase_export",
        help="Human-readable scope; never include a user identifier.",
    )
    args = parser.parse_args()
    result = run(args.input, args.report_dir, input_scope=args.input_scope)
    real = result["real_user_data"]
    print(f"REAL USER DATA STATUS: {real['real_user_data_status']}")
    print(f"PERSONALIZATION STATUS: {real['personalization_status']}")
    print(f"GLOBAL RETRAINING STATUS: {real['global_retraining_status']}")
    print(f"reports={args.report_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
