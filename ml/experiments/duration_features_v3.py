"""Phase 2: offline text-feature ablation dan locked-test error analysis."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import statistics
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import scipy
import sklearn

from ml.datasets.duration_clean import CleanDurationRecord
from ml.datasets.duration_features import DurationFeatureDataset, write_derived_duration_dataset
from ml.evaluation.benchmark import benchmark_serialized_artifact
from ml.evaluation.duration_feature_quality import evaluate_duration_feature_quality
from ml.evaluation.metrics import regression_metrics
from ml.evaluation.splits import make_group_cross_validator, split_group_supervised
from ml.features.duration_text import feature_rules_metadata
from ml.registry.metadata import ModelMetadata, persist_experimental_model
from ml.training.duration import CandidateSpec, candidate_specs
from ml.training.duration_clean import FeatureConfig, fit_clean_duration_candidate
from ml.training.guard import offline_training_session


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports"
MODEL_NAME = "duration"
MODEL_VERSION = "duration-features-v3"
RANDOM_SEED = 42
TEST_FRACTION = 0.20
CV_FOLDS = 5
SELECTION_METRIC = "cv_rmse_mean"
MIN_MEANINGFUL_CV_IMPROVEMENT_PERCENT = 2.0
MIN_BETTER_FOLDS = 4
PERMUTATION_REPEATS = 20
PHASE1_REPORT = ROOT / "reports" / "duration-clean-v2.json"

QUANTITY_COLUMNS = ("quantity_available", "quantity_value")
COMPLEXITY_COLUMNS = (
    "complexity_analysis",
    "complexity_research",
    "complexity_revision",
    "complexity_long_form",
    "complexity_completion",
    "complexity_learning",
)
SCOPE_COLUMNS = ("scope_all", "scope_multiple", "scope_each", "scope_complete")


@dataclass(frozen=True)
class AblationConfig:
    experiment_id: str
    label: str
    columns: tuple[str, ...]
    feature_groups: tuple[str, ...]

    def training_config(self) -> FeatureConfig:
        return FeatureConfig(self.experiment_id, "clean", self.columns)


def _ablation_configs(quality: dict[str, Any]) -> tuple[list[AblationConfig], list[dict[str, Any]]]:
    passed = set(quality["reliable_feature_groups"])
    configs = [
        AblationConfig("A_phase1", "Phase 1 reproduced", (), ()),
        AblationConfig("B_n_token", "Phase 1 + n_token", ("n_token",), ("n_token",)),
        AblationConfig(
            "C_quantity", "Phase 1 + quantity", QUANTITY_COLUMNS, ("quantity",)
        ),
        AblationConfig(
            "D_quantity_unit",
            "Phase 1 + quantity + unit_type",
            (*QUANTITY_COLUMNS, "unit_type"),
            ("quantity", "unit_type"),
        ),
        AblationConfig(
            "E_action_type", "Phase 1 + action_type", ("action_type",), ("action_type",)
        ),
        AblationConfig(
            "G_complexity_scope",
            "Phase 1 + complexity/scope indicators",
            (*COMPLEXITY_COLUMNS, *SCOPE_COLUMNS),
            ("complexity_indicator", "scope_indicators"),
        ),
    ]
    skipped: list[dict[str, Any]] = []
    required = {
        "B_n_token": {"n_token"},
        "C_quantity": {"quantity"},
        "D_quantity_unit": {"quantity", "unit_type"},
        "E_action_type": {"action_type"},
        "G_complexity_scope": {"complexity_indicator", "scope_indicators"},
    }
    valid = [configs[0]]
    for config in configs[1:]:
        missing = sorted(required[config.experiment_id] - passed)
        if missing:
            skipped.append(
                {
                    "experiment_id": config.experiment_id,
                    "label": config.label,
                    "reason": "Feature group failed reliability gate",
                    "failed_groups": missing,
                }
            )
        else:
            valid.append(config)

    if "task_category" in passed:
        valid.append(
            AblationConfig(
                "F_task_category",
                "Phase 1 + task_category",
                ("task_category",),
                ("task_category",),
            )
        )
    else:
        skipped.append(
            {
                "experiment_id": "F_task_category",
                "label": "Phase 1 + task_category",
                "reason": "task_category failed the pre-training reliability gate",
            }
        )

    all_columns: list[str] = []
    all_groups: list[str] = []
    group_columns = {
        "n_token": ("n_token",),
        "quantity": QUANTITY_COLUMNS,
        "unit_type": ("unit_type",),
        "action_type": ("action_type",),
        "task_category": ("task_category",),
        "complexity_indicator": COMPLEXITY_COLUMNS,
        "scope_indicators": SCOPE_COLUMNS,
    }
    for group in (
        "n_token",
        "quantity",
        "unit_type",
        "action_type",
        "task_category",
        "complexity_indicator",
        "scope_indicators",
    ):
        if group in passed:
            all_groups.append(group)
            all_columns.extend(group_columns[group])
    valid.append(
        AblationConfig(
            "H_all_reliable",
            "Phase 1 + all reliable structured features",
            tuple(all_columns),
            tuple(all_groups),
        )
    )
    order = {
        "A_phase1": 0,
        "B_n_token": 1,
        "C_quantity": 2,
        "D_quantity_unit": 3,
        "E_action_type": 4,
        "F_task_category": 5,
        "G_complexity_scope": 6,
        "H_all_reliable": 7,
    }
    return sorted(valid, key=lambda config: order[config.experiment_id]), skipped


def _summarise_fold_metrics(folds: list[dict[str, float]]) -> dict[str, float]:
    summary: dict[str, float] = {}
    for key in folds[0]:
        values = [fold[key] for fold in folds]
        summary[f"cv_{key}_mean"] = float(np.mean(values))
        summary[f"cv_{key}_std"] = float(np.std(values))
    return summary


def _cross_validate(
    spec: CandidateSpec,
    train_records: list[CleanDurationRecord],
    config: AblationConfig,
    target_transform: str,
) -> tuple[dict[str, float], list[dict[str, float]], list[dict[str, Any]], float]:
    groups = [record.source_group_id for record in train_records]
    cv = make_group_cross_validator(folds=CV_FOLDS, random_seed=RANDOM_SEED)
    indices = np.arange(len(train_records))
    fold_metrics: list[dict[str, float]] = []
    fold_audit: list[dict[str, Any]] = []
    started = time.perf_counter()
    for fold_number, (fold_train_idx, validation_idx) in enumerate(
        cv.split(indices, groups=groups), start=1
    ):
        fold_train = [train_records[int(index)] for index in fold_train_idx]
        fold_validation = [train_records[int(index)] for index in validation_idx]
        train_groups = {record.source_group_id for record in fold_train}
        validation_groups = {record.source_group_id for record in fold_validation}
        overlap = train_groups & validation_groups
        if overlap:
            raise AssertionError("Source group menyeberang Phase 2 CV fold")
        artifact, _ = fit_clean_duration_candidate(
            spec, fold_train, config.training_config(), target_transform
        )
        prediction = artifact.predict_minutes(fold_validation)
        metrics = regression_metrics(
            [record.estimated_duration_minutes for record in fold_validation], prediction
        )
        fold_metrics.append(metrics)
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
    return (
        _summarise_fold_metrics(fold_metrics),
        fold_metrics,
        fold_audit,
        time.perf_counter() - started,
    )


def _aggregate_error(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "count": 0,
            "mae": None,
            "rmse": None,
            "median_absolute_error": None,
            "mean_signed_error": None,
            "median_signed_error": None,
        }
    absolute = [row["absolute_error_minutes"] for row in rows]
    signed = [row["signed_error_minutes"] for row in rows]
    return {
        "count": len(rows),
        "mae": float(statistics.mean(absolute)),
        "rmse": float(math.sqrt(statistics.mean(error**2 for error in signed))),
        "median_absolute_error": float(statistics.median(absolute)),
        "mean_signed_error": float(statistics.mean(signed)),
        "median_signed_error": float(statistics.median(signed)),
    }


def _group_error(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = sorted({str(row[field]) for row in rows})
    return {
        value: _aggregate_error([row for row in rows if str(row[field]) == value])
        for value in values
    }


def _duration_bucket(value: float) -> str:
    if value <= 15:
        return "0-15"
    if value <= 30:
        return "16-30"
    if value <= 60:
        return "31-60"
    if value <= 120:
        return "61-120"
    if value <= 300:
        return "121-300"
    return ">300"


def _error_analysis(
    records: list[CleanDurationRecord], prediction: Sequence[float]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for record, predicted in zip(records, prediction):
        human_estimate = record.estimated_duration_minutes
        signed = float(predicted - human_estimate)
        rows.append(
            {
                "row_id": record.row_id,
                "task": record.task,
                "human_estimated_minutes": human_estimate,
                "predicted_minutes": float(predicted),
                "signed_error_minutes": signed,
                "absolute_error_minutes": abs(signed),
                "duration_bucket": _duration_bucket(human_estimate),
                "task_category": record.structured["task_category"],
                "quantity_available": bool(int(record.structured["quantity_available"])),
                "deadline_available": record.has_deadline,
                "importance": record.importance,
            }
        )
    return {
        "overall": _aggregate_error(rows),
        "top_20_largest_absolute_errors": sorted(
            rows, key=lambda row: row["absolute_error_minutes"], reverse=True
        )[:20],
        "by_duration_bucket": _group_error(rows, "duration_bucket"),
        "by_task_category": _group_error(rows, "task_category"),
        "by_quantity_availability": _group_error(rows, "quantity_available"),
        "by_deadline_availability": _group_error(rows, "deadline_available"),
        "by_importance": _group_error(rows, "importance"),
        "short_tasks_0_to_30": _aggregate_error(
            [row for row in rows if row["human_estimated_minutes"] <= 30]
        ),
        "long_tasks_over_300": _aggregate_error(
            [row for row in rows if row["human_estimated_minutes"] > 300]
        ),
        "task_category_warning": (
            "Category failed the Phase 2 reliability gate and is diagnostic only."
        ),
    }


def _shuffle_record_group(
    records: list[CleanDurationRecord], donor_indices: np.ndarray, group: str
) -> list[CleanDurationRecord]:
    group_columns = {
        "quantity": QUANTITY_COLUMNS,
        "unit": ("unit_type",),
        "action": ("action_type",),
        "category": ("task_category",),
        "complexity": COMPLEXITY_COLUMNS,
        "scope": SCOPE_COLUMNS,
        "text_length": ("n_token",),
    }
    shuffled: list[CleanDurationRecord] = []
    for index, record in enumerate(records):
        donor = records[int(donor_indices[index])]
        if group == "task_text":
            shuffled.append(replace(record, task=donor.task))
        elif group == "deadline":
            shuffled.append(
                replace(
                    record,
                    has_deadline=donor.has_deadline,
                    deadline_days=donor.deadline_days,
                )
            )
        elif group == "importance":
            shuffled.append(replace(record, importance=donor.importance))
        else:
            structured = dict(record.structured)
            for column in group_columns[group]:
                structured[column] = donor.structured[column]
            shuffled.append(replace(record, structured=structured))
    return shuffled


def _grouped_permutation_importance(
    artifact: Any,
    records: list[CleanDurationRecord],
    included_columns: set[str],
) -> dict[str, Any]:
    actual = [record.estimated_duration_minutes for record in records]
    baseline_rmse = regression_metrics(actual, artifact.predict_minutes(records))["rmse"]
    groups = {
        "task_text": {"always"},
        "deadline": {"always"},
        "importance": {"always"},
        "quantity": set(QUANTITY_COLUMNS),
        "unit": {"unit_type"},
        "category": {"task_category"},
        "action": {"action_type"},
        "complexity": set(COMPLEXITY_COLUMNS),
        "scope": set(SCOPE_COLUMNS),
        "text_length": {"n_token"},
    }
    rng = np.random.default_rng(RANDOM_SEED)
    report: dict[str, Any] = {}
    for group, columns in groups.items():
        included = "always" in columns or bool(columns & included_columns)
        if not included:
            report[group] = {
                "included_in_model": False,
                "mean_rmse_increase_minutes": None,
                "std_rmse_increase_minutes": None,
            }
            continue
        increases = []
        for _ in range(PERMUTATION_REPEATS):
            donor_indices = rng.permutation(len(records))
            shuffled = _shuffle_record_group(records, donor_indices, group)
            shuffled_rmse = regression_metrics(
                actual, artifact.predict_minutes(shuffled)
            )["rmse"]
            increases.append(shuffled_rmse - baseline_rmse)
        report[group] = {
            "included_in_model": True,
            "mean_rmse_increase_minutes": float(np.mean(increases)),
            "std_rmse_increase_minutes": float(np.std(increases)),
            "repeats": PERMUTATION_REPEATS,
        }
    return {
        "method": "grouped permutation on locked test after all selections were frozen",
        "interpretation": (
            "Positive RMSE increase means the fitted model relied on the group; this is not causal."
        ),
        "baseline_rmse_minutes": baseline_rmse,
        "groups": report,
    }


def _indices_hash(indices: list[int]) -> str:
    raw = ",".join(str(index) for index in sorted(indices)).encode()
    return hashlib.sha256(raw).hexdigest()


def _phase1_reference() -> dict[str, Any]:
    report = json.loads(PHASE1_REPORT.read_text(encoding="utf-8"))
    selected = report["selected_model"]
    result = next(
        candidate
        for candidate in report["configuration_winners"]
        if candidate["experiment_id"] == selected["experiment_id"]
    )
    return {
        "experiment": "Phase 1 clean deadline + raw target",
        "best_model": selected["candidate"],
        "cv_rmse": result["cv_metrics"]["cv_rmse_mean"],
        "locked_test_metrics": result["locked_test_metrics"],
        "source_report": str(PHASE1_REPORT.relative_to(ROOT)),
    }


def _flatten_result(result: dict[str, Any]) -> dict[str, Any]:
    test = result.get("locked_test_metrics") or {}
    return {
        "experiment_id": result["experiment_id"],
        "experiment_label": result["experiment_label"],
        "feature_columns": "|".join(result["feature_columns"]),
        "target_transform": result["target_transform"],
        "model_name": result["model_name"],
        "selected_within_configuration": result["selected_within_configuration"],
        "selected_final": result["selected_final"],
        "cv_rmse_mean": result["cv_metrics"]["cv_rmse_mean"],
        "cv_rmse_std": result["cv_metrics"]["cv_rmse_std"],
        "cv_improvement_vs_phase1_percent": result.get(
            "cv_improvement_vs_phase1_percent", ""
        ),
        "folds_better_than_phase1": result.get("folds_better_than_phase1", ""),
        "meaningful_stable_improvement": result.get(
            "meaningful_stable_improvement", ""
        ),
        "test_mae": test.get("mae", ""),
        "test_rmse": test.get("rmse", ""),
        "test_r2": test.get("r2", ""),
        "test_median_absolute_error": test.get("median_absolute_error", ""),
        "test_within_10_percent": test.get("within_10_percent", ""),
        "test_within_20_percent": test.get("within_20_percent", ""),
        "test_within_30_percent": test.get("within_30_percent", ""),
        "cv_time_seconds": result["cv_time_seconds"],
        "final_training_time_seconds": result.get("final_training_time_seconds", ""),
    }


def _write_reports(report: dict[str, Any], results: list[dict[str, Any]]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / f"{MODEL_VERSION}.json"
    csv_path = REPORT_DIR / f"{MODEL_VERSION}.csv"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = [_flatten_result(result) for result in results]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run() -> dict[str, Any]:
    dataset: DurationFeatureDataset = write_derived_duration_dataset()
    records = list(dataset.records)
    quality = evaluate_duration_feature_quality(records)
    configs, skipped = _ablation_configs(quality)
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
        raise AssertionError("Locked-test source group overlap harus nol")

    specs = candidate_specs(RANDOM_SEED)
    results: list[dict[str, Any]] = []
    with offline_training_session():
        for config in configs:
            for target_transform in ("raw", "log1p"):
                for spec in specs:
                    cv_metrics, fold_metrics, fold_audit, cv_time = _cross_validate(
                        spec, train_records, config, target_transform
                    )
                    results.append(
                        {
                            "experiment_id": config.experiment_id,
                            "experiment_label": config.label,
                            "feature_groups": list(config.feature_groups),
                            "feature_columns": list(config.columns),
                            "feature_schema": config.training_config().schema(),
                            "target_transform": target_transform,
                            "model_name": spec.name,
                            "hyperparameters": spec.hyperparameters,
                            "cv_metrics": cv_metrics,
                            "cv_fold_metrics": fold_metrics,
                            "cv_fold_audit": fold_audit,
                            "cv_time_seconds": cv_time,
                            "selected_within_configuration": False,
                            "selected_final": False,
                            "locked_test_metrics": None,
                        }
                    )

        winners: list[dict[str, Any]] = []
        fitted_winners: dict[tuple[str, str], Any] = {}
        config_by_id = {config.experiment_id: config for config in configs}
        spec_by_name = {spec.name: spec for spec in specs}
        for config in configs:
            for target_transform in ("raw", "log1p"):
                matching = [
                    result
                    for result in results
                    if result["experiment_id"] == config.experiment_id
                    and result["target_transform"] == target_transform
                ]
                winner = min(matching, key=lambda item: item["cv_metrics"][SELECTION_METRIC])
                winner["selected_within_configuration"] = True
                artifact, training_time = fit_clean_duration_candidate(
                    spec_by_name[winner["model_name"]],
                    train_records,
                    config.training_config(),
                    target_transform,
                )
                winner["final_training_time_seconds"] = training_time
                fitted_winners[(config.experiment_id, target_transform)] = artifact
                winners.append(winner)

    baseline_raw = next(
        winner
        for winner in winners
        if winner["experiment_id"] == "A_phase1" and winner["target_transform"] == "raw"
    )
    baseline_cv_rmse = baseline_raw["cv_metrics"][SELECTION_METRIC]
    baseline_fold_rmse = [fold["rmse"] for fold in baseline_raw["cv_fold_metrics"]]
    raw_winners = [winner for winner in winners if winner["target_transform"] == "raw"]
    for winner in raw_winners:
        improvement = (
            (baseline_cv_rmse - winner["cv_metrics"][SELECTION_METRIC])
            / baseline_cv_rmse
            * 100.0
        )
        fold_wins = sum(
            fold["rmse"] < baseline
            for fold, baseline in zip(winner["cv_fold_metrics"], baseline_fold_rmse)
        )
        meaningful = winner is baseline_raw or (
            improvement >= MIN_MEANINGFUL_CV_IMPROVEMENT_PERCENT
            and fold_wins >= MIN_BETTER_FOLDS
        )
        winner["cv_improvement_vs_phase1_percent"] = improvement
        winner["folds_better_than_phase1"] = fold_wins
        winner["meaningful_stable_improvement"] = meaningful

    eligible = [winner for winner in raw_winners if winner["meaningful_stable_improvement"]]
    final = min(eligible, key=lambda item: item["cv_metrics"][SELECTION_METRIC])
    final["selected_final"] = True
    best_engineered = min(
        [winner for winner in raw_winners if winner["experiment_id"] != "A_phase1"],
        key=lambda item: item["cv_metrics"][SELECTION_METRIC],
    )

    # All selections are frozen above. Test metrics below are diagnostic final evidence only.
    for winner in winners:
        artifact = fitted_winners[(winner["experiment_id"], winner["target_transform"])]
        prediction = artifact.predict_minutes(test_records)
        winner["locked_test_metrics"] = regression_metrics(
            [record.estimated_duration_minutes for record in test_records], prediction
        )

    final_artifact = fitted_winners[(final["experiment_id"], final["target_transform"])]
    diagnostic_artifact = fitted_winners[
        (best_engineered["experiment_id"], best_engineered["target_transform"])
    ]
    diagnostic_prediction = diagnostic_artifact.predict_minutes(test_records)
    error_analysis = _error_analysis(test_records, diagnostic_prediction)
    error_analysis["candidate"] = {
        "experiment_id": best_engineered["experiment_id"],
        "model_name": best_engineered["model_name"],
        "target_transform": best_engineered["target_transform"],
        "selection_basis": "lowest training-only CV RMSE among engineered raw-target configurations",
    }
    feature_importance = _grouped_permutation_importance(
        diagnostic_artifact, test_records, set(best_engineered["feature_columns"])
    )
    feature_importance["candidate"] = error_analysis["candidate"]
    performance = benchmark_serialized_artifact(
        final_artifact, lambda loaded: loaded.predict_minutes(test_records[:1])
    )

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
            "selection_metric": SELECTION_METRIC,
            "minimum_meaningful_cv_improvement_percent": (
                MIN_MEANINGFUL_CV_IMPROVEMENT_PERCENT
            ),
            "minimum_better_folds": MIN_BETTER_FOLDS,
        },
        metrics={
            "cross_validation": final["cv_metrics"],
            "locked_test": final["locked_test_metrics"],
            "performance": performance,
        },
        framework="scikit-learn",
        framework_version=sklearn.__version__,
        artifact_path=artifact_relative_path,
        dataset_sha256=dataset.derived_sha256,
        preprocessing={
            "fit_scope": "CV train folds/final 80% training split only",
            "feature_extractor": feature_rules_metadata(),
            "feature_columns": final["feature_columns"],
            "feature_schema": final["feature_schema"],
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
            "experiment_id": final["experiment_id"],
            "experiment_label": final["experiment_label"],
            "feature_groups": final["feature_groups"],
            "target_meaning": "human_estimated_duration",
            "target_transform": final["target_transform"],
            "raw_target_pre_registered_as_primary": True,
            "selection_uses_locked_test": False,
        },
    )
    artifact_path, metadata_path = persist_experimental_model(final_artifact, metadata)
    performance["model_size_bytes"] = artifact_path.stat().st_size

    phase1 = _phase1_reference()
    phase1_metrics = phase1["locked_test_metrics"]
    final_metrics = final["locked_test_metrics"]
    report = {
        "experiment": {
            "name": "duration_features_v3",
            "status": "experimental_not_production_ready",
            "timestamp": timestamp,
            "raw_target_pre_registered_as_primary": True,
            "log1p_role": "secondary comparison only; never eligible for final artifact",
            "selection_metric": SELECTION_METRIC,
            "meaningful_feature_rule": {
                "minimum_cv_rmse_improvement_percent": (
                    MIN_MEANINGFUL_CV_IMPROVEMENT_PERCENT
                ),
                "minimum_folds_better_than_phase1": MIN_BETTER_FOLDS,
                "locked_test_used": False,
            },
            "split": {
                "type": "GroupShuffleSplit",
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
            "locked_test_policy": (
                "Ablation/model selection and the meaningful-improvement gate were finalized "
                "using training-only CV. Locked test was then evaluated once per frozen "
                "configuration winner and used only for final evidence/error diagnostics."
            ),
        },
        "dataset": {
            "source_path": str(dataset.source_dataset.source_path.relative_to(ROOT)),
            "source_sha256": dataset.source_dataset.sha256,
            "derived_path": str(dataset.derived_path.relative_to(ROOT)),
            "derived_sha256": dataset.derived_sha256,
            "dataset_version": dataset.version,
            "row_count": len(records),
            "source_unchanged": True,
        },
        "feature_quality": quality,
        "ablation_configs": [
            {
                "experiment_id": config.experiment_id,
                "label": config.label,
                "feature_groups": list(config.feature_groups),
                "feature_columns": list(config.columns),
            }
            for config in configs
        ],
        "skipped_experiments": skipped,
        "all_candidates": results,
        "configuration_winners": winners,
        "selected_model": {
            "experiment_id": final["experiment_id"],
            "experiment_label": final["experiment_label"],
            "feature_groups": final["feature_groups"],
            "feature_columns": final["feature_columns"],
            "candidate": final["model_name"],
            "target_transform": final["target_transform"],
            "selected_by_cv_only": True,
            "meaningful_stable_improvement": final["meaningful_stable_improvement"],
            "artifact_path": str(artifact_path.relative_to(ROOT)),
            "metadata_path": str(metadata_path.relative_to(ROOT)),
            "production_ready": False,
        },
        "best_engineered_candidate": {
            "experiment_id": best_engineered["experiment_id"],
            "experiment_label": best_engineered["experiment_label"],
            "feature_groups": best_engineered["feature_groups"],
            "feature_columns": best_engineered["feature_columns"],
            "candidate": best_engineered["model_name"],
            "target_transform": best_engineered["target_transform"],
            "cv_improvement_vs_phase1_percent": best_engineered[
                "cv_improvement_vs_phase1_percent"
            ],
            "folds_better_than_phase1": best_engineered["folds_better_than_phase1"],
            "meaningful_stable_improvement": best_engineered[
                "meaningful_stable_improvement"
            ],
            "locked_test_metrics": best_engineered["locked_test_metrics"],
            "diagnostic_only": True,
        },
        "phase1_reference": phase1,
        "phase2_vs_phase1_locked_test": {
            "mae_change_minutes": final_metrics["mae"] - phase1_metrics["mae"],
            "rmse_change_minutes": final_metrics["rmse"] - phase1_metrics["rmse"],
            "r2_change": final_metrics["r2"] - phase1_metrics["r2"],
            "median_absolute_error_change_minutes": (
                final_metrics["median_absolute_error"]
                - phase1_metrics["median_absolute_error"]
            ),
            "within_30_percent_change": (
                final_metrics["within_30_percent"] - phase1_metrics["within_30_percent"]
            ),
        },
        "best_engineered_vs_phase1_locked_test": {
            "mae_change_minutes": (
                best_engineered["locked_test_metrics"]["mae"] - phase1_metrics["mae"]
            ),
            "rmse_change_minutes": (
                best_engineered["locked_test_metrics"]["rmse"] - phase1_metrics["rmse"]
            ),
            "r2_change": (
                best_engineered["locked_test_metrics"]["r2"] - phase1_metrics["r2"]
            ),
            "median_absolute_error_change_minutes": (
                best_engineered["locked_test_metrics"]["median_absolute_error"]
                - phase1_metrics["median_absolute_error"]
            ),
            "within_30_percent_change": (
                best_engineered["locked_test_metrics"]["within_30_percent"]
                - phase1_metrics["within_30_percent"]
            ),
            "diagnostic_only_not_used_for_selection": True,
        },
        "error_analysis": error_analysis,
        "feature_importance": feature_importance,
        "performance": performance,
        "leakage_audit": {
            "feature_extractor_input": "task text only",
            "target_duration_used": False,
            "completion_status_used": False,
            "post_task_information_used": False,
            "future_information_used": False,
            "all_features_computable_at_task_creation": True,
            "source_group_overlap": len(split.overlapping_groups),
        },
        "reproducibility": {
            "command": "PYTHONPATH=\"$PWD\" python -m ml.experiments.duration_features_v3",
            "python_version": platform.python_version(),
            "packages": {
                "scikit-learn": sklearn.__version__,
                "numpy": np.__version__,
                "scipy": scipy.__version__,
                "joblib": joblib.__version__,
            },
            "platform": platform.platform(),
            "executable": sys.executable,
        },
    }
    _write_reports(report, results)
    return report


def main() -> None:
    report = run()
    selected = report["selected_model"]
    split = report["experiment"]["split"]
    print("Duration features v3 selesai")
    print(f"split   : {split['training_rows']} train / {split['test_rows']} locked test")
    print(
        f"groups  : {split['training_groups']} train / {split['test_groups']} test / "
        f"{split['overlapping_groups']} overlap"
    )
    print(
        f"selected: {selected['candidate']} / {selected['experiment_id']} / "
        f"{selected['target_transform']} (CV only)"
    )
    print("status  : experimental, bukan model produksi")
    print("reports : reports/duration-features-v3.csv + .json")


if __name__ == "__main__":
    main()
