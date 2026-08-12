"""Metadata dan persistence artefak model eksperimental."""
from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import joblib


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = Path(__file__).with_name("artifacts")
METADATA_DIR = Path(__file__).with_name("metadata")
INDEX_PATH = Path(__file__).with_name("index.json")
REGISTRY_STATUSES = {"experimental", "candidate", "promoted", "retired"}


@dataclass(frozen=True)
class ModelMetadata:
    model_name: str
    model_version: str
    dataset_version: str
    feature_schema: dict[str, Any]
    training_row_count: int
    test_row_count: int
    training_timestamp: str
    random_seed: int
    hyperparameters: dict[str, Any]
    metrics: dict[str, Any]
    framework: str
    framework_version: str
    artifact_path: str
    status: str = "experimental"
    artifact_sha256: str = ""
    dataset_sha256: str = ""
    preprocessing: dict[str, Any] = field(default_factory=dict)
    split_config: dict[str, Any] = field(default_factory=dict)
    runtime_versions: dict[str, str] = field(default_factory=dict)
    experiment_config: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        required_text = {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "dataset_version": self.dataset_version,
            "training_timestamp": self.training_timestamp,
            "framework": self.framework,
            "framework_version": self.framework_version,
            "artifact_path": self.artifact_path,
        }
        missing = [key for key, value in required_text.items() if not value]
        if missing:
            raise ValueError(f"Metadata model belum lengkap: {missing}")
        if self.training_row_count <= 0 or self.test_row_count <= 0:
            raise ValueError("Metadata model harus memiliki train/test row count")
        if self.status not in REGISTRY_STATUSES:
            raise ValueError(f"Status registry tidak valid: {self.status}")


def persist_experimental_model(artifact: Any, metadata: ModelMetadata) -> tuple[Path, Path]:
    metadata.validate()
    if metadata.status != "experimental":
        raise ValueError("Entrypoint ini hanya menyimpan model experimental")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    artifact_path = ROOT / metadata.artifact_path
    expected_parent = ARTIFACT_DIR.resolve()
    if artifact_path.resolve().parent != expected_parent:
        raise ValueError("Artefak eksperimen harus disimpan di ml/registry/artifacts")
    metadata_path = METADATA_DIR / f"{metadata.model_version}.json"
    if artifact_path.exists() or metadata_path.exists():
        raise FileExistsError(
            f"Model version {metadata.model_version} sudah ada; buat versi baru."
        )

    metadata_dict = asdict(metadata)
    performance = metadata_dict.setdefault("metrics", {}).setdefault("performance", {})
    for _ in range(3):
        artifact.metadata = metadata_dict
        joblib.dump(artifact, artifact_path, compress=3)
        actual_size = artifact_path.stat().st_size
        if performance.get("model_size_bytes") == actual_size:
            break
        performance["model_size_bytes"] = actual_size

    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    metadata_dict["artifact_sha256"] = digest

    metadata_path.write_text(
        json.dumps(metadata_dict, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    index = {"models": {}}
    if INDEX_PATH.exists():
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    index.setdefault("models", {})[metadata.model_name] = {
        "experimental_latest": metadata.model_version,
        "artifact_path": metadata.artifact_path,
        "metadata_path": str(metadata_path.relative_to(ROOT)),
        "production": None,
        "status": metadata.status,
        "artifact_sha256": digest,
        "dataset_version": metadata.dataset_version,
    }
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact_path, metadata_path
