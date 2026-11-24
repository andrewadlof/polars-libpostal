# Releasing

Releases are cut by CI and published to PyPI with [Trusted Publishing](https://docs.pypi.org/trusted-publishers/), so there
is no API token to store. Published versions are immutable.

## One-time setup

1. On PyPI, add a trusted publisher. For a project that does not exist yet, use *Your account* → *Publishing* →
   *Add a new pending publisher*:
    - Project name: `polars-libpostal`
    - Owner / repository: `andrewadlof` / `polars-libpostal`
    - Workflow: `release.yml`
    - Environment: `pypi`
2. On GitHub, create an environment named `pypi` (*Settings* → *Environments*). Optionally require your approval.
3. On GitHub, set *Settings* → *Pages* → *Source* to *GitHub Actions* so the docs deploy.

## Each release

1. Move the `[Unreleased]` notes in `CHANGELOG.md` under the new version and date.
2. `uv version --bump patch` (or `minor` / `major`) and commit. `uv run just bump patch` does the same.
3. From `main`, `uv run just tag`. This pushes `v<version>`, which runs the release workflow: it builds the manylinux wheel
   with the patched libpostal bundled, then publishes it.

To rehearse a release without using a version number, run the *Release* workflow manually (*Actions* → *Release* →
*Run workflow*). It builds and uploads the wheel as an artifact but does not publish.
