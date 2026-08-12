"""Pengukuran serialisasi, cold load, dan latency artefak eksperimen."""
from __future__ import annotations

import statistics
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np


def benchmark_serialized_artifact(
    artifact: Any,
    inference: Callable[[Any], Any],
    *,
    repeats: int = 200,
    load_repeats: int = 3,
) -> dict[str, float | int]:
    with tempfile.TemporaryDirectory(prefix="focusbuddy-ml-") as directory:
        path = Path(directory) / "artifact.joblib"
        joblib.dump(artifact, path, compress=3)
        size = path.stat().st_size

        load_times: list[float] = []
        loaded = None
        for _ in range(load_repeats):
            started = time.perf_counter()
            loaded = joblib.load(path)
            load_times.append((time.perf_counter() - started) * 1000.0)
        assert loaded is not None

        started = time.perf_counter()
        inference(loaded)
        first_inference = (time.perf_counter() - started) * 1000.0

        latencies: list[float] = []
        for _ in range(repeats):
            started = time.perf_counter()
            inference(loaded)
            latencies.append((time.perf_counter() - started) * 1000.0)

    return {
        "model_size_bytes": int(size),
        "cold_load_ms": float(statistics.median(load_times)),
        "first_inference_ms": float(first_inference),
        "warm_inference_mean_ms": float(statistics.mean(latencies)),
        "p50_inference_ms": float(np.percentile(latencies, 50)),
        "p95_inference_ms": float(np.percentile(latencies, 95)),
        "latency_repeats": repeats,
    }
