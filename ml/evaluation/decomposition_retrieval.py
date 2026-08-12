"""Offline evaluation for the Indonesian task-decomposition retrieval corpus."""
from __future__ import annotations

import csv
import os
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVALUATION_DATASET = ROOT / "datasets" / "task_decomposition_eval_id.csv"
ALLOWED_CASE_TYPES = {"easy", "paraphrase", "negative"}


def load_evaluation_rows(path: Path = DEFAULT_EVALUATION_DATASET) -> list[dict[str, str]]:
    """Load frozen, manually curated Indonesian queries without corpus mutation."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            {key: str(value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]
    if not rows:
        raise ValueError("Dataset evaluasi retrieval kosong")
    for index, row in enumerate(rows, start=2):
        case_type = row.get("case_type", "")
        expected_match = row.get("expected_match", "").casefold()
        if case_type not in ALLOWED_CASE_TYPES:
            raise ValueError(f"Baris {index}: case_type tidak valid")
        if not row.get("query"):
            raise ValueError(f"Baris {index}: query kosong")
        if expected_match not in {"true", "false"}:
            raise ValueError(f"Baris {index}: expected_match harus true/false")
        if (expected_match == "true") != bool(row.get("expected_title")):
            raise ValueError(f"Baris {index}: expected_title tidak konsisten")
        if case_type == "negative" and expected_match != "false":
            raise ValueError(f"Baris {index}: negative wajib fallback")
    return rows


@contextmanager
def _production_runtime(enabled: bool):
    previous = os.environ.get("FOCUSBUDDY_RUNTIME_MODE")
    if enabled:
        os.environ["FOCUSBUDDY_RUNTIME_MODE"] = "production"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("FOCUSBUDDY_RUNTIME_MODE", None)
        else:
            os.environ["FOCUSBUDDY_RUNTIME_MODE"] = previous


def _summary(outcomes: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(outcomes)
    positives = [row for row in rows if row["expected_match"]]
    negatives = [row for row in rows if not row["expected_match"]]
    accepted = [row for row in rows if row["accepted"]]
    correct = [row for row in rows if row["correct"]]
    wrong = [row for row in rows if row["wrong"]]
    accepted_positive = [row for row in positives if row["accepted"]]
    false_accepts = [row for row in negatives if row["accepted"]]
    total = len(rows)
    return {
        "query_count": total,
        "positive_query_count": len(positives),
        "negative_query_count": len(negatives),
        "retrieved": len(accepted),
        "correct": len(correct),
        "false_retrieval": len(wrong),
        "retrieval_accuracy": len(correct) / len(positives) if positives else None,
        "precision": len(correct) / len(accepted) if accepted else 0.0,
        "coverage": len(accepted_positive) / len(positives) if positives else None,
        "fallback_rate": (total - len(accepted)) / total if total else None,
        "wrong_retrieval_rate": len(wrong) / total if total else None,
        "negative_false_accept_rate": (
            len(false_accepts) / len(negatives) if negatives else None
        ),
    }


def evaluate_retrieval(
    rows: Iterable[dict[str, str]], *, production_runtime: bool = True
) -> dict[str, Any]:
    """Evaluate current production matching; this never fits or trains a model."""
    from models import model_pecah

    rows = list(rows)
    corpus = list(model_pecah._pola_bawaan())
    outcomes: list[dict[str, Any]] = []
    with _production_runtime(production_runtime):
        for row in rows:
            expected_match = row["expected_match"].casefold() == "true"
            result = model_pecah.cari(
                row["query"],
                records=corpus,
                ambang=model_pecah.AMBANG_MIRIP,
                bahasa="id",
            )
            accepted = result.ketemu
            correct = bool(
                expected_match
                and accepted
                and result.dari_judul == row["expected_title"]
            )
            wrong = bool(accepted and not correct)
            outcomes.append(
                {
                    "case_type": row["case_type"],
                    "expected_match": expected_match,
                    "accepted": accepted,
                    "correct": correct,
                    "wrong": wrong,
                    "returned_title": result.dari_judul,
                    "score": round(result.skor, 6),
                    "second_score": round(result.skor_kedua, 6),
                    "reason": result.alasan,
                }
            )

    failures = [
        {
            "case_type": row["case_type"],
            "failure": "false_retrieval" if row["wrong"] else "fallback",
            "returned_title": row["returned_title"],
            "score": row["score"],
            "reason": row["reason"],
        }
        for row in outcomes
        if not row["correct"] and row["case_type"] != "negative"
    ]
    negative_failures = [
        {
            "case_type": row["case_type"],
            "failure": "false_retrieval",
            "returned_title": row["returned_title"],
            "score": row["score"],
            "reason": row["reason"],
        }
        for row in outcomes
        if row["case_type"] == "negative" and row["wrong"]
    ]
    splits = {
        split: _summary(row for row in outcomes if row["case_type"] == split)
        for split in ("easy", "paraphrase", "negative")
    }
    return {
        "evaluation_version": "task-decomposition-retrieval-eval-v1",
        "production_runtime": production_runtime,
        "corpus": {
            "path": "datasets/task_decomposition_id.csv",
            "language": "id",
            "pattern_count": len(corpus),
        },
        "retrieval_policy": {
            "matching": "character_ngram_hashing_cosine_similarity",
            "confidence_threshold": model_pecah.AMBANG_MIRIP,
            "ambiguity_margin": model_pecah.AMBANG_SELISIH,
            "low_confidence_behavior": "KALEM_or_rule_based_manual_fallback",
        },
        "definitions": {
            "retrieval_accuracy": "correct retrieved positive queries / all positive queries",
            "precision": "correct retrievals / all accepted retrievals",
            "coverage": "accepted positive retrievals / all positive queries",
            "wrong_retrieval_rate": "wrong accepted retrievals / all queries",
            "fallback_rate": "queries rejected by retrieval / all queries",
        },
        "overall": _summary(outcomes),
        "by_case_type": splits,
        "failure_count": len(failures) + len(negative_failures),
        "failures": failures + negative_failures,
        "query_counts": dict(sorted(Counter(row["case_type"] for row in outcomes).items())),
        "privacy": {
            "contains_user_ids": False,
            "contains_raw_user_task_text": False,
        },
    }
