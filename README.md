# polars-libpostal

Parse street addresses with [libpostal](https://github.com/openvenues/libpostal) as a Polars expression that runs on every
core.

```python
import polars as pl
from polars_libpostal import parse_address

df = pl.DataFrame({"address": ["Apt 4B, 456 Elm Ave, Springfield, IL 62704", None]})
df.with_columns(
    parse_address(
        "address", labels=["house_number", "road", "unit", "city", "state", "postcode"]
    ).alias("p")
).unnest("p")
```

```
address                                       house_number  road     unit    city         state  postcode
Apt 4B, 456 Elm Ave, Springfield, IL 62704    456           elm ave  apt 4b  springfield  il     62704
null                                          null          null     null    null         null   null
```

`parse_address` returns a struct with one field per libpostal label: `house`, `category`, `near`, `house_number`, `road`,
`unit`, `level`, `staircase`, `entrance`, `po_box`, `postcode`, `suburb`, `city_district`, `city`, `island`,
`state_district`, `state`, `country_region`, `country` and `world_region`. Pass `labels=[...]` to get only some of them, in
the order you give. A label that is absent, or null or empty input, gives null. A label that appears twice is joined with a
space. Output is lowercase, as libpostal produces it. It works on `LazyFrame`s and the output schema is known without
parsing anything.

## Why this exists

libpostal is a C library, but it cannot be called from several threads: its address parser reuses one parse context, one
CRF scoring context and one Viterbi buffer for every caller. Parse from two threads and they overwrite each other's
buffers (`Error in prediction`, then `double free or corruption` in a stress test). The usual Python binding also holds the
GIL, so the common answer is one process per core, each loading its own 3 GB model.

This package ships a patched libpostal (`patches/0001-thread-safe-address-parser.patch`) that gives each thread its own
scratch space, and a Rust plugin that parses rows on Polars' own Rayon pool. One process, one copy of the model, all cores.

## Install

```bash
uv add polars-libpostal
uv run python -m polars_libpostal download-data    # about 3 GB, once
```

Without uv, `pip install polars-libpostal` works too, followed by `python -m polars_libpostal download-data`.

Wheels are built for Linux x86_64 (manylinux_2_28, Python 3.11+) and bundle the patched libpostal. There is no sdist: it
could not build without the patched library. See [Building from source](#building-from-source).

The model data is looked up in this order: `$LIBPOSTAL_DATA_DIR`, an existing libpostal install at
`/usr/local/share/libpostal`, then `~/.local/share/polars-libpostal`. `uv run python -m polars_libpostal data-dir` prints the
one that will be used, and `parse_address(..., data_dir=...)` overrides it. The models load on the first call in a process.

## Speed

Measured on 14 cores (WSL2) with 193,500 distinct addresses:

| Parser                                      | Throughput                 |
| ------------------------------------------- | -------------------------- |
| libpostal through its Python binding        | about 10,000 addresses/s   |
| `polars-libpostal` on 14 threads            | about 54,000 addresses/s   |

The patched parser scales to about 4x at 4 threads and 6x at 8 threads in the C stress test, then flattens, so expect
roughly that. The plugin parses every row, repeated ones included. If your data has many repeats, parse the distinct values
and join the result back.

## Correctness

`scripts/stress.sh` builds a C program in which every thread parses the same addresses and compares each result with a
single-threaded reference. On the patched library, 280,000 concurrent parses on up to 14 threads gave 0 mismatches; stock
libpostal crashes with 4 threads. The Python suite repeats that check through the plugin (`tests/test_parse.py`).

ThreadSanitizer has not been run to completion. Zero mismatches shows the output is right, not that there are no data
races, so treat the patch as tested but not proven.

## Notes

- libpostal ignores the country when it parses (its parser sets language and country to NULL, because the model was trained
  without them), so there is no country argument.
- Only the parser is bundled. libpostal's address expansion and language classifier are not used.
- The plugin and any other libpostal in the same process (for example `pypostal` linked to the stock library) should not
  share a library name. The wheel bundles its copy under a hashed name, which keeps them apart; this is not yet tested
  against a real `pypostal` install.

## Building from source

You need a Rust toolchain, `uv`, and the autotools to build libpostal.

```bash
uv sync                  # creates the venv and installs the dev tools
uv run just libpostal    # patched libpostal into ./.libpostal (about 15 minutes)
uv run just dev          # build the extension into the venv
uv run just data         # download the model data
uv run just test
```

or by hand: `scripts/build_libpostal.sh /opt/libpostal`, then
`LIBPOSTAL_PREFIX=/opt/libpostal LD_LIBRARY_PATH=/opt/libpostal/lib uv run maturin develop --uv`. Linking against stock libpostal builds
fine and then fails or corrupts memory under load, so always use the patched build.

## Licensing

The code in this repository is licensed under either of [Apache-2.0](LICENSE-APACHE) or [MIT](LICENSE-MIT), at your
option. Wheels bundle libpostal (MIT) and the patch is distributed under its terms; the model data is downloaded from
Senzing and has its own terms. See [NOTICE](NOTICE).
