"""Phase 1 Duration: clean data, group split, pre-registered feature/target matrix."""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import scipy
import sklearn

from ml.datasets.duration_clean import CleanDurationRecord, load_clean_duration_dataset
from ml.evaluation.benchmark import benchmark_serialized_artifact
from ml.evaluation.decomposition_validation import validate_decomposition_dataset
from ml.evaluation.metrics import regression_metrics
from ml.evaluation.splits import make_group_cross_validator, split_group_supervised
from ml.registry.metadata import ModelMetadata, persist_experimental_model
from ml.training.duration import CandidateSpec, candidate_specs
from ml.training.duration_clean import (
    TARGET_TRANSFORMS,
    FeatureConfig,
    feature_configs,
    fit_clean_duration_candidate,
)
from ml.training.guard import offline_training_session


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports"
MODEL_NAME = "duration"
MODEL_VERSION = "duration-clean-v2"
RANDOM_SEED = 42
TEST_FRACTION = 0.20
CV_FOLDS = 5
SELECTION_METRIC = "cv_rmse_mean"
PHASE0_REPORT = ROOT / "reports" / "duration_baseline.json"
FEATURE_TIE_BREAK_PRIORITY = {
    "clean_deadline_structured": 0,
    "clean_deadline": 1,
    "phase0_original": 2,
}


def _mean_std(folds: list[dict[str, float]]) -> dict[str, float]:
    summary: dict[str, float] = {}
    for key in folds[0]:
        values = [fold[key] for fold in folds]
        summary[f"cv_{key}_mean"] = float(np.mean(values))
        summary[f"cv_{key}_std"] = float(np.std(values))
    return summary


def _cross_validate(
    spec: CandidateSpec,
    records: list[CleanDurationRecord],
    feature_config: FeatureConfig,
    target_transform: str,
) -> tuple[dict[str, float], float, list[dict[str, Any]]]:
    groups = [record.source_group_id for record in records]
    cv = make_group_cross_validator(folds=CV_FOLDS, random_seed=RANDOM_SEED)
    indices = np.arange(len(records))
    fold_metrics: list[dict[str, float]] = []
    fold_audit: list[dict[str, Any]] = []
    started = time.perf_counter()
    for fold_number, (fold_train_idx, validation_idx) in enumerate(
        cv.split(indices, groups=groups), start=1
    ):
        fold_train = [records[int(index)] for index in fold_train_idx]
        fold_validation = [records[int(index)] for index in validation_idx]
        train_groups = {record.source_group_id for record in fold_train}
        validation_groups = {record.source_group_id for record in fold_validation}
        overlap = train_groups & validation_groups
        if overlap:
            raise AssertionError("Source group menyeberang CV fold")
        artifact, _ = fit_clean_duration_candidate(
            spec, fold_train, feature_config, target_transform
        )
        prediction = artifact.predict_minutes(fold_validation)
        actual = [record.estimated_duration_minutes for record in fold_validation]
        fold_metrics.append(regression_metrics(actual, prediction))
        fold_audit.append(
            {
                "fold": fold_number,
                "training_rows": len(fold_train),
                "validation_rows": len(fold_validation),
                "training_groups": len(train_groups),
                "validation_groups": len(validation_groups),
                "overlapping_groups": len(overlap),
            }
        )
    return _mean_std(fold_metrics), time.perf_counter() - started, fold_audit


def _indices_hash(indices: list[int]) -> str:
    raw = ",".join(str(index) for index in sorted(indices)).encode()
    return hashlib.sha256(raw).hexdigest()


def _duplicate_cross_split_audit(
    train_records: list[CleanDurationRecord], test_records: list[CleanDurationRecord]
) -> dict[str, Any]:
    def normalise(value: str) -> str:
        return " ".join(value.casefold().split())

    fields = ("tugas", "task_en", "tugas_raw", "task_en_raw")
    overlap_by_field: dict[str, dict[str, Any]] = {}
    for field in fields:
        train_values = {
            normalise(record.audit_texts.get(field, "")) for record in train_records
        } - {""}
        test_values = {
            normalise(record.audit_texts.get(field, "")) for record in test_records
        } - {""}
        overlaps = sorted(train_values & test_values)
        overlap_by_field[field] = {
            "overlap_count": len(overlaps),
            "overlap_examples": overlaps[:10],
        }
    train_groups = {record.source_group_id for record in train_records}
    test_groups = {record.source_group_id for record in test_records}
    return {
        "exact_or_normalized_text_overlap": overlap_by_field,
        "source_group_overlap_count": len(train_groups & test_groups),
        "translated_duplicate_check": (
            "task_en/task_en_raw normalized overlap is checked explicitly"
        ),
        "augmented_duplicate_check": {
            "available": True,
            "non_original_rows": sum(
                record.data_source.casefold() not in {"", "original"}
                for record in (*train_records, *test_records)
            ),
            "method": "data_source plus source_group_id",
        },
        "semantic_duplicate_check": {
            "supported": False,
            "reason": (
                "No independent semantic duplicate detector is available; source_group_id "
                "is used as the authoritative relationship boundary."
            ),
        },
    }


def _phase0_reference() -> dict[str, Any] | None:
    if not PHASE0_REPORT.exists():
        return None
    report = json.loads(PHASE0_REPORT.read_text(encoding="utf-8"))
    selected_name = report["selected_model"]["candidate"]
    selected = next(
        candidate for candidate in report["candidates"] if candidate["model_name"] == selected_name
    )
    return {
        "experiment": "phase0_baseline",
        "model_name": selected_name,
        "feature_config": "phase0_original_dataset",
        "target_transform": "log1p",
        "cv_rmse": selected["cv_metrics"]["cv_rmse_mean"],
        "test_metrics": selected["locked_test_metrics"],
        "comparable_split": False,
        "note": (
            "Reference used the original dataset and row-random split. It is historical "
            "context, not a like-for-like statistical comparison with the group-aware split."
        ),
    }


def _experiment_row(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("locked_test_metrics") or {}
    performance = result.get("performance") or {}
    return {
        "experiment_id": result["experiment_id"],
        "feature_config": result["feature_config"],
        "target_transform": result["target_transform"],
        "model_name": result["model_name"],
        "selected_within_configuration": result["selected_within_configuration"],
        "selected_final_by_cv": result["selected_final_by_cv"],
        "cv_rmse_mean": result["cv_metrics"]["cv_rmse_mean"],
        "cv_rmse_std": result["cv_metrics"]["cv_rmse_std"],
        "test_mae": metrics.get("mae", ""),
        "test_rmse": metrics.get("rmse", ""),
        "test_r2": metrics.get("r2", ""),
        "test_median_absolute_error": metrics.get("median_absolute_error", ""),
        "test_within_10_percent": metrics.get("within_10_percent", ""),
        "test_within_20_percent": metrics.get("within_20_percent", ""),
        "test_within_30_percent": metrics.get("within_30_percent", ""),
        "cv_time_seconds": result["cv_time_seconds"],
        "training_time_seconds": result["training_time_seconds"],
        "model_size_bytes": performance.get("model_size_bytes", ""),
        "cold_load_ms": performance.get("cold_load_ms", ""),
        "warm_inference_mean_ms": performance.get("warm_inference_mean_ms", ""),
        "p50_inference_ms": performance.get("p50_inference_ms", ""),
        "p95_inference_ms": performance.get("p95_inference_ms", ""),
    }


def _write_reports(report: dict[str, Any], results: list[dict[str, Any]]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / f"{MODEL_VERSION}.json"
    csv_path = REPORT_DIR / f"{MODEL_VERSION}.csv"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = [_experiment_row(result) for result in results]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run() -> dict[str, Any]:
    dataset = load_clean_duration_dataset()
    records = list(dataset.records)
    targets = [record.estimated_duration_minutes for record in records]
    groups = [record.source_group_id for record in records]
    split = split_group_supervised(
        records,
        targets,
        groups,
        test_fraction=TEST_FRACTION,
        random_seed=RANDOM_SEED,
    )
    train_records = list(split.train_items)
    test_records = list(split.test_items)
    if split.overlapping_groups:
        raise AssertionError("Locked split mengandung source group overlap")

    configs, skipped_experiments = feature_configs(dataset.columns)
    specs = candidate_specs(RANDOM_SEED)
    results: list[dict[str, Any]] = []
    fitted: dict[str, Any] = {}
    with offline_training_session():
        for config in configs:
            for target_transform in TARGET_TRANSFORMS:
                experiment_id = f"{config.name}__{target_transform}"
                for spec in specs:
                    cv_metrics, cv_time, fold_audit = _cross_validate(
                        spec, train_records, config, target_transform
                    )
                    artifact, training_time = fit_clean_duration_candidate(
                        spec, train_records, config, target_transform
                    )
                    key = f"{experiment_id}__{spec.name}"
                    fitted[key] = artifact
                    results.append(
                        {
                            "experiment_id": experiment_id,
                            "feature_config": config.name,
                            "feature_schema": config.schema(),
                            "target_transform": target_transform,
                            "model_name": spec.name,
                            "hyperparameters": spec.hyperparameters,
                            "cv_metrics": cv_metrics,
                            "cv_time_seconds": cv_time,
                            "cv_fold_audit": fold_audit,
                            "training_time_seconds": training_time,
                            "selected_within_configuration": False,
                            "selected_final_by_cv": False,
                            "locked_test_metrics": None,
                            "performance": None,
                        }
                    )

    shortlisted: list[dict[str, Any]] = []
    for config in configs:
        for target_transform in TARGET_TRANSFORMS:
            matching = [
                result
                for result in results
                if result["feature_config"] == config.name
                and result["target_transform"] == target_transform
            ]
            winner = min(matching, key=lambda result: result["cv_metrics"][SELECTION_METRIC])
            winner["selected_within_configuration"] = True
            shortlisted.append(winner)
    final = min(
        shortlisted,
        key=lambda result: (
            result["cv_metrics"][SELECTION_METRIC],
            FEATURE_TIE_BREAK_PRIORITY[result["feature_config"]],
        ),
    )
    tie_breaker_applied = (
        sum(
            result["cv_metrics"][SELECTION_METRIC]
            == final["cv_metrics"][SELECTION_METRIC]
            for result in shortlisted
        )
        > 1
    )
    final["selected_final_by_cv"] = True

    # The experiment matrix and all selections are frozen above. Locked-test values below
    # are final audit evidence only and never feed back into model/feature/target selection.
    for result in shortlisted:
        key = f"{result['experiment_id']}__{result['model_name']}"
        artifact = fitted[key]
        prediction = artifact.predict_minutes(test_records)
        result["locked_test_metrics"] = regression_metrics(
            [record.estimated_duration_minutes for record in test_records], prediction
        )
        result["performance"] = benchmark_serialized_artifact(
            artifact, lambda loaded: loaded.predict_minutes(test_records[:1])
        )

    final_key = f"{final['experiment_id']}__{final['model_name']}"
    final_artifact = fitted[final_key]
    timestamp = datetime.now(timezone.utc).isoformat()
    artifact_relative_path = f"ml/registry/artifacts/{MODEL_VERSION}.joblib"
    metadata = ModelMetadata(
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        dataset_version=dataset.version,
        feature_schema=final["feature_schema"],
        training_row_count=len(train_records),
        test_row_count=len(test_records),
        training_timestamp=timestamp,
        random_seed=RANDOM_SEED,
        hyperparameters={
            "candidate": final["model_name"],
            **final["hyperparameters"],
            "target_transform": final["target_transform"],
            "cv_folds": CV_FOLDS,
            "cv_type": "GroupKFold(shuffle=True)",
            "selection_metric": SELECTION_METRIC,
        },
        metrics={
            "cross_validation": final["cv_metrics"],
            "locked_test": final["locked_test_metrics"],
            "performance": final["performance"],
        },
        framework="scikit-learn",
        framework_version=sklearn.__version__,
        artifact_path=artifact_relative_path,
        dataset_sha256=dataset.sha256,
        preprocessing={
            "fit_scope": "training folds/final training split only",
            "text": final["feature_schema"]["text"],
            "deadline": final["feature_schema"]["deadline"],
            "structured_columns": final["feature_schema"]["structured_columns"],
        },
        split_config={
            "holdout": "GroupShuffleSplit",
            "test_fraction": TEST_FRACTION,
            "group_column": "source_group_id",
            "training_rows": len(train_records),
            "test_rows": len(test_records),
            "training_groups": len(split.train_groups),
            "test_groups": len(split.test_groups),
            "overlapping_groups": len(split.overlapping_groups),
            "cv": "GroupKFold(shuffle=True)",
            "cv_folds": CV_FOLDS,
        },
        runtime_versions={
            "python": platform.python_version(),
            "scikit-learn": sklearn.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "joblib": joblib.__version__,
        },
        experiment_config={
            "feature_config": final["feature_config"],
            "target_source": "durasi_menit",
            "target_internal_name": "estimated_duration_minutes",
            "target_meaning": "human_estimated_duration",
            "target_transform": final["target_transform"],
            "selection_metric": SELECTION_METRIC,
            "tie_breaker": "prefer cleaned deadline representation on exact CV RMSE tie",
            "selection_uses_locked_test": False,
        },
    )
    artifact_path, metadata_path = persist_experimental_model(final_artifact, metadata)
    final["performance"]["model_size_bytes"] = artifact_path.stat().st_size

    phase0 = _phase0_reference()
    phase1_final = final["locked_test_metrics"]
    comparison_to_phase0 = None
    if phase0:
        phase0_test = phase0["test_metrics"]
        comparison_to_phase0 = {
            "mae_change_minutes": phase1_final["mae"] - phase0_test["mae"],
            "rmse_change_minutes": phase1_final["rmse"] - phase0_test["rmse"],
            "r2_change": phase1_final["r2"] - phase0_test["r2"],
            "mae_improved": phase1_final["mae"] < phase0_test["mae"],
            "rmse_improved": phase1_final["rmse"] < phase0_test["rmse"],
            "warning": (
                "Phase 0 used a different dataset/split. Changes are descriptive, not a "
                "causal estimate of cleaning alone."
            ),
        }

    leakage_audit = _duplicate_cross_split_audit(train_records, test_records)
    report = {
        "experiment": {
            "name": "duration_clean_v2",
            "status": "experimental_not_production_ready",
            "timestamp": timestamp,
            "pre_registered_matrix": [
                {
                    "feature_config": config.name,
                    "target_transforms": list(TARGET_TRANSFORMS),
                    "candidates": [spec.name for spec in specs],
                }
                for config in configs
            ],
            "selection_metric": SELECTION_METRIC,
            "tie_breaker": "prefer cleaned deadline representation on exact CV RMSE tie",
            "selection_uses_locked_test": False,
            "locked_test_policy": (
                "Each feature/target configuration selected its model by train-only CV. "
                "The global artifact was also selected by CV. Locked test was then evaluated "
                "once for each pre-registered configuration winner solely for final comparison; "
                "its values did not change any selection."
            ),
            "split": {
                "type": "GroupShuffleSplit",
                "train_fraction_requested": 1.0 - TEST_FRACTION,
                "test_fraction_requested": TEST_FRACTION,
                "training_rows": len(train_records),
                "test_rows": len(test_records),
                "training_groups": len(split.train_groups),
                "test_groups": len(split.test_groups),
                "overlapping_groups": len(split.overlapping_groups),
                "random_seed": RANDOM_SEED,
                "training_indices_sha256": _indices_hash(split.train_indices),
                "test_indices_sha256": _indices_hash(split.test_indices),
            },
            "cross_validation": {
                "type": "GroupKFold",
                "folds": CV_FOLDS,
                "shuffle": True,
                "random_seed": RANDOM_SEED,
                "groups": "source_group_id",
            },
        },
        "dataset": {
            "name": dataset.manifest["dataset_name"],
            "version": dataset.version,
            "source_path": str(dataset.source_path.relative_to(ROOT)),
            "sha256": dataset.sha256,
            "validation": dataset.validation,
        },
        "target": {
            "source_column": "durasi_menit",
            "internal_name": "estimated_duration_minutes",
            "meaning": "human_estimated_duration",
            "tested_transforms": list(TARGET_TRANSFORMS),
            "evaluation_unit": "minutes_after_inverse_transform",
            "prediction_floor_minutes": 0.0,
        },
        "preprocessing": {
            "fit_scope": "each CV training fold or final 80% training split only",
            "test_influence": "none",
            "text": "char_wb TF-IDF; 3-5 grams; min_df=2; max_features=300",
            "structured_categorical": "OneHotEncoder(handle_unknown=ignore), if available",
            "deadline_clean_encoding": (
                "has_deadline plus deadline_days_or_zero; no deadline=(0,0); "
                "real deadline today=(1,0); -1 is never used in cleaned experiments"
            ),
        },
        "skipped_experiments": skipped_experiments,
        "leakage_audit": leakage_audit,
        "all_candidates": results,
        "configuration_winners": shortlisted,
        "selected_model": {
            "experiment_id": final["experiment_id"],
            "feature_config": final["feature_config"],
            "target_transform": final["target_transform"],
            "candidate": final["model_name"],
            "selection_metric": SELECTION_METRIC,
            "tie_breaker_applied": tie_breaker_applied,
            "artifact_path": str(artifact_path.relative_to(ROOT)),
            "metadata_path": str(metadata_path.relative_to(ROOT)),
            "production_ready": False,
        },
        "phase0_reference": phase0,
        "comparison_to_phase0": comparison_to_phase0,
        "decomposition_validation": validate_decomposition_dataset(),
        "reproducibility": {
            "command": "PYTHONPATH=\"$PWD\" python -m ml.experiments.duration_clean_v2",
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "packages": {
                "scikit-learn": sklearn.__version__,
                "numpy": np.__version__,
                "scipy": scipy.__version__,
                "joblib": joblib.__version__,
            },
            "executable": sys.executable,
        },
    }
    _write_reports(report, results)
    return report


def main() -> None:
    report = run()
    selected = report["selected_model"]
    split = report["experiment"]["split"]
    print("Duration clean v2 selesai")
    print(f"split   : {split['training_rows']} train / {split['test_rows']} locked test")
    print(
        f"groups  : {split['training_groups']} train / {split['test_groups']} test / "
        f"{split['overlapping_groups']} overlap"
    )
    print(
        f"selected: {selected['candidate']} / {selected['feature_config']} / "
        f"{selected['target_transform']} (CV only)"
    )
    print("status  : experimental, bukan model produksi")
    print("reports : reports/duration-clean-v2.csv + .json")


if __name__ == "__main__":
    main()
