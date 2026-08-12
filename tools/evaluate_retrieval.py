"""Evaluate production Indonesian task-decomposition retrieval without training."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.evaluation.decomposition_retrieval import (
    DEFAULT_EVALUATION_DATASET,
    evaluate_retrieval,
    load_evaluation_rows,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "reports" / "task_decomposition_retrieval_eval.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_EVALUATION_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--development-runtime",
        action="store_true",
        help="Evaluate local TF-IDF behavior instead of Render production matching.",
    )
    args = parser.parse_args()
    input_path = args.input if args.input.is_absolute() else ROOT / args.input
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    report = evaluate_retrieval(
        load_evaluation_rows(input_path),
        production_runtime=not args.development_runtime,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    overall = report["overall"]
    print(f"corpus={report['corpus']['pattern_count']} Indonesian patterns")
    print(f"accuracy={overall['retrieval_accuracy']:.1%}")
    print(f"precision={overall['precision']:.1%}")
    print(f"coverage={overall['coverage']:.1%}")
    print(f"wrong_retrieval_rate={overall['wrong_retrieval_rate']:.1%}")
    print(f"fallback_rate={overall['fallback_rate']:.1%}")
    print(f"report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
