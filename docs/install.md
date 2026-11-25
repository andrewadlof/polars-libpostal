# Install

Add it to a project with [uv](https://docs.astral.sh/uv/):

```bash
uv add polars-libpostal
uv run python -m polars_libpostal download-data    # about 3 GB, once
```

Or try it without adding anything:

```bash
uv run --with polars-libpostal python -m polars_libpostal download-data
```

Wheels are built for Linux x86_64 and aarch64 (manylinux_2_28, Python 3.11+) and bundle the patched libpostal. There is no sdist: it
could not build without the patched library. See [Building from source](building.md).

## Model data

The model data is looked up in this order:

1. `$LIBPOSTAL_DATA_DIR`
2. an existing libpostal install at `/usr/local/share/libpostal`
3. `~/.local/share/polars-libpostal`

`uv run python -m polars_libpostal data-dir` prints the one that will be used, and `parse_address(..., data_dir=...)`
overrides it. The models load on the first call in a process.

## Command line

| Command                                           | What it does                                  |
| ------------------------------------------------- | --------------------------------------------- |
| `uv run python -m polars_libpostal download-data` | Download the model data (`--dest`, `--force`) |
| `uv run python -m polars_libpostal data-dir`      | Print the data directory that will be used    |
