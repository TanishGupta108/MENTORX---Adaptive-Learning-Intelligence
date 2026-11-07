import hashlib

import pytest

from mentorx_ml.data import download
from mentorx_ml.data.download import ChecksumError, RemoteFile, fetch


def _remote(content: bytes, tmp_path, sha=None):
    src = tmp_path / "src.csv"
    src.write_bytes(content)
    return RemoteFile(
        url=src.as_uri(),
        filename="data.csv",
        sha256=sha or hashlib.sha256(content).hexdigest(),
    )


def test_fetch_downloads_and_verifies(tmp_path):
    remote = _remote(b"a,b\n1,2\n", tmp_path)
    path = fetch(remote, tmp_path / "out")
    assert path.read_bytes() == b"a,b\n1,2\n"


def test_fetch_rejects_wrong_checksum_and_leaves_no_file(tmp_path):
    remote = _remote(b"tampered", tmp_path, sha="0" * 64)
    with pytest.raises(ChecksumError):
        fetch(remote, tmp_path / "out")
    assert not (tmp_path / "out" / "data.csv").exists()
    assert not (tmp_path / "out" / "data.csv.part").exists()


def test_fetch_skips_download_when_verified_copy_exists(tmp_path, monkeypatch):
    remote = _remote(b"x", tmp_path)
    fetch(remote, tmp_path / "out")

    def fail(*args, **kwargs):
        raise AssertionError("should not download again")

    monkeypatch.setattr(download.urllib.request, "urlopen", fail)
    fetch(remote, tmp_path / "out")
