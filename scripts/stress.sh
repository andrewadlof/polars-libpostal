#!/usr/bin/env bash
# Build and run the C stress test against a libpostal install.
#
#   LIBPOSTAL_DATA_DIR=/path/to/libpostal scripts/stress.sh /opt/libpostal addresses.txt 8 [parse|expand]
#
# The mode picks the libpostal call under test: address parsing (the default),
# or address expansion, which also needs the language classifier data.
#
# One address per line. Every thread parses all addresses and compares them with
# a single-threaded reference: the patched library must report 0 mismatches,
# while stock libpostal crashes or mixes up results with more than one thread.
set -euo pipefail

PREFIX="${1:?usage: stress.sh <prefix> <addresses.txt> [threads] [parse|expand]}"
ADDRESSES="${2:?usage: stress.sh <prefix> <addresses.txt> [threads] [parse|expand]}"
THREADS="${3:-8}"
MODE="${4:-parse}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

cc -O2 "$HERE/stress.c" -o "$OUT/stress" \
    -I"$PREFIX/include" -L"$PREFIX/lib" -lpostal -lpthread -Wl,-rpath,"$PREFIX/lib"
"$OUT/stress" "$ADDRESSES" "$THREADS" "$MODE"
