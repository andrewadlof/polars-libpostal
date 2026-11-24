# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `parse_address`, a Polars expression that parses addresses with libpostal on Polars' thread pool and returns a struct of
  one field per libpostal label (`house_number`, `road`, `unit`, `city`, `state`, `postcode`, ...). The `labels` argument
  limits and orders the fields; `LABELS` lists them all.
- A patch that makes libpostal's address parser thread-safe by giving each thread its own scratch space, a build script
  for it, and a C stress test.
- `download_data` and `data_dir`, with the `python -m polars_libpostal download-data` command, to fetch the libpostal
  model data (about 3 GB).
- A manylinux_2_28 x86_64 wheel that bundles the patched libpostal, built by the release workflow.
