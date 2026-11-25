#!/usr/bin/env bash
# Run the thread-safety stress test under ThreadSanitizer.
#
#   LIBPOSTAL_DATA_DIR=/path/to/libpostal scripts/tsan.sh /opt/libpostal-tsan addresses.txt 8 [parse|expand]
#
# The mode picks the libpostal call under test: address parsing (the default),
# or address expansion, which also needs the language classifier data.
#
# Builds the patched libpostal with -fsanitize=thread into <prefix> unless it is
# already there, builds stress.c the same way, and runs it. Every data race
# ThreadSanitizer reports is printed. Exit codes:
#
#   0  no races reported and the stress test passed
#   1  ThreadSanitizer reported at least one race
#   2  no races reported, but the stress test failed, crashed or timed out
#
# The stress run is killed after $TSAN_TIMEOUT (default 15m). Stock libpostal can
# hang under its own race, and a hang must not hold a CI runner until the job
# times out. Races reported before the kill still count.
#
# Use a different prefix from the normal build: the instrumented library is
# several times slower and must not end up in a wheel.
#
# On Linux 6.x kernels with vm.mmap_rnd_bits=32 (WSL2 and recent Ubuntu), the GCC
# 11 / LLVM 14 sanitizer runtimes abort with "unexpected memory mapping". The
# script turns address randomisation off for its own processes with `setarch -R`
# when that works, which needs no system-wide change.
set -euo pipefail

PREFIX="${1:?usage: tsan.sh <prefix> <addresses.txt> [threads] [parse|expand]}"
ADDRESSES="${2:?usage: tsan.sh <prefix> <addresses.txt> [threads] [parse|expand]}"
THREADS="${3:-8}"
MODE="${4:-parse}"
TSAN_TIMEOUT="${TSAN_TIMEOUT:-15m}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

SAN="-fsanitize=thread -fno-omit-frame-pointer -g"

# Run a command with ASLR off if the kernel lets us, else as it is.
norand() {
    local arch
    arch="$(uname -m)"
    if command -v setarch >/dev/null 2>&1 && setarch "$arch" -R true 2>/dev/null; then
        setarch "$arch" -R "$@"
    else
        "$@"
    fi
}

if [ ! -e "$PREFIX/lib/libpostal.so" ]; then
    echo "building ThreadSanitizer libpostal into $PREFIX"
    # shellcheck disable=SC2086
    CFLAGS="$SAN -O1" LDFLAGS="-fsanitize=thread" norand "$HERE/build_libpostal.sh" "$PREFIX"
fi

# shellcheck disable=SC2086
cc -O1 $SAN "$HERE/stress.c" -o "$OUT/stress" \
    -I"$PREFIX/include" -L"$PREFIX/lib" -lpostal -lpthread -Wl,-rpath,"$PREFIX/lib"

status=0
TSAN_OPTIONS="log_path=$OUT/tsan halt_on_error=0 exitcode=0 history_size=7 ${TSAN_OPTIONS:-}" \
    norand timeout -k 30s "$TSAN_TIMEOUT" "$OUT/stress" "$ADDRESSES" "$THREADS" "$MODE" || status=$?

races=0
for report in "$OUT"/tsan.*; do
    [ -e "$report" ] || continue
    races=$((races + $(grep -c "WARNING: ThreadSanitizer" "$report" || true)))
done

if [ "$races" -gt 0 ]; then
    echo
    echo "ThreadSanitizer reported $races warning(s):"
    cat "$OUT"/tsan.* | head -n 400
    exit 1
fi
if [ "$status" -eq 124 ] || [ "$status" -eq 137 ]; then
    echo "the stress test timed out after $TSAN_TIMEOUT without a ThreadSanitizer report" >&2
    exit 2
fi
if [ "$status" -ne 0 ]; then
    echo "the stress test failed (exit $status) without a ThreadSanitizer report" >&2
    exit 2
fi
echo "ThreadSanitizer: no data races reported"
