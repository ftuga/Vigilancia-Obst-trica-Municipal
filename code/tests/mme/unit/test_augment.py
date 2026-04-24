"""Tests de feature augmentation — `src/mme/features/augment.py`."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mme.features.augment import LOG_POP_COL, augment_with_offset


def test_augment_adds_column() -> None:
    """augment_with_offset agrega la columna log_pop_sem."""
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [10.0, 20.0, 30.0]})
    offset = np.array([0.1, 0.2, 0.3])
    out = augment_with_offset(X, offset)
    assert LOG_POP_COL in out.columns
    assert list(out.columns) == ["a", "b", LOG_POP_COL]
    np.testing.assert_array_equal(out[LOG_POP_COL].to_numpy(), offset)


def test_augment_does_not_mutate_input() -> None:
    """El input no debe mutarse."""
    X = pd.DataFrame({"a": [1.0, 2.0]})
    offset = np.array([0.1, 0.2])
    _ = augment_with_offset(X, offset)
    assert LOG_POP_COL not in X.columns


def test_augment_rejects_mismatched_lengths() -> None:
    """X y offset con shapes distintos → error."""
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    offset = np.array([0.1, 0.2])
    with pytest.raises(ValueError, match="no coinciden"):
        augment_with_offset(X, offset)
