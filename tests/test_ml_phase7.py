"""Phase 7 real-data collection and personalization validation contracts."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import clock, config, focus_session, storage
from ml.datasets.user_outcomes import build_training_dataset
from ml.evaluation.personalization_validation import (
    NOT_READY,
    READY,
    evaluate_duration_personalization,
)
from ml.evaluation.real_user_data_audit import audit_export_rows
from ml.evaluation.user_outcomes import validate_outcome_records
from ml.experiments.phase7_real_user_validation import run


AUTH_A = "c65b233c-4436-47fc-9f46-474dc3523562"
AUTH_B = "9a74c355-29e5-4c40-820c-26cd77423139"
FIXTURE = ROOT / "ml" / "datasets" / "fixtures" / "user_outcomes_v1.synthetic.json"


def _temporary_storage():
    directory = tempfile.TemporaryDirectory(prefix="focusbuddy_phase7_")
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    root = Path(directory.name)
    storage.DATA_DIR = root
    storage.DATA_FILE = root / "data.json"
    storage.BACKUP_FILE = root / "data.json.bak"
    return directory, original


def _candidate(
    user_id: str,
    index: int,
    ratio: float,
    *,
    holdout_ratio: float | None = None,
) -> dict:
    actual_ratio = holdout_ratio if holdout_ratio is not None and index >= 30 else ratio
    ended = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
    return {
        "record_id": f"record-{user_id}-{index}",
        "user_id": user_id,
        "task_id": f"task-{user_id}-{index}",
        "task_family_id": f"family-{user_id}-{index}",
        "session_id": f"session-{user_id}-{index}",
        "source_session_ids": [f"session-{user_id}-{index}"],
        "occurrence_date": ended.date().isoformat(),
        "task_text": "restricted raw task text",
        "category": ("soal", "nulis", "baca")[index % 3],
        "predicted_duration_minutes": 100,
        "global_prediction_minutes": 100,
        "prediction_model_version": "duration-global-test-v1",
        "global_model_version": "duration-global-test-v1",
        "actual_active_duration_minutes": 100 * actual_ratio,
        "ended_at": ended.isoformat(),
        "completion_status": "task_completed",
        "data_quality_status": "valid",
        "data_provenance": "real_user",
        "synthetic": False,
        "training_eligible": True,
    }


def _real_fixture_rows() -> list[dict]:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows[0]["user_id"] = AUTH_A
    rows[0]["state"]["tasks"][0]["data_provenance"] = "real_user"
    for record in rows[0]["state"]["ml_outcome_records"]:
        record["data_provenance"] = "real_user"
        record["collection_context"] = "setting_demo"
        record["synthetic"] = False
    return rows


def test_runtime_focus_record_contains_complete_phase7_instrumentation() -> None:
    directory, original = _temporary_storage()
    original_demo_mode = config.DEMO_MODE
    try:
        config.DEMO_MODE = True
        storage.reset_all_data()
        task = storage.add_task(
            "Kerjakan latihan",
            clock.today().isoformat(),
            steps=[{"id": "step-1", "text": "Buka soal", "done": False}],
            menit_est=30,
            prediction_model_version="duration-test-v1",
            prediction_source="global_model",
            prediction_importance=8,
            prediction_deadline_days=0,
            prediction_global_minutes=30,
            prediction_global_model_version="duration-test-v1",
        )
        focus_session.start(
            1,
            task_title=task["title"],
            task_id=task["id"],
            step_id="step-1",
            step_index=0,
        )
        focus_session._state().ends_at = datetime.now() + timedelta(seconds=58)
        focus_session.finish("completed")
        outcome = storage.get_focus_outcome_records()[-1]
        required = {
            "session_id",
            "task_id",
            "step_id",
            "task_text",
            "predicted_duration_minutes",
            "prediction_model_version",
            "prediction_source",
            "importance",
            "has_deadline",
            "deadline_days_or_zero",
            "planned_session_minutes",
            "actual_active_duration_minutes",
            "pause_duration_minutes",
            "interruption_count",
            "completion_status",
            "task_completed",
            "outcome",
            "started_at",
            "ended_at",
            "data_quality_status",
            "data_quality_reason",
            "data_provenance",
            "collection_context",
            "synthetic",
        }
        assert required <= set(outcome)
        assert outcome["data_provenance"] == "real_user"
        assert outcome["collection_context"] == "setting_demo"
        assert outcome["synthetic"] is False
        assert "user_id" not in outcome
    finally:
        focus_session.stop()
        config.DEMO_MODE = original_demo_mode
        storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original
        directory.cleanup()


def test_offline_validation_requires_phase7_prediction_context() -> None:
    rows = _real_fixture_rows()
    joined = build_training_dataset(rows)
    assert len(joined.records) == 1

    raw = rows[0]["state"]["ml_outcome_records"][0]
    envelope_fields = {
        **raw,
        "user_id": AUTH_A,
        "task_association_valid": True,
    }
    for field in (
        "prediction_source",
        "planned_session_minutes",
        "collection_context",
        "data_quality_reason",
    ):
        broken = dict(envelope_fields)
        broken[field] = "" if field != "planned_session_minutes" else 0
        validated = validate_outcome_records([broken])[0]
        assert validated["data_quality_status"] == "invalid"


def test_real_readiness_counts_exclude_synthetic_and_legacy_rows() -> None:
    synthetic_rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    report = audit_export_rows(synthetic_rows)
    assert report["summary"]["real_outcome_sessions"] == 0
    assert report["summary"]["real_valid_sessions"] == 0
    assert report["summary"]["synthetic_rows"] == 2

    legacy = copy.deepcopy(synthetic_rows)
    legacy[0]["state"]["tasks"][0].pop("data_provenance", None)
    for record in legacy[0]["state"]["ml_outcome_records"]:
        record.pop("data_provenance", None)
        record["synthetic"] = False
    legacy_report = audit_export_rows(legacy)
    assert legacy_report["summary"]["real_outcome_sessions"] == 0
    assert legacy_report["summary"]["real_users_with_outcomes"] == 0


def test_multi_session_group_rejects_changed_prediction_provenance() -> None:
    rows = _real_fixture_rows()
    rows[0]["state"]["ml_outcome_records"][1][
        "global_model_version"
    ] = "duration-other-v2"
    dataset = build_training_dataset(rows)
    assert dataset.records == ()
    assert dataset.audit["rejected_groups"] == {
        "inconsistent_prediction_provenance": 1
    }


def test_personalization_evaluation_is_user_specific_and_temporal() -> None:
    rows = [
        *[_candidate(AUTH_A, index, 1.4) for index in range(36)],
        *[_candidate(AUTH_B, index, 0.7) for index in range(36)],
    ]
    report = evaluate_duration_personalization(
        rows, dataset_version="phase7-test-v1"
    )
    assert report["status"] == READY
    assert report["summary"]["users_ready_for_temporal_evaluation"] == 2
    assert {row["calibration_factor"] for row in report["per_user"]} == {0.7, 1.4}
    assert all(row["history_outcomes"] == 30 for row in report["per_user"])
    assert all(row["holdout_outcomes"] == 6 for row in report["per_user"])
    assert all(row["personalization_improved_mae"] for row in report["per_user"])
    serialized = json.dumps(report, ensure_ascii=False)
    assert AUTH_A not in serialized and AUTH_B not in serialized
    assert "restricted raw task text" not in serialized


def test_future_outcomes_never_change_prior_calibration() -> None:
    rows = [
        _candidate(AUTH_A, index, 1.2, holdout_ratio=2.0)
        for index in range(36)
    ]
    report = evaluate_duration_personalization(
        rows, dataset_version="phase7-temporal-test-v1"
    )
    assert report["status"] == READY
    result = report["per_user"][0]
    assert result["calibration_factor"] == 1.2
    assert result["history_outcomes"] == 30
    assert result["holdout_outcomes"] == 6


def test_phase7_controller_stops_cleanly_without_real_data() -> None:
    with tempfile.TemporaryDirectory(prefix="focusbuddy_phase7_reports_") as directory:
        report_dir = Path(directory)
        stale = report_dir / "personalization_evaluation.json"
        stale.write_text("stale", encoding="utf-8")
        result = run(
            FIXTURE,
            report_dir,
            input_scope="synthetic_fixture_pipeline_validation",
        )
        real = result["real_user_data"]
        personal = result["personalization_readiness"]
        assert real["real_user_data_status"] == "NOT READY"
        assert real["personalization_status"] == NOT_READY
        assert real["global_retraining_status"] == "NOT READY"
        assert real["summary"]["real_users_detected"] == 0
        assert real["summary"]["real_sessions_detected"] == 0
        assert real["summary"]["valid_sessions"] == 0
        assert real["summary"]["synthetic_sessions_excluded"] == 2
        assert personal["evaluation_created"] is False
        assert result["personalization_evaluation"] is None
        assert not stale.exists()
        assert (report_dir / "real_user_data_readiness.json").exists()
        assert (report_dir / "personalization_readiness.json").exists()


def test_phase7_adds_no_training_or_production_dependency() -> None:
    sources = [
        ROOT / "ml" / "evaluation" / "personalization_validation.py",
        ROOT / "ml" / "experiments" / "phase7_real_user_validation.py",
    ]
    for path in sources:
        source = path.read_text(encoding="utf-8")
        assert ".fit(" not in source
        assert "tensorflow" not in source.casefold()
        assert "tflite" not in source.casefold()

    production_sources = [
        *list((ROOT / "app").rglob("*.py")),
        *list((ROOT / "models").rglob("*.py")),
    ]
    for path in production_sources:
        source = path.read_text(encoding="utf-8")
        assert "phase7_real_user_validation" not in source
        assert "personalization_validation" not in source


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"OK: {len(tests)} Phase 7 ML tests")
