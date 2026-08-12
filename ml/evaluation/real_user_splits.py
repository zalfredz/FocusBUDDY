"""Leakage-safe split planning for future real-user Duration evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from ml.evaluation.splits import split_group_supervised


@dataclass(frozen=True)
class RealUserSplit:
    strategy: str
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    leakage: dict[str, tuple[str, ...]]
    random_seed: int | None
    test_fraction: float

    @property
    def clean(self) -> bool:
        return not any(self.leakage.values())


def _values(records: Sequence[dict[str, Any]], indices: Sequence[int], key: str) -> set[str]:
    return {
        str(records[index].get(key) or "")
        for index in indices
        if str(records[index].get(key) or "")
    }


def _source_sessions(records: Sequence[dict[str, Any]], indices: Sequence[int]) -> set[str]:
    values: set[str] = set()
    for index in indices:
        record = records[index]
        values.update(str(value) for value in record.get("source_session_ids", []) if value)
        session = str(record.get("session_id") or "")
        if session:
            values.add(session)
    return values


def leakage_report(
    records: Sequence[dict[str, Any]],
    train_indices: Sequence[int],
    test_indices: Sequence[int],
    *,
    allow_user_overlap: bool = False,
) -> dict[str, tuple[str, ...]]:
    fields = ("user_id", "task_id", "task_family_id", "record_id")
    report = {
        field: tuple(sorted(_values(records, train_indices, field) & _values(records, test_indices, field)))
        for field in fields
    }
    report["source_session_id"] = tuple(
        sorted(_source_sessions(records, train_indices) & _source_sessions(records, test_indices))
    )
    if allow_user_overlap:
        report["user_id"] = ()
    return report


def user_group_holdout(
    records: Sequence[dict[str, Any]],
    *,
    test_fraction: float = 0.20,
    random_seed: int = 42,
) -> RealUserSplit:
    """Primary locked split: every user's records stay on one side."""
    targets = [float(record["actual_active_duration_minutes"]) for record in records]
    groups = [str(record.get("user_id") or "") for record in records]
    if any(not group for group in groups):
        raise ValueError("Every real-user row must have a user_id for group splitting")
    split = split_group_supervised(
        records,
        targets,
        groups,
        test_fraction=test_fraction,
        random_seed=random_seed,
    )
    leakage = leakage_report(records, split.train_indices, split.test_indices)
    if any(leakage.values()):
        raise ValueError(f"Primary user-group split leaked identifiers: {leakage}")
    return RealUserSplit(
        "user_group_holdout",
        tuple(split.train_indices),
        tuple(split.test_indices),
        leakage,
        random_seed,
        test_fraction,
    )


def _parse_time(value: Any) -> datetime:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid temporal split timestamp: {value!r}") from exc


def temporal_holdout(
    records: Sequence[dict[str, Any]], *, test_fraction: float = 0.20
) -> RealUserSplit:
    """Secondary split: newest whole task families per user become holdout."""
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")
    families_by_user: dict[str, dict[str, list[int]]] = {}
    for index, record in enumerate(records):
        user_id = str(record.get("user_id") or "")
        family = str(record.get("task_family_id") or "")
        if not user_id or not family:
            raise ValueError("Temporal split requires user_id and task_family_id")
        _parse_time(record.get("ended_at"))
        families_by_user.setdefault(user_id, {}).setdefault(family, []).append(index)

    train_indices: list[int] = []
    test_indices: list[int] = []
    for user_id, families in sorted(families_by_user.items()):
        ordered = sorted(
            families.items(),
            key=lambda item: (
                max(_parse_time(records[index].get("ended_at")) for index in item[1]),
                item[0],
            ),
        )
        if len(ordered) < 2:
            raise ValueError(
                f"Temporal split needs at least two task families per user; {user_id!r} has one"
            )
        n_test = max(1, int(round(len(ordered) * test_fraction)))
        n_test = min(n_test, len(ordered) - 1)
        for _, indices in ordered[:-n_test]:
            train_indices.extend(indices)
        for _, indices in ordered[-n_test:]:
            test_indices.extend(indices)

    train_indices.sort()
    test_indices.sort()
    leakage = leakage_report(
        records, train_indices, test_indices, allow_user_overlap=True
    )
    if any(leakage.values()):
        raise ValueError(f"Temporal split leaked task/session identity: {leakage}")
    return RealUserSplit(
        "temporal_task_family_holdout",
        tuple(train_indices),
        tuple(test_indices),
        leakage,
        None,
        test_fraction,
    )
