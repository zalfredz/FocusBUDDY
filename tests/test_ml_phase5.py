"""Contracts for the guarded Phase 5 real-user retraining experiment."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.experiments.real_user_duration_v1 import NOT_READY, run


FIXTURE = ROOT / "ml" / "datasets" / "fixtures" / "user_outcomes_v1.synthetic.json"


def _run_in_temp():
    directory = tempfile.TemporaryDirectory(prefix="focusbuddy_phase5_")
    root = Path(directory.name)
    report_path = root / "phase5-report.json"
    report = run(FIXTURE, report_path)
    return directory, report_path, report


def test_zero_real_rows_triggers_critical_stop() -> None:
    directory, _, report = _run_in_temp()
    try:
        assert report["status"] == NOT_READY
        assert report["stop_condition"] == "no_real_user_training_eligible_data"
        assert report["training_started"] is False
        assert report["data_readiness"]["real_users"] == 0
        assert report["data_readiness"]["real_outcome_sessions"] == 0
        assert report["data_readiness"]["training_eligible_real_user_rows"] == 0
        assert report["data_readiness"]["synthetic_rows"] == 2
    finally:
        directory.cleanup()


def test_stop_report_names_exact_failed_gates() -> None:
    directory, _, report = _run_in_temp()
    try:
        assert "dataset_level_training_gate.eligible_occurrences" in report["failed_gates"]
        assert "dataset_level_training_gate.eligible_users" in report["failed_gates"]
        assert "global_retraining_gate.eligible_occurrences" in report["failed_gates"]
        assert report["rejected_rows_by_reason"] == {"task_group:synthetic": 1}
    finally:
        directory.cleanup()


def test_no_split_metrics_or_model_artifact_are_fabricated() -> None:
    directory, report_path, report = _run_in_temp()
    try:
        assert report["integrity"]["primary_user_group_split_run"] is False
        assert report["integrity"]["secondary_temporal_split_run"] is False
        assert report["integrity"]["leakage_detected"] is None
        assert report["models_evaluated"] == []
        assert report["cv_results"] is None
        assert report["locked_test_results"] is None
        assert report["promotion_decision"] == "NOT EVALUATED"
        assert report["model_status"] == "NO MODEL TRAINED"
        assert all(
            value is False
            for key, value in report["artifacts_created"].items()
            if key != "readiness_report"
        )
        assert sorted(path.name for path in report_path.parent.iterdir()) == [
            "phase5-report.json"
        ]
    finally:
        directory.cleanup()


def test_phase5_report_is_reproducible_and_contains_no_pii() -> None:
    with tempfile.TemporaryDirectory(prefix="focusbuddy_phase5_repro_") as directory:
        root = Path(directory)
        first_path = root / "first.json"
        second_path = root / "second.json"
        first = run(FIXTURE, first_path)
        second = run(FIXTURE, second_path)
        assert first == second
        assert first_path.read_bytes() == second_path.read_bytes()
        serialized = json.dumps(first, ensure_ascii=False)
        assert "synthetic-user-001" not in serialized
        assert "Kerjakan latihan kalkulus" not in serialized
        assert first["privacy"]["contains_user_ids"] is False
        assert first["privacy"]["contains_raw_task_text"] is False


def test_phase5_controller_contains_no_training_call() -> None:
    source = (
        ROOT / "ml" / "experiments" / "real_user_duration_v1.py"
    ).read_text(encoding="utf-8")
    assert ".fit(" not in source
    assert "offline_training_session" not in source
    assert "persist_experimental_model" not in source
    assert "tensorflow" not in source.casefold()
    assert "tflite" not in source.casefold()


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"OK: {len(tests)} Phase 5 ML tests")
