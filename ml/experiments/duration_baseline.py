"""Baseline ilmiah Duration: CV pada train, lalu satu locked-test evaluation."""
from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn

from ml.datasets.duration import DurationRecord, load_duration_dataset
from ml.evaluation.benchmark import benchmark_serialized_artifact
from ml.evaluation.metrics import regression_metrics
from ml.evaluation.splits import make_cross_validator, split_supervised
from ml.registry.metadata import ModelMetadata, persist_experimental_model
from ml.training.duration import (
    FEATURE_SCHEMA,
    CandidateSpec,
    candidate_specs,
    fit_duration_candidate,
)
from ml.training.guard import offline_training_session


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports"
MODEL_NAME = "duration"
MODEL_VERSION = "duration-baseline-v1"
RANDOM_SEED = 42
TEST_FRACTION = 0.20
CV_FOLDS = 5


def _mean_std(fold_metrics: list[dict[str, float]]) -> dict[str, float]:
    summary: dict[str, float] = {}
    for key in fold_metrics[0]:
        values = [fold[key] for fold in fold_metrics]
        summary[f"cv_{key}_mean"] = float(np.mean(values))
        summary[f"cv_{key}_std"] = float(np.std(values))
    return summary


def _cross_validate(
    spec: CandidateSpec, train_records: list[DurationRecord]
) -> tuple[dict[str, float], float]:
    targets = [record.duration_minutes for record in train_records]
    cv = make_cross_validator(
        targets, classification=False, folds=CV_FOLDS, random_seed=RANDOM_SEED
    )
    indices = np.arange(len(train_records))
    fold_metrics: list[dict[str, float]] = []
    started = time.perf_counter()
    for train_idx, validation_idx in cv.split(indices):
        fold_train = [train_records[int(index)] for index in train_idx]
        fold_validation = [train_records[int(index)] for index in validation_idx]
        artifact, _ = fit_duration_candidate(spec, fold_train)
        prediction = artifact.predict_minutes(fold_validation)
        actual = [record.duration_minutes for record in fold_validation]
        fold_metrics.append(regression_metrics(actual, prediction))
    return _mean_std(fold_metrics), time.perf_counter() - started


def _flatten_row(result: dict[str, Any]) -> dict[str, Any]:
    row = {
        "model_name": result["model_name"],
        "selected_by_cv": result["selected_by_cv"],
        "training_rows": result["training_rows"],
        "test_rows": result["test_rows"],
        "random_seed": RANDOM_SEED,
        "cv_folds": CV_FOLDS,
        "cv_time_seconds": result["cv_time_seconds"],
        "training_time_seconds": result["training_time_seconds"],
        **result["cv_metrics"],
        **result["performance"],
    }
    test_metrics = result.get("locked_test_metrics") or {}
    for key in (
        "mae",
        "rmse",
        "r2",
        "median_absolute_error",
        "within_10_percent",
        "within_20_percent",
        "within_30_percent",
    ):
        row[f"test_{key}"] = test_metrics.get(key, "")
    return row


def _write_reports(report: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "duration_baseline.json"
    csv_path = REPORT_DIR / "duration_baseline.csv"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = [_flatten_row(result) for result in candidates]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _indices_hash(indices: list[int]) -> str:
    raw = ",".join(str(index) for index in sorted(indices)).encode()
    return hashlib.sha256(raw).hexdigest()


def run() -> dict[str, Any]:
    dataset = load_duration_dataset()
    records = list(dataset.records)
    targets = [record.duration_minutes for record in records]
    split = split_supervised(
        records,
        targets,
        classification=False,
        test_fraction=TEST_FRACTION,
        random_seed=RANDOM_SEED,
    )
    train_records = list(split.train_items)
    test_records = list(split.test_items)

    candidates: list[dict[str, Any]] = []
    fitted: dict[str, Any] = {}
    specs = candidate_specs(RANDOM_SEED)
    with offline_training_session():
        for spec in specs:
            cv_metrics, cv_time = _cross_validate(spec, train_records)
            artifact, training_time = fit_duration_candidate(spec, train_records)
            performance = benchmark_serialized_artifact(
                artifact,
                lambda loaded: loaded.predict_minutes(test_records[:1]),
            )
            fitted[spec.name] = artifact
            candidates.append(
                {
                    "model_name": spec.name,
                    "hyperparameters": spec.hyperparameters,
                    "selected_by_cv": False,
                    "training_rows": len(train_records),
                    "test_rows": len(test_records),
                    "cv_metrics": cv_metrics,
                    "cv_time_seconds": cv_time,
                    "training_time_seconds": training_time,
                    "performance": performance,
                    "locked_test_metrics": None,
                }
            )

    selected = min(candidates, key=lambda item: item["cv_metrics"]["cv_rmse_mean"])
    selected["selected_by_cv"] = True
    selected_artifact = fitted[selected["model_name"]]
    prediction = selected_artifact.predict_minutes(test_records)
    selected["locked_test_metrics"] = regression_metrics(
        [record.duration_minutes for record in test_records], prediction
    )

    timestamp = datetime.now(timezone.utc).isoformat()
    artifact_relative_path = f"ml/registry/artifacts/{MODEL_VERSION}.joblib"
    metadata = ModelMetadata(
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        dataset_version=dataset.version,
        feature_schema=FEATURE_SCHEMA,
        training_row_count=len(train_records),
        test_row_count=len(test_records),
        training_timestamp=timestamp,
        random_seed=RANDOM_SEED,
        hyperparameters={
            "candidate": selected["model_name"],
            **selected["hyperparameters"],
            "cv_folds": CV_FOLDS,
            "selection_metric": "cv_rmse_mean",
        },
        metrics={
            "cross_validation": selected["cv_metrics"],
            "locked_test": selected["locked_test_metrics"],
            "performance": selected["performance"],
        },
        framework="scikit-learn",
        framework_version=sklearn.__version__,
        artifact_path=artifact_relative_path,
    )
    artifact_path, metadata_path = persist_experimental_model(selected_artifact, metadata)
    selected["performance"]["model_size_bytes"] = artifact_path.stat().st_size

    report = {
        "experiment": {
            "name": "duration_baseline",
            "status": "experimental_not_production_ready",
            "timestamp": timestamp,
            "random_seed": RANDOM_SEED,
            "split": {
                "train_fraction": 1.0 - TEST_FRACTION,
                "test_fraction": TEST_FRACTION,
                "training_rows": len(train_records),
                "test_rows": len(test_records),
                "stratified": split.stratified,
                "cross_validation_folds": CV_FOLDS,
                "selection_uses_locked_test": False,
                "training_indices_sha256": _indices_hash(split.train_indices),
                "test_indices_sha256": _indices_hash(split.test_indices),
            },
            "locked_test_policy": (
                "Candidate dipilih hanya dari CV RMSE pada training split. "
                "Locked test dievaluasi sekali hanya untuk kandidat terpilih."
            ),
        },
        "dataset": {
            "name": dataset.manifest["dataset_name"],
            "version": dataset.version,
            "source_path": str(dataset.source_path.relative_to(ROOT)),
            "sha256": dataset.sha256,
            "validation": dataset.validation,
        },
        "feature_schema": FEATURE_SCHEMA,
        "metric_units": {
            "time_errors": "minutes",
            "r2": "unitless",
            "within_tolerance": "proportion_0_to_1",
            "latency": "milliseconds",
            "training_time": "seconds",
            "model_size": "bytes",
        },
        "candidates": candidates,
        "selected_model": {
            "candidate": selected["model_name"],
            "selection_metric": "cv_rmse_mean",
            "artifact_path": str(artifact_path.relative_to(ROOT)),
            "metadata_path": str(metadata_path.relative_to(ROOT)),
            "production_ready": False,
        },
        "framework": {
            "name": "scikit-learn",
            "version": sklearn.__version__,
            "artifact_serializer": f"joblib {joblib.__version__}",
        },
    }
    _write_reports(report, candidates)
    return report


def main() -> None:
    report = run()
    selected = report["selected_model"]
    print("Duration baseline selesai")
    print(f"dataset : {report['dataset']['version']}")
    print(
        f"split   : {report['experiment']['split']['training_rows']} train / "
        f"{report['experiment']['split']['test_rows']} locked test"
    )
    print(f"selected: {selected['candidate']} (berdasarkan CV RMSE)")
    print("status  : experimental, bukan model produksi")
    print("reports : reports/duration_baseline.csv + .json")


if __name__ == "__main__":
    main()
