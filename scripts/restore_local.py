#!/usr/bin/env python
"""Restore an offline backup into a brand new directory without touching the
running data. Prints the three paths to use for the environment variables."""

import argparse
import sys
from pathlib import Path

from _trial_data import TrialDataError, restore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore an AlignSpace offline backup.")
    parser.add_argument("--backup", required=True, help="absolute path to a backup directory")
    parser.add_argument("--destination", required=True, help="absolute new directory to restore into")
    args = parser.parse_args(argv)
    try:
        destination = restore(Path(args.backup), Path(args.destination))
    except TrialDataError as exc:
        print(f"restore failed: {exc}", file=sys.stderr)
        return 1
    print(f"restored database: {destination / 'database.sqlite3'}")
    print(f"restored checkpoint: {destination / 'checkpoints.sqlite3'}")
    print(f"restored assets: {destination / 'assets'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
