# Building from source

You need a Rust toolchain, [uv](https://docs.astral.sh/uv/), and the autotools to build libpostal.

```bash
git clone https://github.com/andrewadlof/polars-libpostal
cd polars-libpostal
uv sync               # creates the venv and installs the dev tools
uv run just libpostal # patched libpostal into ./.libpostal (about 15 minutes)
uv run just dev       # build the extension into the venv
uv run just data      # download the model data
uv run just test
```

or by hand:

```bash
scripts/build_libpostal.sh /opt/libpostal
LIBPOSTAL_PREFIX=/opt/libpostal LD_LIBRARY_PATH=/opt/libpostal/lib uv run maturin develop --uv
```

!!! danger
    Linking against stock libpostal builds fine and then fails or corrupts memory under load. Always use the patched build.

## Documentation

These docs are built with [Zensical](https://zensical.org). The `docs` dependency group is separate from the dev tools, so
it installs without a Rust toolchain.

```bash
uv run --only-group docs zensical serve        # live preview at http://localhost:8000
uv run --only-group docs zensical build --clean # static site into ./site
```

or `uv run just docs-serve` and `uv run just docs-build`.
