"""Locate and download the libpostal model data."""

from __future__ import annotations

import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

# Senzing publishes the libpostal models (retrained parser, v1.2.0) here.
DEFAULT_BASE_URL = "https://public-read-libpostal-data.s3.amazonaws.com"

# Archives that make up a data directory, relative to the base URL. The
# language classifier is only needed for libpostal's address expansion, which
# this package does not use, but the other two are required to parse.
ARCHIVES = ("v1.1.0/libpostal_data.tar.gz", "v1.2.0/parser.tar.gz")

SYSTEM_DIR = Path("/usr/local/share/libpostal")
ENV_VAR = "LIBPOSTAL_DATA_DIR"


def is_complete(path: Path) -> bool:
    """
    Check whether a directory holds the data needed to parse addresses.

    Parameters
    ----------
    path : Path
        Candidate data directory.

    Returns
    -------
    bool
        True when the parser model and the shared dictionaries are present.
    """
    return all((path / name).is_dir() for name in ("address_parser", "numex"))


def user_dir() -> Path:
    """
    Per-user directory that ``download_data`` writes to by default.

    Returns
    -------
    Path
        ``$XDG_DATA_HOME/polars-libpostal`` or ``~/.local/share/polars-libpostal``.
    """
    root = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(root) / "polars-libpostal"


def data_dir() -> Path:
    """
    Find the libpostal data directory.

    The first of these that exists wins: ``$LIBPOSTAL_DATA_DIR``, an existing
    system install at ``/usr/local/share/libpostal``, then the per-user
    directory ``download_data`` writes to.

    Returns
    -------
    Path
        A directory that may not hold data yet (when nothing was found, the
        per-user directory is returned so ``download_data`` knows where to go).
    """
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env)
    if is_complete(SYSTEM_DIR):
        return SYSTEM_DIR
    return user_dir()


def _extract(archive: Path, dest: Path) -> None:
    with tarfile.open(archive) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:  # pragma: no cover - Python without the extraction filters
            tar.extractall(dest)  # noqa: S202


def download_data(
    dest: str | os.PathLike[str] | None = None,
    *,
    force: bool = False,
    base_url: str = DEFAULT_BASE_URL,
) -> Path:
    """
    Download the libpostal model data (about 3 GB on disk).

    Parameters
    ----------
    dest : str | os.PathLike[str] | None
        Directory to install into. Defaults to ``data_dir()``.
    force : bool
        Download again even when the directory already holds data.
    base_url : str
        Where the archives are served from.

    Returns
    -------
    Path
        The data directory, ready to use.
    """
    target = Path(dest) if dest is not None else data_dir()
    if is_complete(target) and not force:
        print(f"libpostal data already in {target}", file=sys.stderr)
        return target

    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target) as tmp:
        for name in ARCHIVES:
            url = f"{base_url.rstrip('/')}/{name}"
            archive = Path(tmp) / Path(name).name
            print(f"downloading {url}", file=sys.stderr)
            with urllib.request.urlopen(url) as src, archive.open("wb") as out:  # noqa: S310
                shutil.copyfileobj(src, out, length=1 << 20)
            _extract(archive, target)
            archive.unlink()
    if not is_complete(target):
        msg = f"downloaded archives did not produce libpostal data in {target}"
        raise RuntimeError(msg)
    return target
