"""Mengukur precision, coverage, wrong retrieval, dan fallback rate."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from models import model_pecah  # noqa: E402

DEFAULT_PATTERNS = ROOT / "datasets" / "task_decomposition_en.csv"
DEFAULT_QUERIES = ROOT / "datasets" / "task_decomposition_queries.csv"


def read_patterns(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            {
                "title": (row.get("judul") or "").strip(),
                "description": (row.get("deskripsi") or "").strip(),
                "steps": [s.strip() for s in (row.get("langkah") or "").split("|") if s.strip()],
                "language": "en",
                "source": "dataset",
            }
            for row in csv.DictReader(handle)
            if (row.get("judul") or "").strip() and (row.get("langkah") or "").strip()
        ]


def evaluate(patterns: list[dict], queries: list[dict], threshold: float) -> dict[str, float | int]:
    retrieved = correct = wrong = 0
    for row in queries:
        result = model_pecah.cari(
            (row.get("query") or "").strip(),
            records=patterns,
            ambang=threshold,
            bahasa="en",
        )
        if not result.ketemu:
            continue
        retrieved += 1
        if result.dari_judul == (row.get("target_judul") or "").strip():
            correct += 1
        else:
            wrong += 1

    total = len(queries)
    return {
        "total_queries": total,
        "retrieved": retrieved,
        "correct": correct,
        "wrong": wrong,
        "precision": correct / retrieved if retrieved else 0.0,
        "coverage": retrieved / total if total else 0.0,
        "wrong_retrieval_rate": wrong / total if total else 0.0,
        "fallback_rate": (total - retrieved) / total if total else 0.0,
    }


def main() -> None:
    args = [Path(arg) for arg in sys.argv[1:]]
    patterns_path = args[0] if args else DEFAULT_PATTERNS
    queries_path = args[1] if len(args) > 1 else DEFAULT_QUERIES
    if not patterns_path.is_absolute():
        patterns_path = ROOT / patterns_path
    if not queries_path.is_absolute():
        queries_path = ROOT / queries_path

    patterns = read_patterns(patterns_path)
    with queries_path.open(encoding="utf-8-sig", newline="") as handle:
        queries = list(csv.DictReader(handle))
    report = evaluate(patterns, queries, model_pecah.AMBANG_MIRIP)

    print(f"patterns              : {len(patterns)} ({patterns_path.name})")
    print(f"queries               : {report['total_queries']} ({queries_path.name})")
    print(f"threshold             : {model_pecah.AMBANG_MIRIP:.2f}")
    print(f"precision             : {report['precision']:.1%}")
    print(f"coverage              : {report['coverage']:.1%}")
    print(f"wrong retrieval rate  : {report['wrong_retrieval_rate']:.1%}")
    print(f"fallback rate         : {report['fallback_rate']:.1%}")
    print(f"correct / wrong       : {report['correct']} / {report['wrong']}")


if __name__ == "__main__":
    main()
