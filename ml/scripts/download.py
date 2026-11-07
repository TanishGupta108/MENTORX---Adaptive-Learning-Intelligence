"""Download a public dataset from its official source and verify its checksum.

Usage (from ml/):  python scripts/download.py --dataset assist2009
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from mentorx_ml.data import assist2009
from mentorx_ml.data.download import fetch

ML_DIR = Path(__file__).resolve().parents[1]
DATASETS = {assist2009.NAME: assist2009.REMOTE}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", choices=sorted(DATASETS), required=True)
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    args = parser.parse_args()

    print(
        "Before using this data, read its terms in docs/datasets.md "
        "(no redistribution; cite the source)."
    )
    fetch(DATASETS[args.dataset], ML_DIR / "data" / "raw" / args.dataset, force=args.force)


if __name__ == "__main__":
    main()
