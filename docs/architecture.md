# How it works

## The patch

libpostal's address parser keeps its working buffers in shared global state, so concurrent calls corrupt each other (stock
libpostal crashes with 4 threads). `patches/0001-thread-safe-address-parser.patch` gives each thread its own scratch space.
`scripts/build_libpostal.sh` downloads libpostal, applies the patch and builds it.

## The plugin

A Rust Polars expression plugin calls the patched parser from Polars' own Rayon pool, so parsing shares threads with the rest
of the query and the model is loaded once per process. The wheel bundles the patched `libpostal.so` under a hashed name,
which keeps it apart from any other libpostal in the same process.

## Correctness

`scripts/stress.sh` builds a C program in which every thread parses the same addresses and compares each result with a
single-threaded reference. On the patched library, 280,000 concurrent parses on up to 14 threads gave 0 mismatches. The
Python suite repeats that check through the plugin (`tests/test_parse.py`).

!!! warning
    ThreadSanitizer has not been run to completion. Zero mismatches shows the output is right, not that there are no data
    races, so treat the patch as tested but not proven.

## Scope

Only the parser is bundled. libpostal's address expansion and language classifier are not used. Compatibility with a real
`pypostal` install in the same process is not yet tested.
