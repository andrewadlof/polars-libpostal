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
from typing import TYPE_CHECKING

import polars as pl
from polars.plugins import register_plugin_function

from polars_libpostal._data import data_dir, download_data

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "LABELS",
    "data_dir",
    "download_data",
    "parse_address",
    "parse_address_list",
]

#: Every label libpostal's address parser can return, in the order that
#: ``parse_address`` returns them by default.
LABELS = (
    "house",
    "category",
    "near",
    "house_number",
    "road",
    "unit",
    "level",
    "staircase",
    "entrance",
    "po_box",
    "postcode",
    "suburb",
    "city_district",
    "city",
    "island",
    "state_district",
    "state",
    "country_region",
    "country",
    "world_region",
)

_PLUGIN_DIR = Path(__file__).parent


def _folder(data_dir: str | os.PathLike[str] | None) -> str:
    from polars_libpostal import _data  # noqa: PLC0415

    return str(Path(data_dir) if data_dir is not None else _data.data_dir())


def parse_address(
    address: pl.Expr | str,
    *,
    labels: Sequence[str] | None = None,
    data_dir: str | os.PathLike[str] | None = None,  # noqa: F811
) -> pl.Expr:
    """
    Parse addresses into libpostal components, in parallel.

    Parameters
    ----------
    address : pl.Expr | str
        String expression (or column name) holding the address text.
    labels : Sequence[str] | None
        Labels to return, in output order. Defaults to all of ``LABELS``.
    data_dir : str | os.PathLike[str] | None
        Directory with the libpostal model data. Defaults to the result of
        ``polars_libpostal.data_dir()``. The models load once per process, on
        the first call, from the first directory used.

    Returns
    -------
    pl.Expr
        Struct expression with one string field per requested label. A label
        that libpostal returns more than once is joined with a space. Labels
        that are absent, and null or empty addresses, give null fields.

    Raises
    ------
    ValueError
        If ``labels`` is empty, repeats a label, or names a label that
        libpostal does not have.

    Notes
    -----
    libpostal ignores the country when parsing, so there is no country
    argument: the same address parses the same way everywhere.
    """
    chosen = list(LABELS if labels is None else labels)
    unknown = [label for label in chosen if label not in LABELS]
    if unknown:
        msg = f"unknown libpostal label(s) {unknown}; choose from {list(LABELS)}"
        raise ValueError(msg)
    if not chosen or len(set(chosen)) != len(chosen):
        msg = "labels must be a non-empty list without repeats"
        raise ValueError(msg)

    expr = pl.col(address) if isinstance(address, str) else address
    return register_plugin_function(
        plugin_path=_PLUGIN_DIR,
        function_name="parse_address",
        args=expr,
        kwargs={"data_dir": _folder(data_dir), "labels": chosen},
        is_elementwise=True,
    )


def parse_address_list(
    address: pl.Expr | str,
    *,
    data_dir: str | os.PathLike[str] | None = None,  # noqa: F811
) -> pl.Expr:
    """
    Parse addresses into libpostal components, in address order, in parallel.

    Unlike ``parse_address``, this keeps libpostal's own response: one element
    per component, in the order the components appear in the address text,
    with repeated labels left as separate elements.

    Parameters
    ----------
    address : pl.Expr | str
        String expression (or column name) holding the address text.
    data_dir : str | os.PathLike[str] | None
        Directory with the libpostal model data, as for ``parse_address``.

    Returns
    -------
    pl.Expr
        Expression of type ``List(Struct({"label": String, "value": String}))``.
        Labels are those in ``LABELS``. Null or empty addresses give null.

    Examples
    --------
    Fold every label except a few into one column, in address order:

    >>> kept = ["house", "house_number", "road", "unit", "level", "po_box"]
    >>> label = pl.element().struct.field("label")
    >>> value = pl.element().struct.field("value")
    >>> df.with_columns(
    ...     parse_address_list("address")
    ...     .list.eval(value.filter(~label.is_in(kept)))
    ...     .list.join(" ")
    ...     .alias("other")
    ... )  # doctest: +SKIP

    Get one row per component, for grouping or joining:

    >>> df.with_columns(parts=parse_address_list("address")).explode(
    ...     "parts"
    ... ).unnest("parts")  # doctest: +SKIP
    """
    expr = pl.col(address) if isinstance(address, str) else address
    return register_plugin_function(
        plugin_path=_PLUGIN_DIR,
        function_name="parse_address_list",
        args=expr,
        kwargs={"data_dir": _folder(data_dir)},
        is_elementwise=True,
    )
