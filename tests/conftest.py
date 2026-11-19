"""Shared fixtures: tests that parse need the libpostal model data."""

from __future__ import annotations

from pathlib import Path

import pytest
from polars_libpostal import _data


@pytest.fixture(scope="session")
def model_dir() -> Path:
    """Directory with the libpostal data, or skip when it is not installed."""
    path = _data.data_dir()
    if not _data.is_complete(path):
        pytest.skip(
            f"no libpostal data in {path}; run `python -m polars_libpostal download-data`"
        )
    return path
