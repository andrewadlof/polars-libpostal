# Define project root
root := justfile_directory()

# Where `libpostal` is built and linked from. Override with LIBPOSTAL_PREFIX.
export LIBPOSTAL_PREFIX := env_var_or_default("LIBPOSTAL_PREFIX", root / ".libpostal")

# Point pyo3 at the project venv's interpreter.
export PYO3_PYTHON := justfile_directory() / ".venv/bin/python"

# List available recipes
default:
    @just --list

# ----------------------------------------------------------------------------
# dev
# ----------------------------------------------------------------------------

# Build the patched libpostal into $LIBPOSTAL_PREFIX (once)
[group('dev')]
libpostal:
    test -e "{{LIBPOSTAL_PREFIX}}/lib/libpostal.so" || scripts/build_libpostal.sh "{{LIBPOSTAL_PREFIX}}"

# Build the extension into the venv in-place (debug), so tests see it
[group('dev')]
dev: libpostal
    uv run maturin develop --uv

# Run the Python suite (tests that parse skip until the model data is installed)
[group('dev')]
test *args: dev
    uv run pytest {{args}}

# Download the libpostal model data (about 3 GB)
[group('dev')]
data:
    uv run python -m polars_libpostal download-data

# Lint with ruff and auto-fix what it safely can
[group('dev')]
lint *args:
    uv run ruff check --fix {{args}}

# Format the codebase with ruff and rustfmt
[group('dev')]
format:
    uv run ruff format
    cargo fmt

# Lint (no fixes) + format check + tests
[group('dev')]
check: dev
    cargo fmt --check
    cargo clippy --all-targets -- -D warnings
    uv run ruff check
    uv run ruff format --check
    uv run pytest

# ----------------------------------------------------------------------------
# docs
# ----------------------------------------------------------------------------

# Live-preview the docs at http://localhost:8000
[group('docs')]
docs-serve:
    uv run --only-group docs zensical serve

# Build the static docs site into ./site
[group('docs')]
docs-build:
    uv run --only-group docs zensical build --clean

# ----------------------------------------------------------------------------
# release
#
# Releases are cut by CI: push a v<version> tag and .github/workflows/release.yml
# builds the manylinux wheel (bundling the patched libpostal) and publishes it
# through PyPI Trusted Publishing. Published versions are immutable.
# ----------------------------------------------------------------------------

# Print the current package version
[group('release')]
version:
    uv version --short

# Bump the version: `just bump patch` | minor | major
[group('release')]
bump level="patch":
    uv version --bump {{level}}

# Guard: refuse to tag a release from anywhere but `main`
[private]
_require-main:
    #!/usr/bin/env bash
    set -euo pipefail
    branch="$(git rev-parse --abbrev-ref HEAD)"
    if [ "$branch" != "main" ]; then
        echo "error: release tags are cut from 'main', but you are on '$branch'." >&2
        exit 1
    fi

# Tag the current version and push it, which triggers the release workflow
[group('release')]
tag: _require-main
    #!/usr/bin/env bash
    set -euo pipefail
    version="$(uv version --short)"
    echo "Tagging v$version"
    git tag "v$version"
    git push origin "v$version"
