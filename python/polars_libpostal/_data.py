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

# Archives that make up a data directory, relative to the base URL, and the
# folder each one creates. The dictionaries are needed for everything, the
# parser model for parsing, and the language classifier for expanding addresses
# without naming their languages.
ARCHIVES = {
    "v1.1.0/libpostal_data.tar.gz": "address_expansions",
    "v1.2.0/parser.tar.gz": "address_parser",
    "v1.1.0/language_classifier.tar.gz": "language_classifier",
}

SYSTEM_DIR = Path("/usr/local/share/libpostal")
ENV_VAR = "LIBPOSTAL_DATA_DIR"


def is_complete(path: Path) -> bool:
    """
    Check whether a directory holds all of libpostal's data.

    Parameters
    ----------
    path : Path
        Candidate data directory.

    Returns
    -------
    bool
        True when the dictionaries, the parser model and the language
        classifier are all present.
    """
    return all((path / folder).is_dir() for folder in ARCHIVES.values())


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

    Only the archives whose folder is missing are fetched, so running it on an
    older install adds what is new (such as the language classifier) without
    downloading the rest again.

    Parameters
    ----------
    dest : str | os.PathLike[str] | None
        Directory to install into. Defaults to ``data_dir()``.
    force : bool
        Download every archive again, even when its folder is present.
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
    missing = [
        name
        for name, folder in ARCHIVES.items()
        if force or not (target / folder).is_dir()
    ]
    with tempfile.TemporaryDirectory(dir=target) as tmp:
        for name in missing:
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
