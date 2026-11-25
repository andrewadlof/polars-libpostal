"""Behaviour of the expand_address expression."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal
from polars_libpostal import expand_address


def expand(
    addresses: list[str | None], languages: list[str] | None = None
) -> list[list[str] | None]:
    df = pl.DataFrame({"a": addresses}, schema={"a": pl.String})
    return df.select(expand_address("a", languages=languages).alias("e"))["e"].to_list()


def test_schema_is_known_without_expanding() -> None:
    # No model_dir fixture: resolving the schema must not load anything.
    lazy = pl.LazyFrame({"a": ["30 W 26th St"]}).with_columns(
        expand_address("a").alias("e")
    )
    assert lazy.collect_schema()["e"] == pl.List(pl.String)


def test_abbreviations_are_spelled_out(model_dir: Path) -> None:
    (forms,) = expand(["30 W 26th St"])
    assert forms is not None
    assert "30 west 26th street" in forms
    assert len(forms) == len(set(forms))


def test_the_classifier_picks_the_language(model_dir: Path) -> None:
    (forms,) = expand(["Quatre-vingt-douze Ave des Champs-Élysées"])
    assert forms is not None
    assert "92 avenue des champs elysees" in forms


def test_languages_are_used_as_given(model_dir: Path) -> None:
    # Read as English, "quatre-vingt-douze" is not a number.
    (forms,) = expand(["Quatre-vingt-douze Ave des Champs-Élysées"], languages=["en"])
    assert forms is not None
    assert "quatre vingt douze avenue des champs elysees" in forms
    assert not any(form.startswith("92") for form in forms)


def test_null_and_empty_give_null(model_dir: Path) -> None:
    assert expand([None, "", "1 Main St"])[:2] == [None, None]


def test_row_order_is_kept(model_dir: Path) -> None:
    addresses = [f"{n} Main St" for n in range(2_000)]
    out = expand(addresses, languages=["en"])
    assert all(
        forms is not None and f"{n} main street" in forms for n, forms in enumerate(out)
    )


@pytest.mark.parametrize("languages", [[], ["en", "en"], ["EN"], ["english"], [""]])
def test_bad_languages_are_rejected(languages: list[str]) -> None:
    with pytest.raises(ValueError, match="languages"):
        expand_address("a", languages=languages)


def test_works_on_a_lazy_frame_with_parsing(model_dir: Path) -> None:
    from polars_libpostal import parse_address  # noqa: PLC0415

    lazy = pl.LazyFrame({"a": ["10 Downing St, London"]}).select(
        expand_address("a").alias("e"),
        parse_address("a", labels=["road"]).struct.field("road"),
    )
    out = lazy.collect()
    assert "10 downing street london" in out["e"][0]
    assert out["road"][0] == "downing st"


def _run(code: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", textwrap.dedent(code), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_languages_do_not_need_the_classifier(model_dir: Path, tmp_path: Path) -> None:
    """With languages given, only the shared dictionaries are loaded."""
    for folder in ("address_expansions", "numex", "transliteration"):
        (tmp_path / folder).symlink_to(model_dir / folder)
    done = _run(
        """
        import sys, polars as pl
        from polars_libpostal import expand_address
        df = pl.DataFrame({"a": ["1 Main St"]})
        print(df.select(expand_address("a", languages=["en"], data_dir=sys.argv[1]))
              .item().to_list())
        try:
            df.select(expand_address("a", data_dir=sys.argv[1]))
        except Exception as e:
            print(type(e).__name__, e)
        """,
        str(tmp_path),
    )
    assert done.returncode == 0, done.stderr
    first, second = done.stdout.splitlines()[:2]
    assert "1 main street" in first
    assert "language_classifier" in second
    assert "download-data" in second


def test_many_threads_match_one_thread(model_dir: Path, tmp_path: Path) -> None:
    """Concurrent expansion must give exactly the single-threaded answer."""
    addresses = [
        f"{n} {street}, Apt {n % 17}, {city}"
        for n in range(1, 1_001)
        for street, city in [
            ("Oak St", "Springfield IL"),
            ("Rue de Rivoli", "Paris"),
            ("Calle Mayor", "Madrid"),
        ]
    ]
    many = pl.DataFrame({"a": addresses}).select(expand_address("a").alias("e"))

    src, dst = tmp_path / "in.parquet", tmp_path / "out.parquet"
    pl.DataFrame({"a": addresses}).write_parquet(src)
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                """
                import sys, polars as pl
                from polars_libpostal import expand_address
                pl.read_parquet(sys.argv[1]).select(
                    expand_address("a").alias("e")
                ).write_parquet(sys.argv[2])
                """
            ),
            str(src),
            str(dst),
        ],
        check=True,
        env={**os.environ, "POLARS_MAX_THREADS": "1"},
    )
    assert_frame_equal(many, pl.read_parquet(dst))
