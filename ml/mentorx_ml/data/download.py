"""Download a dataset file from its official source and verify its checksum.

Datasets are never committed to git (licence terms forbid redistribution), so each
team member downloads them with this code. The SHA-256 check guarantees everyone
trains on byte-identical data.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RemoteFile:
    url: str
    filename: str
    sha256: str


class ChecksumError(RuntimeError):
    pass


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def fetch(remote: RemoteFile, dest_dir: Path, force: bool = False) -> Path:
    """Download `remote` into dest_dir (skipping if a verified copy exists)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / remote.filename

    if target.exists() and not force:
        if sha256_of(target) == remote.sha256:
            logger.info("%s already present and verified", target)
            return target
        logger.warning("%s exists but checksum differs; re-downloading", target)

    tmp = target.with_suffix(target.suffix + ".part")
    logger.info("Downloading %s", remote.url)
    req = urllib.request.Request(remote.url, headers={"User-Agent": "mentorx-ml/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as out:
        shutil.copyfileobj(resp, out)

    actual = sha256_of(tmp)
    if actual != remote.sha256:
        tmp.unlink(missing_ok=True)
        raise ChecksumError(
            f"{remote.filename}: expected sha256 {remote.sha256}, got {actual}. "
            "The source file may have changed; do not train on it until this is understood."
        )
    tmp.replace(target)
    logger.info("Saved %s (sha256 verified)", target)
    return target
