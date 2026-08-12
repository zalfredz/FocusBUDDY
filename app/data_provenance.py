"""Provenance labels for genuine usage versus developer-created data."""
from __future__ import annotations

from typing import Any


REAL_USER = "real_user"
SYNTHETIC_SCENARIO = "synthetic_scenario"
SYNTHETIC_FIXTURE = "synthetic_fixture"
ALLOWED = {REAL_USER, SYNTHETIC_SCENARIO, SYNTHETIC_FIXTURE}


def task_provenance(task: dict[str, Any] | None) -> str:
    task = task or {}
    explicit = str(task.get("data_provenance") or "").strip()
    if explicit in ALLOWED:
        return explicit
    if task.get("_demo_generated") is True:
        return SYNTHETIC_SCENARIO
    return REAL_USER


def is_synthetic(provenance: str) -> bool:
    return provenance in {SYNTHETIC_SCENARIO, SYNTHETIC_FIXTURE}
