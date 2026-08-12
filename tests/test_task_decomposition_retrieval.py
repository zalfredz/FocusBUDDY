"""Production-safety contracts for Indonesian task-decomposition retrieval."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import storage
from app.core import ai_client, decomposer_logic
from ml.evaluation.decomposition_retrieval import (
    evaluate_retrieval,
    load_evaluation_rows,
)
from models import model_pecah


def _temporary_storage():
    directory = tempfile.TemporaryDirectory(prefix="focusbuddy_retrieval_")
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    root = Path(directory.name)
    storage.DATA_DIR = root
    storage.DATA_FILE = root / "data.json"
    storage.BACKUP_FILE = root / "data.json.bak"
    return directory, original


def _task(title: str, *, task_id: str, description: str = "") -> dict:
    return {
        "id": task_id,
        "title": title,
        "description": description,
        "important": False,
        "kategori": "",
        "jumlah_unit": 0,
        "menit_est": 30,
    }


def test_production_corpus_accepts_only_explicit_indonesian_records() -> None:
    with patch.dict(os.environ, {"FOCUSBUDDY_RUNTIME_MODE": "production"}, clear=False):
        corpus = list(model_pecah._pola_bawaan())
        assert len(corpus) == 212
        assert all(row["language"] == "id" for row in corpus)

        rejected = model_pecah.cari(
            "Clean my room",
            records=[
                {"title": "Clean room", "steps": ["Start"], "language": "en"},
                {"title": "Legacy record", "steps": ["Start"]},
            ],
        )
        assert rejected.ketemu is False
        assert rejected.alasan == "corpus_indonesia_kosong"

        unsupported = model_pecah.cari("Beresin kamar", records=corpus, bahasa="en")
        assert unsupported.ketemu is False
        assert unsupported.alasan == "bahasa_retrieval_tidak_didukung"


def test_retrieval_is_conservative_for_exact_and_unrelated_queries() -> None:
    with patch.dict(os.environ, {"FOCUSBUDDY_RUNTIME_MODE": "production"}, clear=False):
        corpus = list(model_pecah._pola_bawaan())
        exact = model_pecah.cari("Beresin kamar", records=corpus)
        unrelated = model_pecah.cari("bikin proposal buat ikut lomba hackathon", records=corpus)
        ambiguous = model_pecah.cari(
            "Rapikan meja",
            records=[
                {"title": "Rapikan meja", "steps": ["Mulai"], "language": "id"},
                {"title": "Rapikan meja", "steps": ["Mulai lagi"], "language": "id"},
            ],
        )

    assert exact.ketemu is True
    assert exact.dari_judul == "Beresin kamar"
    assert exact.alasan == "retrieval_confident"
    assert unrelated.ketemu is False
    assert unrelated.alasan in {"confidence_di_bawah_ambang", "dua_pola_terlalu_ambigu"}
    assert ambiguous.ketemu is False
    assert ambiguous.alasan == "dua_pola_terlalu_ambigu"


def test_provenance_is_campuran_when_ai_and_retrieval_both_contribute() -> None:
    directory, original = _temporary_storage()
    try:
        storage.reset_all_data()
        ai_task = _task("Rancang proposal robot", task_id="ai-task")
        local_task = _task("Beresin kamar", task_id="local-task")
        with patch.object(ai_client, "can_generate", return_value=True), patch.object(
            decomposer_logic,
            "_ai_steps",
            return_value=([("Rancang proposal robot", "Tulis tujuan proposal", 20)], ""),
        ):
            result = decomposer_logic.plan_today([local_task, ai_task], allow_ai=True)

        assert result.source == "campuran"
        assert result.n_retrieval == 1 and result.n_ai == 1
        assert result.ai_called is True
        assert result.task_sources["local-task"] == "retrieval"
        assert result.task_sources["ai-task"] == "ai"
    finally:
        storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original
        directory.cleanup()


def test_partial_ai_response_never_leaves_a_task_without_steps_or_honest_source() -> None:
    directory, original = _temporary_storage()
    try:
        storage.reset_all_data()
        first = _task("Rancang proposal robot", task_id="first")
        second = _task("Siapkan eksperimen sains", task_id="second")
        with patch.object(ai_client, "can_generate", return_value=True), patch.object(
            decomposer_logic,
            "_ai_steps",
            return_value=([("Rancang proposal robot", "Tulis tujuan proposal", 20)], ""),
        ):
            result = decomposer_logic.plan_today([first, second], allow_ai=True)

        assert result.source == "campuran"
        assert result.n_ai == 1
        assert result.task_sources["first"] == "ai"
        assert result.task_sources["second"] == "fallback"
        assert result.task_steps["first"]
        assert result.task_steps["second"]
    finally:
        storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original
        directory.cleanup()


def test_ai_quota_does_not_disable_retrieval_manual_or_rule_fallback() -> None:
    directory, original = _temporary_storage()
    try:
        storage.reset_all_data()
        manual = _task(
            "Susun proposal", task_id="manual", description="Cari tujuan\nTulis draft"
        )
        retrieved = _task("Beresin kamar", task_id="retrieved")
        unknown = _task("Rancang eksperimen robot", task_id="unknown")
        result = decomposer_logic.plan_today(
            [manual, retrieved, unknown], allow_ai=False
        )

        assert result.ai_called is False
        assert result.n_ai == 0
        assert result.n_manual == 1 and result.n_retrieval == 1
        assert result.source == "campuran"
        assert result.task_sources == {
            "manual": "manual",
            "retrieved": "retrieval",
            "unknown": "fallback",
        }
        assert all(result.task_steps[key] for key in result.task_sources)
    finally:
        storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original
        directory.cleanup()


def test_indonesian_retrieval_evaluation_is_reproducible_and_privacy_safe() -> None:
    report = evaluate_retrieval(load_evaluation_rows(), production_runtime=True)
    overall = report["overall"]

    assert report["query_counts"] == {"easy": 20, "negative": 20, "paraphrase": 30}
    assert report["corpus"] == {
        "path": "datasets/task_decomposition_id.csv",
        "language": "id",
        "pattern_count": 212,
    }
    assert report["by_case_type"]["easy"]["precision"] == 1.0
    assert report["by_case_type"]["negative"]["negative_false_accept_rate"] == 0.0
    assert overall["wrong_retrieval_rate"] <= 0.02
    assert "kamar gue berantakan banget" not in json.dumps(report)
    assert report["privacy"]["contains_raw_user_task_text"] is False


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"OK: {len(tests)} task-decomposition retrieval tests")
