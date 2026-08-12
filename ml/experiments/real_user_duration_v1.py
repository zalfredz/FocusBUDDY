"""Phase 5 controller: enforce readiness before any real-user training."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ml.evaluation.real_user_data_audit import audit_export_rows, load_export


EXPERIMENT_VERSION = "duration-real-user-v1"
NOT_READY = "REAL USER RETRAINING STATUS: NOT READY"


def _failed_checks(readiness: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for gate_name in ("dataset_level_training_gate", "global_retraining_gate"):
        for check_name, passed in readiness[gate_name]["checks"].items():
            if not passed:
                failures.append(f"{gate_name}.{check_name}")
    return failures


def run(input_path: Path, report_path: Path) -> dict[str, Any]:
    """Run readiness and stop before training whenever a critical gate fails."""
    raw = input_path.read_bytes()
    cloud_rows = load_export(input_path)
    audit = audit_export_rows(
        cloud_rows, source_sha256=hashlib.sha256(raw).hexdigest()
    )
    summary = audit["summary"]
    readiness = audit["readiness"]
    eligible_rows = int(summary["training_eligible_task_occurrences"])
    global_ready = bool(
        readiness["global_retraining_gate"]["ready_for_candidate_experiment"]
    )

    if eligible_rows == 0:
        stop_condition = "no_real_user_training_eligible_data"
    elif not global_ready:
        stop_condition = "phase4_global_retraining_gate_failed"
    else:
        raise RuntimeError(
            "The reviewed export passed Phase 5 readiness. Candidate training must be "
            "implemented and reviewed in a new controlled run; this repository run "
            "must not cross the current stop boundary automatically."
        )

    rejection_reasons = dict(audit["rows_rejected_by_session_reason"])
    for reason, count in audit["task_occurrence_groups_rejected"].items():
        rejection_reasons[f"task_group:{reason}"] = int(count)
    duplicate_findings = {
        "duplicate_record_ids": int(
            audit["rows_rejected_by_session_reason"].get("duplicate_record_id", 0)
        ),
        "duplicate_session_ids": int(
            audit["rows_rejected_by_session_reason"].get("duplicate_session_id", 0)
        ),
    }
    report = {
        "experiment_version": EXPERIMENT_VERSION,
        "status": NOT_READY,
        "stop_condition": stop_condition,
        "training_started": False,
        "production_inference_changed": False,
        "data_readiness": {
            "real_users": int(summary["real_users_with_outcomes"]),
            "raw_outcome_sessions": int(summary["total_sessions"]),
            "real_outcome_sessions": int(summary["real_outcome_sessions"]),
            "valid_sessions": int(summary["valid_sessions"]),
            "suspicious_sessions": int(summary["suspicious_sessions"]),
            "invalid_sessions": int(summary["invalid_sessions"]),
            "unknown_sessions": int(summary["unknown_sessions"]),
            "completed_task_occurrence_candidates": int(
                summary["real_completed_task_occurrences"]
            ),
            "training_eligible_real_user_rows": eligible_rows,
            "synthetic_rows": int(summary["synthetic_rows"]),
            "dataset_version": audit["dataset_snapshot"]["dataset_version"],
            "dataset_checksum": audit["dataset_snapshot"]["dataset_sha256"],
            "source_export_checksum": audit["source_export_sha256"],
        },
        "failed_gates": _failed_checks(readiness),
        "rejected_rows_by_reason": dict(sorted(rejection_reasons.items())),
        "integrity": {
            "duplicate_findings": duplicate_findings,
            "primary_user_group_split_run": False,
            "secondary_temporal_split_run": False,
            "leakage_status": "NOT EVALUATED — ZERO ELIGIBLE REAL-USER ROWS",
            "leakage_detected": None,
        },
        "models_evaluated": [],
        "cv_results": None,
        "locked_test_results": None,
        "long_task_results": None,
        "phase_1_2_comparison": None,
        "promotion_decision": "NOT EVALUATED",
        "model_status": "NO MODEL TRAINED",
        "artifacts_created": {
            "readiness_report": True,
            "dataset_snapshot": False,
            "metrics_csv": False,
            "metrics_json": False,
            "model_metadata": False,
            "model_artifact": False,
        },
        "privacy": audit["privacy"],
        "note": (
            "Synthetic fixture rows validate the pipeline only. They are excluded from "
            "real-user training and cannot support model metrics or an accuracy claim."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the guarded Phase 5 real-user Duration experiment"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report = run(args.input, args.report)
    print(report["status"])
    print(
        "real_users={real_users} real_sessions={real_outcome_sessions} "
        "eligible_rows={training_eligible_real_user_rows}".format(
            **report["data_readiness"]
        )
    )
    print(f"stop_condition={report['stop_condition']}")
    print(f"report={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
