"""Command line: ``python -m polars_libpostal download-data``."""

from __future__ import annotations

import argparse

from polars_libpostal._data import DEFAULT_BASE_URL, data_dir, download_data


def main(argv: list[str] | None = None) -> int:
    """
    Run the command line interface.

    Parameters
    ----------
    argv : list[str] | None
        Arguments, without the program name. Defaults to ``sys.argv``.

    Returns
    -------
    int
        Process exit code.
    """
    parser = argparse.ArgumentParser(prog="python -m polars_libpostal")
    commands = parser.add_subparsers(dest="command", required=True)

    download = commands.add_parser(
        "download-data", help="download the libpostal model data (about 3 GB)"
    )
    download.add_argument("--dest", help="directory to install into")
    download.add_argument("--force", action="store_true", help="download again")
    download.add_argument("--base-url", default=DEFAULT_BASE_URL)

    commands.add_parser("data-dir", help="print the directory that will be used")

    args = parser.parse_args(argv)
    if args.command == "data-dir":
        print(data_dir())
    else:
        print(download_data(args.dest, force=args.force, base_url=args.base_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
