#!/usr/bin/env bash
# Build and run the C stress test against a libpostal install.
#
#   scripts/stress.sh /opt/libpostal /path/to/addresses.txt 8
#
# One address per line. Every thread parses all addresses and compares them with
# a single-threaded reference: the patched library must report 0 mismatches,
# while stock libpostal crashes or mixes up results with more than one thread.
set -euo pipefail

PREFIX="${1:?usage: stress.sh <prefix> <addresses.txt> [threads]}"
ADDRESSES="${2:?usage: stress.sh <prefix> <addresses.txt> [threads]}"
THREADS="${3:-8}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

cc -O2 "$HERE/stress.c" -o "$OUT/stress" \
    -I"$PREFIX/include" -L"$PREFIX/lib" -lpostal -lpthread -Wl,-rpath,"$PREFIX/lib"
"$OUT/stress" "$ADDRESSES" "$THREADS"
