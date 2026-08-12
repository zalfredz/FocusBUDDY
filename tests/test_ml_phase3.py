"""Contracts for Phase 3 real-user outcome collection and offline building."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import clock, focus_session, storage
from ml.datasets.user_outcomes import build_training_dataset, write_training_dataset
from ml.evaluation.user_outcomes import validate_outcome_records


FIXTURE = ROOT / "ml" / "datasets" / "fixtures" / "user_outcomes_v1.synthetic.json"


def _base_record(**changes):
    record = {
        "schema_version": "focus-outcome-v1",
        "record_id": "record-1",
        "user_id": "c65b233c-4436-47fc-9f46-474dc3523562",
        "task_id": "task-1",
        "session_id": "session-1",
        "task_text": "Tulis laporan",
        "importance": 8,
        "has_deadline": True,
        "deadline_days_or_zero": 1,
        "predicted_duration_minutes": 30,
        "prediction_model_version": "duration-production-legacy-v1",
        "prediction_source": "model",
        "planned_session_minutes": 30,
        "started_at": "2026-08-12T10:00:00+07:00",
        "ended_at": "2026-08-12T10:30:00+07:00",
        "actual_active_duration_minutes": 25,
        "completion_status": "task_completed",
        "outcome": "completed",
        "task_completed": True,
        "task_association_valid": True,
        "timing_quality": "pause_aware_no_visibility_signal",
        "interruption_count": 0,
        "pause_duration_minutes": 0,
        "task_created_at": "2026-08-12T09:00:00+07:00",
        "created_at": "2026-08-12T10:00:00+07:00",
        "data_provenance": "real_user",
        "synthetic": False,
        "is_demo": False,
        "collection_context": "production",
        "data_quality_status": "unknown",
        "data_quality_reason": "pending_offline_validation",
    }
    record.update(changes)
    return record


def _quality(record):
    return validate_outcome_records([record])[0]


def test_valid_completed_session() -> None:
    result = _quality(_base_record())
    assert result["data_quality_status"] == "valid"
    assert result["training_eligible_session"] is True


def test_cancelled_session_is_measured_but_not_a_task_label() -> None:
    result = _quality(
        _base_record(
            completion_status="cancelled",
            outcome="cancelled",
            task_completed=False,
        )
    )
    assert result["data_quality_status"] == "valid"
    assert result["measurement_usable"] is True
    assert result["training_eligible_session"] is False


def test_missing_timestamps_are_not_silently_zeroed() -> None:
    missing_start = _quality(_base_record(started_at=""))
    missing_end = _quality(_base_record(ended_at=""))
    in_progress = _quality(
        _base_record(
            ended_at="",
            actual_active_duration_minutes=None,
            completion_status="started",
            outcome="",
            task_completed=False,
        )
    )
    assert missing_start["data_quality_status"] == "invalid"
    assert missing_end["data_quality_status"] == "invalid"
    assert in_progress["data_quality_status"] == "unknown"
    assert in_progress["actual_active_duration_minutes"] is None


def test_negative_and_impossible_duration_are_invalid() -> None:
    negative = _quality(_base_record(actual_active_duration_minutes=-1))
    impossible = _quality(
        _base_record(
            ended_at="2026-08-14T12:00:00+07:00",
            actual_active_duration_minutes=1_500,
        )
    )
    assert negative["data_quality_status"] == "invalid"
    assert "non_positive" in negative["data_quality_reason"]
    assert impossible["data_quality_status"] == "invalid"
    assert "impossible" in impossible["data_quality_reason"]


def test_duplicate_session_marks_every_copy_invalid() -> None:
    first = _base_record(record_id="record-a")
    second = _base_record(record_id="record-b")
    results = validate_outcome_records([first, second])
    assert all(row["data_quality_status"] == "invalid" for row in results)
    assert all("duplicate_session_id" in row["data_quality_reason"] for row in results)


def test_missing_prediction_and_model_version_are_invalid() -> None:
    no_prediction = _quality(_base_record(predicted_duration_minutes=None))
    no_version = _quality(_base_record(prediction_model_version=""))
    assert no_prediction["data_quality_status"] == "invalid"
    assert "missing_or_invalid_prediction" in no_prediction["data_quality_reason"]
    assert no_version["data_quality_status"] == "invalid"
    assert "missing_prediction_model_version" in no_version["data_quality_reason"]


def test_task_session_relationship_and_quality_classes() -> None:
    mismatch = _quality(_base_record(task_association_valid=False))
    suspicious = _quality(
        _base_record(
            ended_at="2026-08-12T20:00:00+07:00",
            actual_active_duration_minutes=600,
        )
    )
    unknown = _quality(
        _base_record(
            ended_at="",
            actual_active_duration_minutes=None,
            completion_status="crashed",
            outcome="",
            task_completed=False,
        )
    )
    assert mismatch["data_quality_status"] == "invalid"
    assert suspicious["data_quality_status"] == "suspicious"
    assert unknown["data_quality_status"] == "unknown"


def test_dataset_generation_aggregates_sessions_and_blocks_synthetic_training() -> None:
    fixture_rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    synthetic = build_training_dataset(
        fixture_rows, allow_synthetic_for_testing=True
    )
    assert len(synthetic.records) == 1
    row = synthetic.records[0]
    assert row["actual_active_duration_minutes"] == 30
    assert row["source_session_ids"] == [
        "synthetic-session-001",
        "synthetic-session-002",
    ]
    assert row["synthetic"] is True
    assert row["training_eligible"] is False

    real_rows = copy.deepcopy(fixture_rows)
    real_rows[0]["user_id"] = "c65b233c-4436-47fc-9f46-474dc3523562"
    real_rows[0]["state"]["tasks"][0]["data_provenance"] = "real_user"
    for record in real_rows[0]["state"]["ml_outcome_records"]:
        record["data_provenance"] = "real_user"
        record["collection_context"] = "setting_demo"
        record["synthetic"] = False
    real = build_training_dataset(real_rows)
    assert len(real.records) == 1
    assert real.records[0]["training_eligible"] is True
    assert real.audit["real_training_eligible_count"] == 1


def test_dataset_generation_accepts_serialized_supabase_state_and_is_reproducible() -> None:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows[0]["state"] = json.dumps(rows[0]["state"])
    first = build_training_dataset(rows, allow_synthetic_for_testing=True)
    second = build_training_dataset(rows, allow_synthetic_for_testing=True)
    assert first.records == second.records
    assert first.audit["sha256"] == second.audit["sha256"]
    assert first.records[0]["task_family_id"].startswith("synthetic-user-001:")

    with tempfile.TemporaryDirectory(prefix="focusbuddy_phase3_export_") as directory:
        csv_path = Path(directory) / "outcomes.csv"
        json_path = Path(directory) / "outcomes.json"
        write_training_dataset(first, csv_path, json_path)
        assert csv_path.exists() and json_path.exists()
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["dataset_version"].startswith(
            "focusbuddy-user-outcomes-v1-sha256-"
        )


def test_runtime_collection_is_pause_aware_and_persists_prediction_provenance() -> None:
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    with tempfile.TemporaryDirectory(prefix="focusbuddy_phase3_runtime_") as directory:
        storage.DATA_DIR = Path(directory)
        storage.DATA_FILE = storage.DATA_DIR / "data.json"
        storage.BACKUP_FILE = storage.DATA_DIR / "data.json.bak"
        try:
            state = storage.reset_all_data()
            state["profile"].update({"name": "Ari", "onboarded": True})
            storage.save_state(state)
            task = storage.add_task(
                "Kerjakan 10 soal",
                clock.today().isoformat(),
                steps=[{"id": "step-1", "text": "Kerjakan soal pertama", "done": False}],
                menit_est=30,
                prediction_model_version="duration-production-legacy-v1",
                prediction_source="model",
                prediction_importance=8,
                prediction_deadline_days=0,
            )
            focus_session.start(
                30,
                label="Kerjakan soal pertama",
                task_title=task["title"],
                task_id=task["id"],
                step_id="step-1",
                step_index=0,
                task_estimate_minutes=30,
            )
            internal = focus_session._state()
            internal.ends_at = datetime.now() + timedelta(minutes=20)
            focus_session.pause()
            internal.paused_at = datetime.now() - timedelta(minutes=5)
            focus_session.resume()
            internal.ends_at = datetime.now() + timedelta(minutes=10)
            focus_session.finish("completed")

            outcomes = storage.get_focus_outcome_records()
            assert len(outcomes) == 1
            outcome = outcomes[0]
            assert outcome["session_id"]
            assert outcome["prediction_model_version"] == "duration-production-legacy-v1"
            assert outcome["predicted_duration_minutes"] == 30
            assert outcome["interruption_count"] == 1
            assert 4.9 <= outcome["pause_duration_minutes"] <= 5.1
            assert 19.9 <= outcome["actual_active_duration_minutes"] <= 20.1
            assert outcome["task_completed"] is True
        finally:
            focus_session.stop()
            storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original


def test_phase3_collection_introduces_no_training_or_new_ml_runtime_dependency() -> None:
    production_sources = [
        ROOT / "app" / "focus_session.py",
        ROOT / "app" / "storage.py",
        ROOT / "app" / "views" / "tracker.py",
    ]
    for path in production_sources:
        source = path.read_text(encoding="utf-8")
        assert ".fit(" not in source
        assert "tensorflow" not in source.casefold()
        assert "tflite" not in source.casefold()
        assert "from ml." not in source
        assert "import ml." not in source


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"OK: {len(tests)} Phase 3 ML tests")
