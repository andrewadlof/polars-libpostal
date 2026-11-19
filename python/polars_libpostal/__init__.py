"""
Parallel libpostal address parsing as a Polars expression.

>>> import polars as pl
>>> from polars_libpostal import parse_address
>>> df = pl.DataFrame({"address": ["10 Downing St, London"]})
>>> df.with_columns(parse_address("address").alias("p")).unnest("p")  # doctest: +SKIP
"""

from __future__ import annotations

import os
from pathlib import Path

import polars as pl
from polars.plugins import register_plugin_function

from polars_libpostal._data import data_dir, download_data

__all__ = ["COMPONENTS", "data_dir", "download_data", "parse_address"]

#: Fields of the struct that ``parse_address`` returns. Every other libpostal
#: label (suburb, city, state, postcode, ...) is folded into ``other``.
COMPONENTS = (
    "house",
    "house_number",
    "road",
    "unit",
    "level",
    "po_box",
    "other",
)

_PLUGIN_DIR = Path(__file__).parent


def parse_address(
    address: pl.Expr | str,
    *,
    data_dir: str | os.PathLike[str] | None = None,  # noqa: F811
) -> pl.Expr:
    """
    Parse addresses into libpostal components, in parallel.

    Parameters
    ----------
    address : pl.Expr | str
        String expression (or column name) holding the address text.
    data_dir : str | os.PathLike[str] | None
        Directory with the libpostal model data. Defaults to the result of
        ``polars_libpostal.data_dir()``. The models load once per process, on
        the first call, from the first directory used.

    Returns
    -------
    pl.Expr
        Struct expression with one string field per name in ``COMPONENTS``.
        Components that libpostal labels more than once are joined with a
        space. Null and empty addresses give null fields.

    Notes
    -----
    libpostal ignores the country when parsing, so there is no country
    argument: the same address parses the same way everywhere.
    """
    from polars_libpostal import _data  # noqa: PLC0415

    expr = pl.col(address) if isinstance(address, str) else address
    folder = Path(data_dir) if data_dir is not None else _data.data_dir()
    return register_plugin_function(
        plugin_path=_PLUGIN_DIR,
        function_name="parse_address",
        args=expr,
        kwargs={"data_dir": str(folder)},
        is_elementwise=True,
    )
