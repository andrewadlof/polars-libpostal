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

### ThreadSanitizer

`scripts/tsan.sh` builds libpostal and the stress test with `-fsanitize=thread` and runs it. On the patched library it
reports no data races (8 threads, 80,000 parses). As a control, the same run on stock libpostal reports races in
`uint32_array_clear`, `uint32_array_push` and `address_parser_context_fill`, the shared parse context the patch removes, and
then crashes. The `ThreadSanitizer` workflow runs both variants on demand and on changes to the patch or scripts, and fails if
the patched library reports a race or if the control finds none.

!!! note
    ThreadSanitizer only reports races that happen during the run, so this is strong evidence for the addresses and code
    paths tested, not a proof.

### Expansion

`expand_address` needs no patch. libpostal's expansion and language classifier only read their loaded models (the
dictionaries, transliteration tables and classifier weights) and allocate their working buffers per call. The stress test
has an `expand` mode (`scripts/stress.sh ... 8 expand`, `scripts/tsan.sh ... 4 expand`). On 5,000 multilingual addresses
with 8 threads, ThreadSanitizer reports no data races and 0 of 40,000 expansions differ from the single-threaded ones,
on the patched library and on stock libpostal alike. CI runs the expansion stress test, and the `ThreadSanitizer` workflow
runs it on the patched build.

## Scope

The parser, address expansion and the language classifier are used. libpostal's near-duplicate hashing and its
`expand_address_root` variant are not. Compatibility with a real `pypostal` install in the same process is not yet tested.
