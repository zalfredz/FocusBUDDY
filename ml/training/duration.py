"""Training kandidat Duration memakai representasi produksi yang ada."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.tree import DecisionTreeRegressor

from ml.datasets.duration import DurationRecord
from ml.training.guard import require_offline_training


MAX_TEXT_FEATURES = 300
FEATURE_SCHEMA = {
    "text": {
        "source": "tugas",
        "transformer": "TfidfVectorizer",
        "analyzer": "char_wb",
        "ngram_range": [3, 5],
        "min_df": 2,
        "sublinear_tf": True,
        "max_features": MAX_TEXT_FEATURES,
    },
    "numeric": [
        {"source": "jatuh_tempo_hari", "name": "due_days"},
        {"source": "tingkat_kepentingan_1_10", "name": "importance"},
    ],
    "target": {
        "source": "durasi_jam",
        "converted_to": "duration_minutes",
        "training_transform": "log1p",
        "prediction_inverse": "expm1",
        "evaluation_cap": None,
    },
}


class MedianRegressor(RegressorMixin, BaseEstimator):
    """Baseline yang selalu mengembalikan median target training."""

    def fit(self, X, y):
        self.constant_ = float(np.median(np.asarray(y, dtype=float)))
        return self

    def predict(self, X):
        return np.full(len(X), self.constant_, dtype=float)


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    factory: Callable[[], Any]
    hyperparameters: dict[str, Any]


@dataclass
class DurationArtifact:
    model_name: str
    vectorizer: TfidfVectorizer
    estimator: Any
    feature_schema: dict[str, Any] = field(default_factory=lambda: dict(FEATURE_SCHEMA))
    metadata: dict[str, Any] = field(default_factory=dict)

    def predict_minutes(self, records: Sequence[DurationRecord]) -> np.ndarray:
        X = transform_records(records, self.vectorizer)
        prediction = np.expm1(self.estimator.predict(X))
        return np.maximum(prediction, 0.0)


def candidate_specs(random_seed: int = 42) -> list[CandidateSpec]:
    return [
        CandidateSpec("median_baseline", MedianRegressor, {}),
        CandidateSpec(
            "decision_tree",
            lambda: DecisionTreeRegressor(
                max_depth=8, min_samples_leaf=2, random_state=random_seed
            ),
            {"max_depth": 8, "min_samples_leaf": 2, "random_state": random_seed},
        ),
        CandidateSpec(
            "random_forest",
            lambda: RandomForestRegressor(
                n_estimators=300,
                min_samples_leaf=2,
                random_state=random_seed,
                n_jobs=-1,
            ),
            {
                "n_estimators": 300,
                "min_samples_leaf": 2,
                "random_state": random_seed,
                "n_jobs": -1,
            },
        ),
        CandidateSpec(
            "extra_trees",
            lambda: ExtraTreesRegressor(
                n_estimators=300,
                min_samples_leaf=2,
                random_state=random_seed,
                n_jobs=-1,
            ),
            {
                "n_estimators": 300,
                "min_samples_leaf": 2,
                "random_state": random_seed,
                "n_jobs": -1,
            },
        ),
        CandidateSpec(
            "gradient_boosting",
            lambda: GradientBoostingRegressor(
                n_estimators=200,
                learning_rate=0.05,
                max_depth=3,
                random_state=random_seed,
            ),
            {
                "n_estimators": 200,
                "learning_rate": 0.05,
                "max_depth": 3,
                "random_state": random_seed,
            },
        ),
        CandidateSpec(
            "hist_gradient_boosting",
            lambda: HistGradientBoostingRegressor(
                max_iter=200,
                learning_rate=0.05,
                max_leaf_nodes=31,
                l2_regularization=1.0,
                random_state=random_seed,
            ),
            {
                "max_iter": 200,
                "learning_rate": 0.05,
                "max_leaf_nodes": 31,
                "l2_regularization": 1.0,
                "random_state": random_seed,
            },
        ),
    ]


def _fit_vectorizer(records: Sequence[DurationRecord]) -> TfidfVectorizer:
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=2,
        sublinear_tf=True,
        max_features=MAX_TEXT_FEATURES,
    )
    vectorizer.fit([record.task for record in records])
    return vectorizer


def transform_records(
    records: Sequence[DurationRecord], vectorizer: TfidfVectorizer
) -> np.ndarray:
    text = vectorizer.transform([record.task for record in records])
    numeric = csr_matrix(
        [[record.due_days, record.importance] for record in records], dtype=float
    )
    return hstack([text, numeric]).toarray()


def fit_duration_candidate(
    spec: CandidateSpec, records: Sequence[DurationRecord]
) -> tuple[DurationArtifact, float]:
    require_offline_training()
    started = time.perf_counter()
    vectorizer = _fit_vectorizer(records)
    X = transform_records(records, vectorizer)
    target = np.log1p([record.duration_minutes for record in records])
    estimator = spec.factory().fit(X, target)
    elapsed = time.perf_counter() - started
    return DurationArtifact(spec.name, vectorizer, estimator), elapsed
