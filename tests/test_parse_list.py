"""Behaviour of the parse_address_list expression."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal, assert_series_equal
from polars_libpostal import LABELS, parse_address, parse_address_list

PARTS = pl.List(pl.Struct({"label": pl.String, "value": pl.String}))

ADDRESSES = [
    "Apt 4B, 456 Elm Ave, Springfield, IL 62704",
    "Apt 4B, 456 Elm Ave, Springfield, IL 62704, USA",
    "10 Downing St, London SW1A 2AA, United Kingdom",
    "1600 Pennsylvania Ave NW, Washington, DC 20500",
    "Flat 3, 12 Railway Terrace, Seattle WA 98101",
    "PO Box 1234, Anchorage, AK 99501",
    "Rue de Rivoli 99, 75001 Paris, France",
    "Calle Mayor 5, 3o izquierda, 28013 Madrid",
    "Hauptstrasse 12, 10115 Berlin, Deutschland",
    "Empire State Building, 350 5th Ave, New York, NY 10118",
    "Level 2, 100 George St, Sydney NSW 2000, Australia",
    "near the old mill, Route 9, Hudson Valley",
    "Suite 500, 1 Infinite Loop, Cupertino, CA 95014",
    "Barcelona Spain",
]


def parts(addresses: list[str | None]) -> list[list[tuple[str, str]] | None]:
    df = pl.DataFrame({"a": addresses}, schema={"a": pl.String})
    out = df.select(parse_address_list("a").alias("p"))["p"].to_list()
    return [
        None if row is None else [(c["label"], c["value"]) for c in row] for row in out
    ]


def test_schema_is_known_without_parsing() -> None:
    # No model_dir fixture: resolving the schema must not load the model.
    lazy = pl.LazyFrame({"a": ["10 Downing St"]}).with_columns(
        parse_address_list("a").alias("p")
    )
    assert lazy.collect_schema()["p"] == PARTS


def test_components_are_in_address_order(model_dir: Path) -> None:
    (row,) = parts(["Apt 4B, 456 Elm Ave, Springfield, IL 62704"])
    assert row is not None
    assert [label for label, _ in row] == [
        "unit",
        "house_number",
        "road",
        "city",
        "state",
        "postcode",
    ]
    assert dict(row)["postcode"] == "62704"


def test_labels_are_libpostal_labels(model_dir: Path) -> None:
    for row in parts(ADDRESSES):
        assert row
        assert {label for label, _ in row} <= set(LABELS)


def test_agrees_with_parse_address(model_dir: Path) -> None:
    """Joining each label's values in order gives the parse_address field."""
    df = pl.DataFrame({"a": ADDRESSES}).with_row_index("row")
    expected = (
        df.select("row", parse_address("a").alias("p"))
        .unnest("p")
        .unpivot(index="row", variable_name="label", value_name="value")
        .drop_nulls("value")
    )
    joined = (
        df.select("row", parse_address_list("a").alias("parts"))
        .explode("parts")
        .unnest("parts")
        .group_by("row", "label", maintain_order=True)
        .agg(pl.col("value").str.join(" "))
    )
    assert_frame_equal(joined, expected, check_row_order=False)


def test_null_and_empty_give_null(model_dir: Path) -> None:
    out = parts([None, "", "10 Downing St"])
    assert out[0] is None
    assert out[1] is None
    assert out[2] == [("house_number", "10"), ("road", "downing st")]


def test_works_on_a_lazy_frame(model_dir: Path) -> None:
    lazy = pl.LazyFrame({"a": ["10 Downing St", "1600 Pennsylvania Ave NW"]})
    out = lazy.select(parse_address_list("a").alias("p")).collect()
    assert out.schema["p"] == PARTS
    assert_series_equal(
        out["p"].list.first().struct.field("value"),
        pl.Series("value", ["10", "1600"]),
    )


@pytest.mark.parametrize("n", [1, 2_500])
def test_row_order_and_repeats_are_kept(model_dir: Path, n: int) -> None:
    streets = [f"{k} Main St" for k in range(n)]
    addresses: list[str | None] = [*streets, None, *streets[:10], ""]
    out = parts(addresses)
    assert len(out) == len(addresses)
    numbers = [None if row is None else row[0][1] for row in out]
    expected = [str(k) for k in range(n)]
    assert numbers == [*expected, None, *expected[:10], None]


def test_many_threads_match_one_thread(model_dir: Path, tmp_path: Path) -> None:
    """Concurrent parsing must give exactly the single-threaded answer."""
    addresses = [
        f"{n} {street} {kind}, Apt {n % 17}, City {n % 53}"
        for n in range(1, 4_001)
        for street, kind in [("Oak", "St"), ("Maple", "Avenue"), ("Rue de Rivoli", "")]
    ][:6_000]
    many = pl.DataFrame({"a": addresses}).select(parse_address_list("a").alias("p"))

    script = textwrap.dedent(
        """
        import sys, polars as pl
        from polars_libpostal import parse_address_list
        addresses = pl.read_parquet(sys.argv[1])["a"]
        out = pl.DataFrame({"a": addresses}).select(
            parse_address_list("a").alias("p")
        )
        out.write_parquet(sys.argv[2])
        """
    )
    src, dst = tmp_path / "in.parquet", tmp_path / "out.parquet"
    pl.DataFrame({"a": addresses}).write_parquet(src)
    subprocess.run(  # noqa: S603
        [sys.executable, "-c", script, str(src), str(dst)],
        check=True,
        env={**os.environ, "POLARS_MAX_THREADS": "1"},
    )
    single = pl.read_parquet(dst)

    assert_frame_equal(many, single)
