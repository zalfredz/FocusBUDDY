"""Resolve explicitly approved production artifacts without training them."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "models" / "approved_models.json"


@dataclass(frozen=True)
class ApprovedArtifact:
    model_name: str
    model_version: str
    dataset_version: str
    feature_schema_version: str
    artifact_format: str
    sha256: str
    path: Path
    metadata: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest() -> dict[str, Any]:
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_approved_artifact(model_name: str) -> ApprovedArtifact | None:
    """Return a checksum-verified artifact or None; never download or fit."""
    entry = (_manifest().get("models") or {}).get(model_name) or {}
    if entry.get("promotion_status") != "promoted":
        return None
    version = str(entry.get("model_version") or "").strip()
    checksum = str(entry.get("artifact_sha256") or "").strip().lower()
    artifact_format = str(entry.get("artifact_format") or "").strip()
    environment_key = str(entry.get("artifact_path_env") or "").strip()
    path_value = os.getenv(environment_key, "").strip() if environment_key else ""
    if (
        not version
        or artifact_format != "focusbuddy-duration-legacy-dict-v1"
        or len(checksum) != 64
        or not path_value
    ):
        return None
    path = Path(path_value).expanduser().resolve()
    if not path.is_file() or _sha256(path) != checksum:
        return None
    return ApprovedArtifact(
        model_name=model_name,
        model_version=version,
        dataset_version=str(entry.get("dataset_version") or ""),
        feature_schema_version=str(entry.get("feature_schema_version") or ""),
        artifact_format=artifact_format,
        sha256=checksum,
        path=path,
        metadata=dict(entry),
    )
