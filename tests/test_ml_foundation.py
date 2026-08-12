"""Unit tests untuk fondasi training/evaluation offline."""
from __future__ import annotations

import sys
import json
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.datasets.duration import DurationRecord, load_duration_dataset
from ml.datasets.duration_clean import load_clean_duration_dataset
from ml.evaluation.metrics import (
    classification_metrics,
    regression_metrics,
    retrieval_metrics,
)
from ml.evaluation.splits import split_group_supervised, split_supervised
from ml.registry.metadata import ModelMetadata
from ml.training.duration import candidate_specs, fit_duration_candidate
from ml.training.guard import OfflineTrainingRequired, offline_training_session
from ml.training.duration_clean import feature_configs, fit_clean_duration_candidate


def test_duration_manifest_and_split() -> None:
    dataset = load_duration_dataset()
    assert len(dataset.records) == 549
    targets = [record.duration_minutes for record in dataset.records]
    first = split_supervised(
        dataset.records, targets, classification=False, random_seed=42
    )
    second = split_supervised(
        dataset.records, targets, classification=False, random_seed=42
    )
    assert len(first.train_items) == 439
    assert len(first.test_items) == 110
    assert first.train_indices == second.train_indices
    assert first.test_indices == second.test_indices
    assert not set(first.train_indices) & set(first.test_indices)


def test_classification_split_uses_stratification() -> None:
    items = list(range(20))
    labels = [0] * 10 + [1] * 10
    split = split_supervised(items, labels, classification=True, random_seed=42)
    assert split.stratified is True
    assert split.test_targets.count(0) == 2
    assert split.test_targets.count(1) == 2


def test_metrics_contracts() -> None:
    regression = regression_metrics([100, 200], [110, 180])
    assert set(regression) == {
        "mae",
        "rmse",
        "r2",
        "median_absolute_error",
        "within_10_percent",
        "within_20_percent",
        "within_30_percent",
    }
    classification = classification_metrics(
        [0, 0, 1, 1], [0, 1, 1, 1], probabilities=[0.1, 0.6, 0.8, 0.9]
    )
    assert classification["accuracy"] == 0.75
    assert classification["roc_auc"] is not None
    retrieval = retrieval_metrics(
        ["a", "b"], [["a", "x"], ["x", "b"]], accepted=[True, False]
    )
    assert retrieval == {
        "top_1": 0.5,
        "top_3": 1.0,
        "mrr": 0.75,
        "coverage": 0.5,
        "fallback_rate": 0.5,
    }


def test_training_guard_and_train_only_preprocessing() -> None:
    records = [
        DurationRecord(f"tugas latihan {index}", float(index), 5.0, 10.0 + index)
        for index in range(12)
    ]
    spec = candidate_specs()[0]
    try:
        fit_duration_candidate(spec, records)
    except OfflineTrainingRequired:
        pass
    else:
        raise AssertionError("Training tanpa offline session harus ditolak")

    with offline_training_session():
        artifact, _ = fit_duration_candidate(spec, records)
    assert "token_test_yang_tidak_pernah_masuk" not in artifact.vectorizer.vocabulary_


def test_metadata_requires_experimental_status() -> None:
    metadata = ModelMetadata(
        model_name="duration",
        model_version="duration-test-v1",
        dataset_version="dataset-v1",
        feature_schema={"x": "number"},
        training_row_count=8,
        test_row_count=2,
        training_timestamp="2026-08-12T00:00:00+00:00",
        random_seed=42,
        hyperparameters={},
        metrics={"mae": 1.0},
        framework="scikit-learn",
        framework_version="test",
        artifact_path="ml/registry/artifacts/duration-test-v1.joblib",
    )
    metadata.validate()


def test_generated_duration_experiment_contract() -> None:
    report_path = ROOT / "reports" / "duration_baseline.json"
    metadata_path = ROOT / "ml" / "registry" / "metadata" / "duration-baseline-v1.json"
    artifact_path = ROOT / "ml" / "registry" / "artifacts" / "duration-baseline-v1.joblib"
    if not (report_path.exists() and metadata_path.exists() and artifact_path.exists()):
        return

    report = json.loads(report_path.read_text(encoding="utf-8"))
    candidates = report["candidates"]
    selected = [candidate for candidate in candidates if candidate["selected_by_cv"]]
    tested = [candidate for candidate in candidates if candidate["locked_test_metrics"]]
    assert len(selected) == 1
    assert tested == selected
    assert selected[0]["cv_metrics"]["cv_rmse_mean"] == min(
        candidate["cv_metrics"]["cv_rmse_mean"] for candidate in candidates
    )
    assert report["selected_model"]["production_ready"] is False

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["status"] == "experimental"
    assert metadata["metrics"]["performance"]["model_size_bytes"] == artifact_path.stat().st_size
    artifact = joblib.load(artifact_path)
    assert artifact.metadata["model_version"] == metadata["model_version"]


def test_production_does_not_import_offline_training_package() -> None:
    for folder in (ROOT / "app", ROOT / "models"):
        for path in folder.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "from ml." not in source
            assert "import ml." not in source


def test_clean_duration_manifest_deadline_and_group_split() -> None:
    dataset = load_clean_duration_dataset()
    assert len(dataset.records) == 549
    assert dataset.validation["target"]["meaning"] == "human_estimated_duration"
    assert dataset.validation["target"]["over_600_count"] == 6
    assert dataset.validation["label_review_needed_count"] == 2
    assert all(
        record.deadline_days is None
        for record in dataset.records
        if not record.has_deadline
    )
    split = split_group_supervised(
        dataset.records,
        [record.estimated_duration_minutes for record in dataset.records],
        [record.source_group_id for record in dataset.records],
        random_seed=42,
    )
    assert not split.overlapping_groups
    repeated = split_group_supervised(
        dataset.records,
        [record.estimated_duration_minutes for record in dataset.records],
        [record.source_group_id for record in dataset.records],
        random_seed=42,
    )
    assert split.train_indices == repeated.train_indices
    assert split.test_indices == repeated.test_indices


def test_clean_deadline_encoding_disambiguates_none_from_today() -> None:
    dataset = load_clean_duration_dataset()
    without_deadline = next(record for record in dataset.records if not record.has_deadline)
    deadline_today = next(
        record
        for record in dataset.records
        if record.has_deadline and record.deadline_days == 0
    )
    config = feature_configs(dataset.columns)[0][1]
    spec = candidate_specs()[0]
    with offline_training_session():
        artifact, _ = fit_clean_duration_candidate(
            spec, list(dataset.records[:30]), config, "raw"
        )
    matrix = artifact.preprocessor.transform([without_deadline, deadline_today])
    numeric = matrix[:, -3:]
    assert numeric[0, 0] == 0 and numeric[0, 1] == 0
    assert numeric[1, 0] == 1 and numeric[1, 1] == 0


def test_structured_experiment_is_skipped_when_columns_absent() -> None:
    dataset = load_clean_duration_dataset()
    configs, skipped = feature_configs(dataset.columns)
    assert [config.name for config in configs] == ["phase0_original", "clean_deadline"]
    assert skipped and skipped[0]["experiment"] == "clean_deadline_structured"


def test_generated_clean_experiment_contract() -> None:
    report_path = ROOT / "reports" / "duration-clean-v2.json"
    metadata_path = ROOT / "ml" / "registry" / "metadata" / "duration-clean-v2.json"
    artifact_path = ROOT / "ml" / "registry" / "artifacts" / "duration-clean-v2.joblib"
    if not (report_path.exists() and metadata_path.exists() and artifact_path.exists()):
        return
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["experiment"]["selection_uses_locked_test"] is False
    assert report["experiment"]["split"]["overlapping_groups"] == 0
    winners = report["configuration_winners"]
    assert len(winners) == 4
    assert all(winner["locked_test_metrics"] for winner in winners)
    final = [result for result in report["all_candidates"] if result["selected_final_by_cv"]]
    assert len(final) == 1
    assert final[0]["cv_metrics"]["cv_rmse_mean"] == min(
        winner["cv_metrics"]["cv_rmse_mean"] for winner in winners
    )
    assert report["selected_model"]["production_ready"] is False
    assert report["decomposition_validation"]["retrieval_benchmark"]["run"] is False
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["status"] == "experimental"
    assert metadata["metrics"]["performance"]["model_size_bytes"] == artifact_path.stat().st_size
    artifact = joblib.load(artifact_path)
    assert artifact.metadata["model_version"] == "duration-clean-v2"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"OK: {len(tests)} ML foundation tests")
