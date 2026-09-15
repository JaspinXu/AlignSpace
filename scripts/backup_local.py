#!/usr/bin/env python
"""Offline local backup: stop all writers, then copy the business database, the
checkpoint database and the asset directory into one consistent package."""

import argparse
import sys
from pathlib import Path

from _trial_data import TrialDataError, backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline AlignSpace backup. Stop every writer before running."
    )
    parser.add_argument("--database", required=True, help="absolute path to the business SQLite file")
    parser.add_argument("--checkpoint", required=True, help="absolute path to the checkpoint SQLite file")
    parser.add_argument("--assets", required=True, help="absolute path to the asset directory")
    parser.add_argument("--output", required=True, help="absolute new directory for the backup")
    parser.add_argument(
        "--confirm-stopped",
        action="store_true",
        help="operator confirmation that every writer has stopped",
    )
    args = parser.parse_args(argv)
    try:
        output = backup(
            Path(args.database),
            Path(args.checkpoint),
            Path(args.assets),
            Path(args.output),
            confirmed_stopped=args.confirm_stopped,
        )
    except TrialDataError as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"backup written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
