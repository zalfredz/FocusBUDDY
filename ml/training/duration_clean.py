"""Training Duration Phase 1; seluruh fit hanya diizinkan dalam sesi offline."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder

from ml.datasets.duration_clean import CleanDurationRecord
from ml.training.duration import CandidateSpec, MAX_TEXT_FEATURES
from ml.training.guard import require_offline_training


TARGET_TRANSFORMS = ("raw", "log1p")
STRUCTURED_CATEGORICAL = (
    "task_category",
    "action_type",
    "complexity_indicator",
    "unit_type",
)
STRUCTURED_NUMERIC = (
    "n_token",
    "quantity_available",
    "quantity_value",
    "complexity_analysis",
    "complexity_research",
    "complexity_revision",
    "complexity_long_form",
    "complexity_completion",
    "complexity_learning",
    "scope_all",
    "scope_multiple",
    "scope_each",
    "scope_complete",
)


@dataclass(frozen=True)
class FeatureConfig:
    name: str
    deadline_encoding: str
    structured_columns: tuple[str, ...] = ()

    def schema(self) -> dict[str, Any]:
        if self.deadline_encoding == "phase0_raw":
            deadline = {
                "mode": "phase0_raw",
                "features": ["jatuh_tempo_hari"],
                "warning": "-1 is retained only to reproduce the Phase 0 representation",
            }
        else:
            deadline = {
                "mode": "clean_presence_plus_days",
                "features": ["has_deadline", "deadline_days_or_zero"],
                "no_deadline_encoding": {
                    "has_deadline": 0.0,
                    "deadline_days_or_zero": 0.0,
                },
                "deadline_encoding": {
                    "has_deadline": 1.0,
                    "deadline_days_or_zero": "tenggat_hari",
                },
                "note": "The presence flag disambiguates no deadline from a real 0-day deadline",
            }
        return {
            "name": self.name,
            "text": {
                "source": "tugas",
                "transformer": "TfidfVectorizer",
                "analyzer": "char_wb",
                "ngram_range": [3, 5],
                "min_df": 2,
                "sublinear_tf": True,
                "max_features": MAX_TEXT_FEATURES,
            },
            "deadline": deadline,
            "importance": "tingkat_kepentingan_1_10",
            "structured_columns": list(self.structured_columns),
        }


@dataclass
class CleanDurationPreprocessor:
    feature_config: FeatureConfig
    vectorizer: TfidfVectorizer
    categorical_columns: tuple[str, ...] = ()
    numeric_columns: tuple[str, ...] = ()
    categorical_encoder: OneHotEncoder | None = None

    def transform(self, records: Sequence[CleanDurationRecord]) -> np.ndarray:
        text = self.vectorizer.transform([record.task for record in records])
        numeric_rows: list[list[float]] = []
        for record in records:
            if self.feature_config.deadline_encoding == "phase0_raw":
                row = [record.raw_due_days, record.importance]
            else:
                row = [
                    float(record.has_deadline),
                    record.deadline_days if record.deadline_days is not None else 0.0,
                    record.importance,
                ]
            for column in self.numeric_columns:
                value = record.structured.get(column, "")
                if value == "":
                    raise ValueError(f"Structured numeric feature {column} kosong")
                row.append(float(value))
            numeric_rows.append(row)
        matrices = [text, csr_matrix(numeric_rows, dtype=float)]
        if self.categorical_columns:
            assert self.categorical_encoder is not None
            categorical = [
                [record.structured[column] for column in self.categorical_columns]
                for record in records
            ]
            matrices.append(self.categorical_encoder.transform(categorical))
        return hstack(matrices).toarray()


@dataclass
class CleanDurationArtifact:
    model_name: str
    target_transform: str
    preprocessor: CleanDurationPreprocessor
    estimator: Any
    feature_schema: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def predict_minutes(self, records: Sequence[CleanDurationRecord]) -> np.ndarray:
        prediction = np.asarray(
            self.estimator.predict(self.preprocessor.transform(records)), dtype=float
        )
        if self.target_transform == "log1p":
            prediction = np.expm1(prediction)
        return np.maximum(prediction, 0.0)


def feature_configs(available_columns: Sequence[str]) -> tuple[list[FeatureConfig], list[dict[str, Any]]]:
    available = set(available_columns)
    configs = [
        FeatureConfig("phase0_original", "phase0_raw"),
        FeatureConfig("clean_deadline", "clean"),
    ]
    structured = tuple(
        column
        for column in (*STRUCTURED_CATEGORICAL, *STRUCTURED_NUMERIC)
        if column in available
    )
    skipped: list[dict[str, Any]] = []
    if structured:
        configs.append(FeatureConfig("clean_deadline_structured", "clean", structured))
    else:
        skipped.append(
            {
                "experiment": "clean_deadline_structured",
                "reason": (
                    "Dataset does not contain task_category, action_type, "
                    "complexity_indicator, or n_token; no feature was invented."
                ),
                "missing_columns": list(
                    (*STRUCTURED_CATEGORICAL, *STRUCTURED_NUMERIC)
                ),
            }
        )
    return configs, skipped


def _fit_preprocessor(
    records: Sequence[CleanDurationRecord], config: FeatureConfig
) -> CleanDurationPreprocessor:
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=2,
        sublinear_tf=True,
        max_features=MAX_TEXT_FEATURES,
    )
    vectorizer.fit([record.task for record in records])
    categorical = tuple(
        column for column in config.structured_columns if column in STRUCTURED_CATEGORICAL
    )
    numeric = tuple(
        column for column in config.structured_columns if column in STRUCTURED_NUMERIC
    )
    encoder = None
    if categorical:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
        encoder.fit(
            [[record.structured[column] for column in categorical] for record in records]
        )
    return CleanDurationPreprocessor(config, vectorizer, categorical, numeric, encoder)


def _transform_target(values: Sequence[float], target_transform: str) -> np.ndarray:
    target = np.asarray(values, dtype=float)
    if target_transform == "raw":
        return target
    if target_transform == "log1p":
        return np.log1p(target)
    raise ValueError(f"Target transform tidak dikenal: {target_transform}")


def fit_clean_duration_candidate(
    spec: CandidateSpec,
    records: Sequence[CleanDurationRecord],
    feature_config: FeatureConfig,
    target_transform: str,
) -> tuple[CleanDurationArtifact, float]:
    require_offline_training()
    if target_transform not in TARGET_TRANSFORMS:
        raise ValueError(f"Target transform harus salah satu {TARGET_TRANSFORMS}")
    started = time.perf_counter()
    preprocessor = _fit_preprocessor(records, feature_config)
    X = preprocessor.transform(records)
    target = _transform_target(
        [record.estimated_duration_minutes for record in records], target_transform
    )
    estimator = spec.factory().fit(X, target)
    artifact = CleanDurationArtifact(
        model_name=spec.name,
        target_transform=target_transform,
        preprocessor=preprocessor,
        estimator=estimator,
        feature_schema=feature_config.schema(),
    )
    return artifact, time.perf_counter() - started
