"""Runtime boundary: training is forbidden in hosted production processes."""
from __future__ import annotations

import os


PRODUCTION_MODES = {"prod", "production"}
DEVELOPMENT_MODES = {"dev", "development", "local", "test", "testing"}


def runtime_mode() -> str:
    explicit = os.getenv("FOCUSBUDDY_RUNTIME_MODE", "").strip().lower()
    if explicit in PRODUCTION_MODES:
        return "production"
    if explicit in DEVELOPMENT_MODES:
        return "development"
    if os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"):
        return "production"
    return "development"


def runtime_training_allowed() -> bool:
    return runtime_mode() != "production"


def require_runtime_training_allowed(operation: str) -> None:
    if not runtime_training_allowed():
        raise RuntimeError(
            f"{operation} diblokir: production runtime hanya boleh inference."
        )
