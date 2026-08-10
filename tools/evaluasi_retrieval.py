"""Ukur retrieval TF-IDF terhadap query berlabel.

Ini sengaja menilai retrieval, bukan kualitas bahasa langkah AI. Retrieval
dianggap benar hanya jika judul pola yang dipungut sama dengan `target_judul`.
Query yang tidak dipungut dihitung sebagai fallback; itu lebih aman daripada
memaksa coverage tinggi dengan pola yang salah.

Jalankan dari root project:
    python tools/evaluasi_retrieval.py

Default memakai dataset/query Inggris yang memang saling berpasangan. Untuk
baseline Indonesia, operkan CSV pola dan query berlabel Indonesia sendiri:
    python tools/evaluasi_retrieval.py pola.csv query.csv
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.kalem_ml import model_pecah  # noqa: E402

DEFAULT_PATTERNS = ROOT / "DATASET" / "focusbuddy_task_decomposition_dataset_extended.csv"
DEFAULT_QUERIES = ROOT / "DATASET" / "focusbuddy_task_queries.csv"


def read_patterns(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            {
                "title": (row.get("judul") or "").strip(),
                "description": (row.get("deskripsi") or "").strip(),
                "steps": [s.strip() for s in (row.get("langkah") or "").split("|") if s.strip()],
                # Evaluasi ini berbahasa Inggris; language eksplisit agar
                # tidak tersaring oleh default runtime Indonesia.
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
        # Dari hasil yang berani dipungut, berapa yang tepat?
        "precision": correct / retrieved if retrieved else 0.0,
        # Berapa bagian input yang selesai tanpa fallback AI?
        "coverage": retrieved / total if total else 0.0,
        # Metrik risiko utama: salah dibagi seluruh input.
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
