"""Contracts for Phase 4 real-user audit and retraining design."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.datasets.user_outcomes import build_training_dataset
from ml.evaluation.model_promotion import evaluate_promotion
from ml.evaluation.real_user_data_audit import audit_export_rows, run
from ml.evaluation.real_user_readiness import NOT_READY
from ml.evaluation.real_user_splits import (
    leakage_report,
    temporal_holdout,
    user_group_holdout,
)


FIXTURE = ROOT / "ml" / "datasets" / "fixtures" / "user_outcomes_v1.synthetic.json"


def _fixture_rows():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _split_record(user: int, family: int, *, day: int = 0) -> dict:
    ended = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        days=day or family
    )
    return {
        "record_id": f"record-{user}-{family}",
        "user_id": f"private-user-{user}",
        "task_id": f"task-{user}-{family}",
        "task_family_id": f"family-{user}-{family}",
        "session_id": f"session-{user}-{family}",
        "source_session_ids": [f"source-session-{user}-{family}"],
        "actual_active_duration_minutes": 20 + family,
        "ended_at": ended.isoformat(),
    }


def _promotion_evidence(**changes):
    evidence = {
        "real_user_dataset_gate_passed": True,
        "locked_test_was_untouched_until_selection": True,
        "reproducible_run": True,
        "dataset_version": "real-v1-sha256-abc",
        "model_version": "duration-real-v1",
        "feature_schema_compatible": True,
        "baseline_is_comparable": True,
    }
    evidence.update(changes)
    return evidence


def _metrics(cv: float, rmse: float, mae: float, long_rmse: float) -> dict:
    return {
        "cv_rmse": cv,
        "locked_test": {"rmse": rmse, "mae": mae},
        "slices": {"over_300_minutes": {"rmse": long_rmse}},
    }


def test_synthetic_data_is_excluded_and_report_is_pii_safe() -> None:
    rows = _fixture_rows()
    report = audit_export_rows(rows, source_sha256="fixture-sha")
    assert report["summary"]["synthetic_rows"] == 2
    assert report["summary"]["training_eligible_task_occurrences"] == 0
    assert report["real_user_retraining_status"] == NOT_READY
    assert report["privacy"] == {
        "contains_raw_task_text": False,
        "contains_user_ids": False,
        "contains_names_or_emails": False,
    }
    serialized = json.dumps(report, ensure_ascii=False)
    assert "synthetic-user-001" not in serialized
    assert "Kerjakan latihan kalkulus" not in serialized


def test_invalid_and_unknown_sessions_are_excluded() -> None:
    rows = _fixture_rows()
    rows[0]["user_id"] = "c65b233c-4436-47fc-9f46-474dc3523562"
    rows[0]["state"]["tasks"][0]["data_provenance"] = "real_user"
    first, second = rows[0]["state"]["ml_outcome_records"]
    for record in (first, second):
        record["data_provenance"] = "real_user"
        record["collection_context"] = "setting_demo"
        record["synthetic"] = False
    first["ended_at"] = ""
    first["actual_active_duration_minutes"] = None
    first["completion_status"] = "started"
    second["actual_active_duration_minutes"] = -4
    report = audit_export_rows(rows)
    assert report["summary"]["unknown_sessions"] == 1
    assert report["summary"]["invalid_sessions"] == 1
    assert report["summary"]["training_eligible_task_occurrences"] == 0
    assert report["real_user_retraining_status"] == NOT_READY


def test_completed_task_aggregation_preserves_session_audit_ids() -> None:
    rows = _fixture_rows()
    rows[0]["user_id"] = "c65b233c-4436-47fc-9f46-474dc3523562"
    rows[0]["state"]["tasks"][0]["data_provenance"] = "real_user"
    for record in rows[0]["state"]["ml_outcome_records"]:
        record["data_provenance"] = "real_user"
        record["collection_context"] = "setting_demo"
        record["synthetic"] = False
    dataset = build_training_dataset(rows)
    assert len(dataset.records) == 1
    candidate = dataset.records[0]
    assert candidate["actual_active_duration_minutes"] == 30
    assert candidate["source_session_ids"] == [
        "synthetic-session-001",
        "synthetic-session-002",
    ]
    assert candidate["training_eligible"] is True


def test_user_group_split_has_no_user_task_or_session_leakage() -> None:
    records = [_split_record(user, family) for user in range(6) for family in range(3)]
    split = user_group_holdout(records, random_seed=42)
    assert split.clean
    assert split.strategy == "user_group_holdout"
    assert set(split.train_indices).isdisjoint(split.test_indices)
    train_users = {records[index]["user_id"] for index in split.train_indices}
    test_users = {records[index]["user_id"] for index in split.test_indices}
    assert train_users.isdisjoint(test_users)


def test_temporal_split_uses_later_whole_task_families() -> None:
    records = [_split_record(user, family) for user in range(3) for family in range(5)]
    split = temporal_holdout(records, test_fraction=0.20)
    assert split.clean
    assert split.strategy == "temporal_task_family_holdout"
    for user in range(3):
        train_days = [
            records[index]["ended_at"]
            for index in split.train_indices
            if records[index]["user_id"] == f"private-user-{user}"
        ]
        test_days = [
            records[index]["ended_at"]
            for index in split.test_indices
            if records[index]["user_id"] == f"private-user-{user}"
        ]
        assert train_days and test_days and max(train_days) < min(test_days)


def test_leakage_detector_finds_same_task_and_source_session() -> None:
    records = [_split_record(0, 0), _split_record(1, 1)]
    records[1]["task_id"] = records[0]["task_id"]
    records[1]["source_session_ids"] = records[0]["source_session_ids"]
    leakage = leakage_report(records, [0], [1])
    assert leakage["task_id"] == (records[0]["task_id"],)
    assert leakage["source_session_id"] == (
        records[0]["source_session_ids"][0],
    )


def test_dataset_version_is_content_addressed_and_reproducible() -> None:
    rows = _fixture_rows()
    rows[0]["user_id"] = "c65b233c-4436-47fc-9f46-474dc3523562"
    rows[0]["state"]["tasks"][0]["data_provenance"] = "real_user"
    for record in rows[0]["state"]["ml_outcome_records"]:
        record["data_provenance"] = "real_user"
        record["collection_context"] = "setting_demo"
        record["synthetic"] = False
    first = build_training_dataset(rows)
    second = build_training_dataset(copy.deepcopy(rows))
    assert first.version == second.version
    assert first.audit["sha256"] == second.audit["sha256"]
    assert all(row["dataset_version"] == first.version for row in first.records)

    changed = copy.deepcopy(rows)
    changed[0]["state"]["ml_outcome_records"][0][
        "actual_active_duration_minutes"
    ] = 11
    third = build_training_dataset(changed)
    assert third.version != first.version
    assert third.audit["sha256"] != first.audit["sha256"]


def test_cv_improvement_alone_does_not_pass_promotion_gate() -> None:
    baseline = _metrics(100, 100, 70, 300)
    candidate = _metrics(95, 103, 69, 295)
    result = evaluate_promotion(
        candidate=candidate,
        baseline=baseline,
        evidence=_promotion_evidence(),
    )
    assert result["metric_checks"]["cv_rmse_improvement"] is True
    assert result["metric_checks"]["locked_rmse_improvement"] is False
    assert result["accepted_for_manual_promotion_review"] is False
    assert result["recommendation"] == "KEEP EXISTING MODEL"


def test_promotion_requires_slices_versions_and_manual_review() -> None:
    baseline = _metrics(100, 100, 70, 300)
    candidate = _metrics(96, 96, 68, 310)
    accepted = evaluate_promotion(
        candidate=candidate,
        baseline=baseline,
        evidence=_promotion_evidence(),
    )
    assert accepted["accepted_for_manual_promotion_review"] is True
    assert accepted["automatic_promotion"] is False

    regressed = evaluate_promotion(
        candidate=_metrics(96, 96, 68, 340),
        baseline=baseline,
        evidence=_promotion_evidence(),
    )
    assert regressed["metric_checks"]["no_major_slice_regression"] is False
    assert regressed["accepted_for_manual_promotion_review"] is False

    missing_version = evaluate_promotion(
        candidate=candidate,
        baseline=baseline,
        evidence=_promotion_evidence(dataset_version=""),
    )
    assert missing_version["evidence_checks"]["dataset_version_present"] is False
    assert missing_version["accepted_for_manual_promotion_review"] is False


def test_offline_audit_command_is_reproducible() -> None:
    with tempfile.TemporaryDirectory(prefix="focusbuddy_phase4_audit_") as directory:
        root = Path(directory)
        source = root / "supabase-export.json"
        first_output = root / "audit-1.json"
        second_output = root / "audit-2.json"
        source.write_text(
            json.dumps(_fixture_rows(), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        first = run(source, first_output)
        second = run(source, second_output)
        assert first == second
        assert first_output.read_bytes() == second_output.read_bytes()
        assert first["real_user_retraining_status"] == NOT_READY


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"OK: {len(tests)} Phase 4 ML tests")
