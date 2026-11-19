"""The model data downloader, against a local server and tiny archives."""

from __future__ import annotations

import functools
import http.server
import io
import tarfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from polars_libpostal import _data


def _archive(path: Path, members: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as tar:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))


@pytest.fixture()
def server(tmp_path: Path) -> Iterator[str]:
    root = tmp_path / "www"
    _archive(root / "v1.1.0" / "libpostal_data.tar.gz", {"numex/en.dat": b"x"})
    _archive(root / "v1.2.0" / "parser.tar.gz", {"address_parser/model.dat": b"y"})
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(root)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_download_extracts_both_archives(server: str, tmp_path: Path) -> None:
    dest = tmp_path / "data"
    assert _data.download_data(dest, base_url=server) == dest
    assert (dest / "numex" / "en.dat").read_bytes() == b"x"
    assert (dest / "address_parser" / "model.dat").read_bytes() == b"y"
    assert _data.is_complete(dest)


def test_second_download_is_skipped_unless_forced(server: str, tmp_path: Path) -> None:
    dest = tmp_path / "data"
    _data.download_data(dest, base_url=server)
    # A dead server proves nothing was fetched
    assert _data.download_data(dest, base_url="http://127.0.0.1:1") == dest
    with pytest.raises(OSError):  # noqa: PT011
        _data.download_data(dest, force=True, base_url="http://127.0.0.1:1")


def test_data_dir_prefers_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(_data.ENV_VAR, str(tmp_path))
    assert _data.data_dir() == tmp_path


def test_data_dir_falls_back_to_the_user_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(_data.ENV_VAR, raising=False)
    monkeypatch.setattr(_data, "SYSTEM_DIR", tmp_path / "no-system-install")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert _data.data_dir() == tmp_path / "polars-libpostal"
