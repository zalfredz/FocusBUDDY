"""Phase 6 contracts for provenance and production inference boundaries."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import clock, config, focus_session, storage
from app.demo_scenarios import apply_scenario_overlay, clear_demo_overlay
from ml.datasets.user_outcomes import build_training_dataset
from ml.personalization.duration import build_duration_personalization
from models import model_durasi, model_kalem, model_mood, model_overwhelm, model_pecah
from models.personalization import state_for_user
from models.prediction_interface import apply_duration_personalization


AUTH_UUID = "c65b233c-4436-47fc-9f46-474dc3523562"
FIXTURE = ROOT / "ml" / "datasets" / "fixtures" / "user_outcomes_v1.synthetic.json"


def _temporary_storage():
    directory = tempfile.TemporaryDirectory(prefix="focusbuddy_phase6_")
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    root = Path(directory.name)
    storage.DATA_DIR = root
    storage.DATA_FILE = root / "data.json"
    storage.BACKUP_FILE = root / "data.json.bak"
    return directory, original


def test_real_setting_demo_flow_reaches_training_candidate_and_cloud_hook() -> None:
    directory, original = _temporary_storage()
    synced: list[dict] = []
    original_demo_mode = config.DEMO_MODE
    try:
        config.DEMO_MODE = True
        storage.reset_all_data()
        storage.set_cloud_save_hook(lambda state: synced.append(copy.deepcopy(state)))
        task = storage.add_task(
            "Kerjakan 10 soal kalkulus",
            clock.today().isoformat(),
            steps=[{"id": "phase6-step", "text": "Buka soal pertama", "done": False}],
            menit_est=30,
            prediction_model_version="duration-reviewed-v0",
            prediction_source="model",
            prediction_importance=8,
            prediction_deadline_days=0,
        )
        focus_session.start(
            1,
            task_title=task["title"],
            task_id=task["id"],
            step_id="phase6-step",
            step_index=0,
        )
        focus_session._state().ends_at = datetime.now() + timedelta(seconds=59)
        focus_session.finish("completed")

        assert synced
        state = synced[-1]
        outcome = state["ml_outcome_records"][-1]
        assert task["data_provenance"] == "real_user"
        assert outcome["data_provenance"] == "real_user"
        assert outcome["collection_context"] == "setting_demo"
        assert outcome["synthetic"] is False and outcome["is_demo"] is False
        assert outcome["prediction_model_version"] == "duration-reviewed-v0"
        assert "user_id" not in outcome
        assert not ({"email", "phone", "name"} & set(outcome))

        dataset = build_training_dataset([{"user_id": AUTH_UUID, "state": state}])
        assert len(dataset.records) == 1
        candidate = dataset.records[0]
        assert candidate["training_eligible"] is True
        assert candidate["actual_active_duration_minutes"] > 0
        assert candidate["prediction_model_version"] == "duration-reviewed-v0"
    finally:
        storage.set_cloud_save_hook(None)
        focus_session.stop()
        config.DEMO_MODE = original_demo_mode
        storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original
        directory.cleanup()


def test_scenario_overlay_is_explicitly_synthetic() -> None:
    directory, original = _temporary_storage()
    try:
        storage.reset_all_data()
        apply_scenario_overlay("deadline_stack")
        generated = [
            task for task in storage.get_tasks() if task.get("_demo_generated") is True
        ]
        assert generated
        assert all(
            task.get("data_provenance") == "synthetic_scenario"
            for task in generated
        )
        clear_demo_overlay()
    finally:
        storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original
        directory.cleanup()


def test_synthetic_fixture_remains_training_ineligible() -> None:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    dataset = build_training_dataset(rows, allow_synthetic_for_testing=True)
    assert len(dataset.records) == 1
    assert dataset.records[0]["data_provenance"] == "synthetic_fixture"
    assert dataset.records[0]["training_eligible"] is False
    assert build_training_dataset(rows).records == ()

    fake_candidate = _personal_row(AUTH_UUID, 0, 1.5, training_eligible=True)
    state = build_duration_personalization(
        AUTH_UUID,
        [fake_candidate],
        dataset_version="synthetic-mechanics-v1",
        cutoff_at="2026-09-01T00:00:00",
        computed_at="2026-09-01T01:00:00",
    )
    assert state.eligible_outcome_count == 0
    assert state.active is False


def test_production_duration_inference_cannot_train() -> None:
    with patch.dict(os.environ, {"FOCUSBUDDY_RUNTIME_MODE": "production"}, clear=False):
        model_durasi.reset_model()
        with patch(
            "models.model_durasi.latih_dari_dataset",
            side_effect=AssertionError("runtime training called"),
        ):
            prediction = model_durasi.perkirakan("Kerjakan laporan", kalibrasi=1.0)
        assert prediction.model_version == model_durasi.STATIC_FALLBACK_VERSION
        assert model_durasi.status()["runtime_training_allowed"] is False
    model_durasi.reset_model()


def test_all_legacy_runtime_fit_paths_are_guarded_in_production() -> None:
    from app.core import energy_predictor, mood_model

    with patch.dict(os.environ, {"FOCUSBUDDY_RUNTIME_MODE": "production"}, clear=False):
        energy_predictor._model = None
        with patch.object(
            energy_predictor,
            "train_model",
            side_effect=AssertionError("energy runtime training called"),
        ):
            result = energy_predictor.predict_workload(7, 4, 4)
        assert result.workload_label in energy_predictor.LABELS

        model_mood.reset_model()
        model_overwhelm.reset_model()
        model_kalem.reset_model()
        assert model_mood._latih() is False
        assert model_overwhelm._latih() is False
        records = [
            {
                "kind": "next_action",
                "action_kind": "focus",
                "acted": index % 2 == 0,
                "n_tampil": 3,
                "fitur": {"jam": index},
            }
            for index in range(24)
        ]
        assert model_kalem.nilai({}, records).siap is False
        assert model_kalem._model is None

        logs = [
            {
                "date": f"2026-08-{index + 1:02d}",
                "weekday": index % 7,
                "energy": 4,
                "score": 3,
            }
            for index in range(10)
        ]
        with patch(
            "app.core.mood_model.DecisionTreeRegressor.fit",
            side_effect=AssertionError("mood runtime training called"),
        ):
            assert mood_model._predict_today(logs) is None

        with patch(
            "models.model_pecah.TfidfVectorizer.fit_transform",
            side_effect=AssertionError("retrieval fit called"),
        ):
            result = model_pecah.cari(
                "Kerjakan kalkulus",
                records=[
                    {
                        "title": "Kerjakan kalkulus",
                        "steps": ["Buka buku"],
                        "language": "id",
                    }
                ],
            )
        assert result.n_dibanding == 1


def test_application_uses_prediction_interface_and_registry_has_no_promotion() -> None:
    from models.model_registry import resolve_approved_artifact
    from models.prediction_interface import duration_predictions

    tracker_source = (ROOT / "app" / "views" / "tracker.py").read_text(encoding="utf-8")
    decomposer_source = (ROOT / "app" / "core" / "decomposer_logic.py").read_text(
        encoding="utf-8"
    )
    assert "from models import model_durasi" not in tracker_source
    assert "from models import model_durasi" not in decomposer_source
    assert duration_predictions.categories
    assert resolve_approved_artifact("duration") is None


def test_registry_resolves_only_promoted_checksum_valid_runtime_format() -> None:
    from models import model_registry

    with tempfile.TemporaryDirectory(prefix="focusbuddy_phase6_registry_") as directory:
        root = Path(directory)
        artifact = root / "duration.joblib"
        artifact.write_bytes(b"runtime-artifact-placeholder")
        checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest = root / "approved_models.json"
        manifest.write_text(
            json.dumps(
                {
                    "models": {
                        "duration": {
                            "model_version": "duration-global-v1",
                            "dataset_version": "dataset-v1",
                            "feature_schema_version": "duration-legacy-v1",
                            "artifact_format": "focusbuddy-duration-legacy-dict-v1",
                            "artifact_sha256": checksum,
                            "artifact_path_env": "PHASE6_TEST_ARTIFACT",
                            "promotion_status": "promoted",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        with patch.object(model_registry, "MANIFEST_PATH", manifest), patch.dict(
            os.environ, {"PHASE6_TEST_ARTIFACT": str(artifact)}, clear=False
        ):
            resolved = model_registry.resolve_approved_artifact("duration")
            assert resolved is not None
            assert resolved.model_version == "duration-global-v1"
            assert resolved.dataset_version == "dataset-v1"
            assert resolved.sha256 == checksum
            assert resolved.artifact_format == "focusbuddy-duration-legacy-dict-v1"

            changed = json.loads(manifest.read_text(encoding="utf-8"))
            changed["models"]["duration"]["artifact_sha256"] = "0" * 64
            manifest.write_text(json.dumps(changed), encoding="utf-8")
            assert model_registry.resolve_approved_artifact("duration") is None


def _personal_row(user_id: str, index: int, ratio: float, **changes) -> dict:
    ended_at = (datetime(2026, 7, 1) + timedelta(days=index)).isoformat()
    row = {
        "record_id": f"record-{user_id}-{index}",
        "user_id": user_id,
        "task_id": f"task-{index}",
        "occurrence_date": "",
        "predicted_duration_minutes": 100,
        "global_prediction_minutes": 100,
        "actual_active_duration_minutes": 100 * ratio,
        "ended_at": ended_at,
        "category": ("soal", "nulis", "baca")[index % 3],
        "training_eligible": True,
        "data_quality_status": "valid",
        "completion_status": "task_completed",
        "data_provenance": "synthetic_fixture",
        "synthetic": True,
    }
    row.update(changes)
    return row


def test_personalization_cold_start_threshold_and_isolation_mechanics() -> None:
    user_a = "synthetic-user-a"
    user_b = "synthetic-user-b"
    rows = [
        *[_personal_row(user_a, index, 1.4) for index in range(30)],
        *[_personal_row(user_b, index, 0.7) for index in range(30)],
    ]
    common = {
        "dataset_version": "synthetic-mechanics-v1",
        "cutoff_at": "2026-09-01T00:00:00",
        "computed_at": "2026-09-01T01:00:00",
        "allow_synthetic_for_testing": True,
    }
    insufficient = build_duration_personalization(user_a, rows[:29], **common)
    state_a = build_duration_personalization(user_a, rows, **common)
    state_b = build_duration_personalization(user_b, rows, **common)
    assert insufficient.active is False and insufficient.factor == 1.0
    assert state_a.active and state_a.factor == 1.4
    assert state_b.active and state_b.factor == 0.7
    assert state_a.source_outcomes_sha256 != state_b.source_outcomes_sha256
    assert state_for_user(state_b.to_dict(), expected_user_id=user_a).active is False

    global_prediction = model_durasi.Perkiraan(
        100, 80, 120, "global_model", model_version="duration-global-v1",
        global_model_version="duration-global-v1", global_minutes=100,
    )
    cold_start = apply_duration_personalization(global_prediction, insufficient)
    prediction_a = apply_duration_personalization(global_prediction, state_a)
    prediction_b = apply_duration_personalization(global_prediction, state_b)
    assert cold_start.menit == global_prediction.menit
    assert cold_start.personalization_active is False
    assert prediction_a.menit == 140
    assert prediction_b.menit == 70
    assert prediction_a.personalization_version == "duration-personalization-v1"
    assert prediction_b.personalization_version == "duration-personalization-v1"


def test_personalization_never_uses_current_or_future_outcome() -> None:
    user_id = "synthetic-user-a"
    prior = [_personal_row(user_id, index, 1.2) for index in range(30)]
    current = _personal_row(
        user_id,
        40,
        2.0,
        task_id="current-task",
        ended_at="2026-08-12T10:00:00",
    )
    future = _personal_row(
        user_id,
        41,
        2.0,
        ended_at="2026-08-13T10:00:00",
    )
    state = build_duration_personalization(
        user_id,
        [*prior, current, future],
        dataset_version="synthetic-mechanics-v1",
        cutoff_at="2026-08-12T09:00:00",
        computed_at="2026-08-12T09:00:01",
        exclude_task_id="current-task",
        allow_synthetic_for_testing=True,
    )
    assert state.eligible_outcome_count == 30
    assert state.factor == 1.2


def test_global_model_update_does_not_erase_personalization_state() -> None:
    payload = {
        "user_id": "synthetic-user-a",
        "version": "duration-personalization-v1",
        "factor": 1.25,
        "eligible_outcome_count": 30,
        "active_day_count": 14,
        "category_count": 3,
        "active": True,
        "source_dataset_version": "synthetic-mechanics-v1",
        "source_outcomes_sha256": "a" * 64,
        "cutoff_at": "2026-08-12T09:00:00",
        "computed_at": "2026-08-12T09:00:01",
        "test_only": True,
    }
    state = state_for_user(
        payload,
        expected_user_id="synthetic-user-a",
        allow_test_state=True,
    )
    global_v1 = model_durasi.Perkiraan(
        100, 80, 120, "global_model", model_version="duration-global-v1",
        global_model_version="duration-global-v1", global_minutes=100,
    )
    global_v2 = model_durasi.Perkiraan(
        120, 100, 140, "global_model", model_version="duration-global-v2",
        global_model_version="duration-global-v2", global_minutes=120,
    )
    result_v1 = apply_duration_personalization(global_v1, state)
    result_v2 = apply_duration_personalization(global_v2, state)
    assert result_v1.faktor_personal == result_v2.faktor_personal == 1.25
    assert result_v1.personalization_version == result_v2.personalization_version
    assert result_v1.global_model_version == "duration-global-v1"
    assert result_v2.global_model_version == "duration-global-v2"
    assert result_v1.menit == 125 and result_v2.menit == 150


def test_production_dependency_boundary_excludes_offline_ml() -> None:
    production_files = [
        *list((ROOT / "app").rglob("*.py")),
        *list((ROOT / "models").rglob("*.py")),
    ]
    for path in production_files:
        source = path.read_text(encoding="utf-8")
        assert "from ml." not in source
        assert "import ml." not in source

    check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import app.main; "
                "assert not any(name.startswith('ml.training') or "
                "name.startswith('ml.experiments') for name in sys.modules)"
            ),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.returncode == 0, check.stderr


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"OK: {len(tests)} Phase 6 ML tests")
