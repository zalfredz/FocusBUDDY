"""Split reproducible dengan stratification untuk classification bila memungkinkan."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Sequence

from sklearn.model_selection import (
    GroupKFold,
    GroupShuffleSplit,
    KFold,
    StratifiedKFold,
    train_test_split,
)


@dataclass(frozen=True)
class HoldoutSplit:
    train_items: list[Any]
    test_items: list[Any]
    train_targets: list[Any]
    test_targets: list[Any]
    train_indices: list[int]
    test_indices: list[int]
    stratified: bool
    random_seed: int
    test_fraction: float


@dataclass(frozen=True)
class GroupHoldoutSplit(HoldoutSplit):
    train_groups: list[Any]
    test_groups: list[Any]
    overlapping_groups: list[Any]


def _can_stratify(targets: Sequence[Any]) -> bool:
    counts = Counter(targets)
    return len(counts) >= 2 and min(counts.values()) >= 2


def split_supervised(
    items: Sequence[Any],
    targets: Sequence[Any],
    *,
    classification: bool,
    test_fraction: float = 0.20,
    random_seed: int = 42,
) -> HoldoutSplit:
    if len(items) != len(targets):
        raise ValueError("Jumlah items dan targets harus sama")
    if len(items) < 5:
        raise ValueError("Minimal 5 baris diperlukan untuk 80/20 split")
    indices = list(range(len(items)))
    use_stratify = classification and _can_stratify(targets)
    train_idx, test_idx = train_test_split(
        indices,
        test_size=test_fraction,
        random_state=random_seed,
        shuffle=True,
        stratify=list(targets) if use_stratify else None,
    )
    return HoldoutSplit(
        train_items=[items[index] for index in train_idx],
        test_items=[items[index] for index in test_idx],
        train_targets=[targets[index] for index in train_idx],
        test_targets=[targets[index] for index in test_idx],
        train_indices=train_idx,
        test_indices=test_idx,
        stratified=use_stratify,
        random_seed=random_seed,
        test_fraction=test_fraction,
    )


def split_group_supervised(
    items: Sequence[Any],
    targets: Sequence[Any],
    groups: Sequence[Any],
    *,
    test_fraction: float = 0.20,
    random_seed: int = 42,
) -> GroupHoldoutSplit:
    """Membuat holdout group-aware agar satu sumber tidak menyeberang split."""
    if not (len(items) == len(targets) == len(groups)):
        raise ValueError("Jumlah items, targets, dan groups harus sama")
    if len(items) < 5 or len(set(groups)) < 5:
        raise ValueError("Minimal 5 baris dan 5 grup diperlukan untuk group split")
    indices = list(range(len(items)))
    splitter = GroupShuffleSplit(
        n_splits=1, test_size=test_fraction, random_state=random_seed
    )
    train_array, test_array = next(splitter.split(indices, targets, groups))
    train_idx = [int(index) for index in train_array]
    test_idx = [int(index) for index in test_array]
    train_groups = sorted({groups[index] for index in train_idx}, key=str)
    test_groups = sorted({groups[index] for index in test_idx}, key=str)
    overlap = sorted(set(train_groups) & set(test_groups), key=str)
    return GroupHoldoutSplit(
        train_items=[items[index] for index in train_idx],
        test_items=[items[index] for index in test_idx],
        train_targets=[targets[index] for index in train_idx],
        test_targets=[targets[index] for index in test_idx],
        train_indices=train_idx,
        test_indices=test_idx,
        stratified=False,
        random_seed=random_seed,
        test_fraction=test_fraction,
        train_groups=train_groups,
        test_groups=test_groups,
        overlapping_groups=overlap,
    )
def make_cross_validator(
    targets: Sequence[Any],
    *,
    classification: bool,
    folds: int = 5,
    random_seed: int = 42,
):
    if classification and _can_stratify(targets):
        return StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_seed)
    return KFold(n_splits=folds, shuffle=True, random_state=random_seed)


def make_group_cross_validator(*, folds: int = 5, random_seed: int = 42) -> GroupKFold:
    """Group-aware CV yang reproducible untuk training split."""
    return GroupKFold(n_splits=folds, shuffle=True, random_state=random_seed)
