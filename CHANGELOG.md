# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `expand_address`, which returns libpostal's normalized forms of each address as a `List(String)`, for matching and
  deduplication. `languages=` names the languages; without it libpostal's language classifier picks them.
- The language classifier (about 50 MB) is part of the model data. `download-data` now fetches only the archives that are
  missing, so running it again on an existing install adds just the classifier.
- An `expand` mode for the C stress test and the ThreadSanitizer script. Expansion is thread-safe without a patch: no
  races and no mismatches on 8 threads.

### Changed

- Each part of the model data loads on first use: the parser model only for parsing, and the language classifier only for
  expansion without `languages`.

## [0.3.0] - 2026-11-25

### Added

- `parse_address_list`, which returns libpostal's components as a `List(Struct({"label": String, "value": String}))` in
  address order, with repeated labels kept apart (#15).

### Changed

- The ThreadSanitizer stress run is killed after 15 minutes (`TSAN_TIMEOUT`), and the stock-libpostal control now has to
  report races rather than just fail.

### Fixed

- The "repeated addresses" example in the docs used an inner join, which dropped rows with a null address.

## [0.2.0] - 2026-11-24

### Added

- `scripts/tsan.sh` and a ThreadSanitizer workflow that run the stress test under ThreadSanitizer: the patched libpostal
  must report no data races, and stock libpostal, as a control, must report them.
- A manylinux_2_28 aarch64 wheel, built on GitHub's Arm runners alongside the x86_64 one in CI and the release workflow.

## [0.1.0] - 2026-11-24

First release.

### Added

- `parse_address`, a Polars expression that parses addresses with libpostal on Polars' thread pool and returns a struct of
  one field per libpostal label (`house_number`, `road`, `unit`, `city`, `state`, `postcode`, ...). The `labels` argument
  limits and orders the fields; `LABELS` lists them all.
- A patch that makes libpostal's address parser thread-safe by giving each thread its own scratch space, a build script
  for it, and a C stress test.
- `download_data` and `data_dir`, with the `python -m polars_libpostal download-data` command, to fetch the libpostal
  model data (about 3 GB).
- A manylinux_2_28 x86_64 wheel that bundles the patched libpostal, built by the release workflow.
- Contributor tooling: a pull request template, pre-commit hooks (`just precommit`, run with prek) for ruff, rustfmt,
  taplo and mdformat, and a `just test_cov` coverage recipe.
- Docs: an API reference generated from the docstrings, a zoomable Mermaid diagram viewer, MathJax equations, click-to-zoom
  images and GitHub-style alerts.

[Unreleased]: https://github.com/andrewadlof/polars-libpostal/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/andrewadlof/polars-libpostal/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/andrewadlof/polars-libpostal/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/andrewadlof/polars-libpostal/releases/tag/v0.1.0
