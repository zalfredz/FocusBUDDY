"""Metrik standar untuk regression, classification, dan retrieval."""
from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    median_absolute_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)


def regression_metrics(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, float]:
    y = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    if y.shape != p.shape or not len(y):
        raise ValueError("Regression metrics memerlukan actual/predicted non-empty yang sejajar")
    relative_error = np.abs(y - p) / np.maximum(np.abs(y), 1e-12)
    return {
        "mae": float(mean_absolute_error(y, p)),
        "rmse": float(mean_squared_error(y, p) ** 0.5),
        "r2": float(r2_score(y, p)),
        "median_absolute_error": float(median_absolute_error(y, p)),
        "within_10_percent": float(np.mean(relative_error <= 0.10)),
        "within_20_percent": float(np.mean(relative_error <= 0.20)),
        "within_30_percent": float(np.mean(relative_error <= 0.30)),
    }


def classification_metrics(
    actual: Sequence[Any],
    predicted: Sequence[Any],
    *,
    probabilities: Optional[Sequence[Any]] = None,
    labels: Optional[Sequence[Any]] = None,
) -> dict[str, Any]:
    y = np.asarray(actual)
    p = np.asarray(predicted)
    if y.shape != p.shape or not len(y):
        raise ValueError("Classification metrics memerlukan actual/predicted non-empty yang sejajar")
    label_values = list(labels) if labels is not None else sorted(set(y.tolist()) | set(p.tolist()))
    result: dict[str, Any] = {
        "accuracy": float(accuracy_score(y, p)),
        "precision": float(precision_score(y, p, average="macro", zero_division=0)),
        "recall": float(recall_score(y, p, average="macro", zero_division=0)),
        "f1": float(f1_score(y, p, average="macro", zero_division=0)),
        "confusion_matrix": confusion_matrix(y, p, labels=label_values).tolist(),
        "labels": label_values,
        "roc_auc": None,
    }
    if probabilities is not None:
        scores = np.asarray(probabilities)
        try:
            if len(label_values) == 2:
                positive_scores = scores[:, 1] if scores.ndim == 2 else scores
                result["roc_auc"] = float(roc_auc_score(y, positive_scores))
            elif scores.ndim == 2:
                result["roc_auc"] = float(
                    roc_auc_score(y, scores, multi_class="ovr", average="macro")
                )
        except ValueError:
            result["roc_auc"] = None
    return result


def retrieval_metrics(
    expected: Sequence[Any],
    ranked_candidates: Sequence[Sequence[Any]],
    *,
    accepted: Optional[Sequence[bool]] = None,
) -> dict[str, float]:
    if len(expected) != len(ranked_candidates) or not expected:
        raise ValueError("Retrieval metrics memerlukan expected/ranking non-empty yang sejajar")
    accepted_flags = (
        list(accepted)
        if accepted is not None
        else [bool(candidates) for candidates in ranked_candidates]
    )
    if len(accepted_flags) != len(expected):
        raise ValueError("Jumlah accepted harus sama dengan jumlah query")

    top1 = top3 = reciprocal_sum = retrieved = 0
    for target, candidates, is_accepted in zip(expected, ranked_candidates, accepted_flags):
        candidates = list(candidates)
        if candidates and candidates[0] == target:
            top1 += 1
        if target in candidates[:3]:
            top3 += 1
        if target in candidates:
            reciprocal_sum += 1.0 / (candidates.index(target) + 1)
        if is_accepted:
            retrieved += 1
    total = len(expected)
    coverage = retrieved / total
    return {
        "top_1": top1 / total,
        "top_3": top3 / total,
        "mrr": reciprocal_sum / total,
        "coverage": coverage,
        "fallback_rate": 1.0 - coverage,
    }
