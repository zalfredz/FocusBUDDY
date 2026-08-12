"""Kontrak eksperimen offline Duration feature engineering Phase 2."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.datasets.duration_features import derive_duration_feature_records, write_derived_duration_dataset
from ml.evaluation.duration_feature_quality import evaluate_duration_feature_quality
from ml.experiments.duration_features_v3 import _ablation_configs
from ml.features.duration_text import MISSING_CATEGORY, extract_duration_text_features


def test_quantity_is_explicit_and_rejects_numeric_identifiers() -> None:
    explicit = extract_duration_text_features("kerjakan 20 soal kalkulus")
    assert explicit.quantity_available == 1
    assert explicit.quantity_value == 20
    assert explicit.unit_type == "soal"

    chapter = extract_duration_text_features("baca satu bab buku 1984")
    assert chapter.quantity_value == 1
    assert chapter.unit_type == "bab"

    for text in (
        "selesaikan PR nomor 2",
        "selesaikan project 1",
        "tulis bab 4 skripsi",
        "rangkum kuliah 12",
        "bandingkan penelitian 2021 dan 2026",
        "unggah sebelum jam 5 sore",
    ):
        extracted = extract_duration_text_features(text)
        assert extracted.quantity_available == 0, text
        assert extracted.quantity_value == 0


def test_time_quantity_and_missing_time_are_distinct() -> None:
    duration = extract_duration_text_features("latihan selama 30 menit")
    assert duration.quantity_available == 1
    assert duration.quantity_value == 30
    assert duration.unit_type == "menit"

    approximate = extract_duration_text_features("cas HP beberapa jam")
    assert approximate.quantity_available == 0
    assert approximate.unit_type == MISSING_CATEGORY
    assert approximate.scope_multiple == 1


def test_feature_extraction_is_text_only_and_reproducible() -> None:
    text = "revisi keseluruhan draf laporan lengkap"
    first = extract_duration_text_features(text)
    second = extract_duration_text_features(text)
    assert first == second
    assert first.complexity_revision == 1
    assert first.complexity_long_form == 1
    assert first.scope_all == 1
    assert first.scope_complete == 1
    assert first.n_token == 5


def test_quality_gate_controls_ablation_matrix() -> None:
    _, records = derive_duration_feature_records()
    quality = evaluate_duration_feature_quality(records)
    assert quality["target_or_duration_used"] is False
    assert quality["features"]["quantity"]["passes_reliability_gate"] is True
    assert quality["features"]["n_token"]["coverage_percent"] == 100.0
    assert quality["features"]["task_category"]["passes_reliability_gate"] is False
    configs, skipped = _ablation_configs(quality)
    ids = [config.experiment_id for config in configs]
    assert ids == [
        "A_phase1",
        "B_n_token",
        "C_quantity",
        "D_quantity_unit",
        "E_action_type",
        "G_complexity_scope",
        "H_all_reliable",
    ]
    assert any(item["experiment_id"] == "F_task_category" for item in skipped)
    all_features = next(config for config in configs if config.experiment_id == "H_all_reliable")
    assert "task_category" not in all_features.columns


def test_derived_dataset_is_reproducible_and_does_not_replace_source() -> None:
    dataset = write_derived_duration_dataset()
    first = dataset.derived_path.read_bytes()
    repeated = write_derived_duration_dataset()
    second = repeated.derived_path.read_bytes()
    assert first == second
    assert dataset.derived_sha256 == repeated.derived_sha256
    assert dataset.derived_path != dataset.source_dataset.source_path
    assert len(dataset.records) == 549


def test_generated_phase2_experiment_contract() -> None:
    report_path = ROOT / "reports" / "duration-features-v3.json"
    metadata_path = ROOT / "ml" / "registry" / "metadata" / "duration-features-v3.json"
    artifact_path = ROOT / "ml" / "registry" / "artifacts" / "duration-features-v3.joblib"
    if not (report_path.exists() and metadata_path.exists() and artifact_path.exists()):
        return
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["experiment"]["split"]["overlapping_groups"] == 0
    assert report["leakage_audit"]["target_duration_used"] is False
    assert report["selected_model"]["target_transform"] == "raw"
    assert report["selected_model"]["selected_by_cv_only"] is True
    assert report["selected_model"]["production_ready"] is False
    assert report["best_engineered_candidate"]["experiment_id"] != "A_phase1"
    assert report["best_engineered_candidate"]["diagnostic_only"] is True
    assert len(report["error_analysis"]["top_20_largest_absolute_errors"]) == 20
    assert report["error_analysis"]["candidate"]["experiment_id"] == report[
        "best_engineered_candidate"
    ]["experiment_id"]
    assert "task_text" in report["feature_importance"]["groups"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["status"] == "experimental"
    assert metadata["metrics"]["performance"]["model_size_bytes"] == artifact_path.stat().st_size
    artifact = joblib.load(artifact_path)
    assert artifact.metadata["model_version"] == "duration-features-v3"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"OK: {len(tests)} Phase 2 ML tests")
