#!/usr/bin/env bash
# Build libpostal with the thread-safe parser patch into a private prefix.
#
#   scripts/build_libpostal.sh /opt/libpostal
#   LIBPOSTAL_PREFIX=/opt/libpostal maturin develop
#
# The stock library cannot be used: it shares one parse context between all
# callers, so parsing from several threads corrupts memory. See
# patches/0001-thread-safe-address-parser.patch.
#
# Needs git, a C compiler, make, autoconf, automake, libtool and pkg-config.
# Model data is not built in: run `python -m polars_libpostal download-data`.
set -euo pipefail

PREFIX="$(realpath -m "${1:?usage: build_libpostal.sh <prefix>}")"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The upstream commit the patch was made against
UPSTREAM="https://github.com/openvenues/libpostal"
COMMIT="25099c506612b34b23b1bfe286ca6321fcf06f35"

SRC="$(mktemp -d)"
trap 'rm -rf "$SRC"' EXIT

git init -q "$SRC"
git -C "$SRC" fetch -q --depth 1 "$UPSTREAM" "$COMMIT"
git -C "$SRC" checkout -q FETCH_HEAD
git -C "$SRC" apply "$HERE"/patches/*.patch

cd "$SRC"
./bootstrap.sh
# libpostal predates C23, where `false` became a keyword: upstream has
# `return false;` in a function that returns a pointer (trie_search.c), which
# GCC 14 rejects when it defaults to C23. Build as C11.
export CFLAGS="${CFLAGS:-} -std=gnu11"
# libpostal's SIMD code is x86 SSE2 only, so ARM builds need --disable-sse2.
EXTRA=()
case "$(uname -m)" in
    aarch64|arm64) EXTRA+=(--disable-sse2) ;;
esac
./configure --prefix="$PREFIX" --datadir="$PREFIX/share" --disable-data-download "${EXTRA[@]}"
make -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)"
make install
echo "patched libpostal installed in $PREFIX"
