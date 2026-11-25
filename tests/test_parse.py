"""Behaviour of the parse_address expression."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal
from polars_libpostal import LABELS, parse_address


def parse(frame: pl.DataFrame | pl.LazyFrame, column: str = "a") -> pl.DataFrame:
    result = frame.with_columns(parse_address(column).alias("p")).unnest("p")
    return result.collect() if isinstance(result, pl.LazyFrame) else result


def test_schema_is_known_without_parsing() -> None:
    lazy = pl.LazyFrame({"a": ["10 Downing St"]}).with_columns(
        parse_address("a").alias("p")
    )
    schema = lazy.collect_schema()
    assert schema["p"] == pl.Struct(dict.fromkeys(LABELS, pl.String))


def test_parses_components(model_dir: Path) -> None:
    df = parse(pl.DataFrame({"a": ["Apt 4B, 456 Elm Ave, Springfield"]}))
    row = df.row(0, named=True)
    assert row["house_number"] == "456"
    assert row["road"] == "elm ave"
    assert row["unit"] == "apt 4b"
    assert row["city"] == "springfield"
    assert row["state"] is None


def test_every_label_is_its_own_field(model_dir: Path) -> None:
    df = parse(pl.DataFrame({"a": ["Apt 4B, 456 Elm Ave, Springfield, IL 62704, USA"]}))
    row = df.row(0, named=True)
    assert row["city"] == "springfield"
    assert row["state"] == "il"
    assert row["postcode"] == "62704"
    assert row["country"] == "usa"


def test_labels_selects_and_orders_fields(model_dir: Path) -> None:
    labels = ["city", "road"]
    lazy = pl.LazyFrame({"a": ["456 Elm Ave, Springfield"]}).with_columns(
        parse_address("a", labels=labels).alias("p")
    )
    assert lazy.collect_schema()["p"] == pl.Struct(dict.fromkeys(labels, pl.String))
    assert lazy.collect().unnest("p").row(0, named=True) == {
        "a": "456 Elm Ave, Springfield",
        "city": "springfield",
        "road": "elm ave",
    }


@pytest.mark.parametrize("labels", [[], ["road", "road"], ["road", "street"]])
def test_bad_labels_are_rejected(labels: list[str]) -> None:
    with pytest.raises(ValueError, match="label"):
        parse_address("a", labels=labels)


def test_null_and_empty_give_null_fields(model_dir: Path) -> None:
    df = parse(
        pl.DataFrame({"a": [None, "", "10 Downing St"]}, schema={"a": pl.String})
    )
    assert df.select(LABELS).row(0) == (None,) * len(LABELS)
    assert df.select(LABELS).row(1) == (None,) * len(LABELS)
    assert df["road"][2] == "downing st"


def test_row_order_and_repeats_are_kept(model_dir: Path) -> None:
    streets = [f"{n} Main St" for n in range(2_000)]
    addresses = [*streets, *streets[:100], None, "10 Downing St"]
    df = parse(pl.DataFrame({"a": addresses}, schema={"a": pl.String}))
    assert df["a"].to_list() == addresses
    assert df["house_number"].to_list()[:2_000] == [str(n) for n in range(2_000)]
    assert df["house_number"][2_000:2_100].to_list() == [str(n) for n in range(100)]


def test_works_on_a_lazy_frame(model_dir: Path) -> None:
    lazy = pl.LazyFrame({"a": ["10 Downing St", "1600 Pennsylvania Ave NW"]})
    out = parse(lazy)
    assert out["house_number"].to_list() == ["10", "1600"]


def test_many_threads_match_one_thread(model_dir: Path, tmp_path: Path) -> None:
    """
    Concurrent parsing must give exactly the single-threaded answer.

    Stock libpostal fails this: it shares one parse context between callers.
    """
    addresses = [
        f"{n} {street} {kind}, Apt {n % 17}, City {n % 53}"
        for n in range(1, 4_001)
        for street, kind in [("Oak", "St"), ("Maple", "Avenue"), ("Rue de Rivoli", "")]
    ][:6_000]
    many = parse(pl.DataFrame({"a": addresses}))

    script = textwrap.dedent(
        """
        import sys, polars as pl
        from polars_libpostal import parse_address
        addresses = pl.read_parquet(sys.argv[1])["a"]
        out = pl.DataFrame({"a": addresses}).with_columns(
            parse_address("a").alias("p")
        ).unnest("p")
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


def test_missing_data_is_a_clear_error(tmp_path: Path) -> None:
    code = textwrap.dedent(
        """
        import polars as pl, sys
        from polars_libpostal import parse_address
        try:
            pl.DataFrame({"a": ["1 Main St"]}).select(
                parse_address("a", data_dir=sys.argv[1])
            )
        except Exception as e:
            print(type(e).__name__, e)
            raise SystemExit(0)
        raise SystemExit("no error was raised")
        """
    )
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code, str(tmp_path / "nothing")],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "download-data" in done.stdout
