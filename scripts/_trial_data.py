"""Helpers for the offline (stopped-service) local backup and restore tools.

A backup is a directory containing ``database.sqlite3``, ``checkpoints.sqlite3``,
``assets/`` and ``manifest.json``. The manifest lists relative paths, sizes and
SHA-256 hashes and never records secrets or source-machine absolute paths.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
DATABASE_NAME = "database.sqlite3"
CHECKPOINT_NAME = "checkpoints.sqlite3"
ASSETS_NAME = "assets"


class TrialDataError(Exception):
    """Raised when a backup or restore request is unsafe or invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_absolute(path: Path) -> None:
    if not path.is_absolute():
        raise TrialDataError(f"path must be absolute: {path}")


def require_not_symlink(path: Path) -> None:
    if path.is_symlink():
        raise TrialDataError(f"symlinks are not supported: {path}")


def require_existing_file(path: Path) -> None:
    require_absolute(path)
    require_not_symlink(path)
    if not path.is_file():
        raise TrialDataError(f"missing file: {path}")


def require_existing_dir(path: Path) -> None:
    require_absolute(path)
    require_not_symlink(path)
    if not path.is_dir():
        raise TrialDataError(f"missing directory: {path}")


def is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def reject_broad_target(target: Path) -> None:
    if target.parent == target:
        raise TrialDataError("refusing to use a filesystem root as a target")
    if target == Path.home():
        raise TrialDataError("refusing to use the home directory as a target")


def sqlite_backup(source: Path, destination: Path) -> None:
    """Copy a SQLite database with the backup API so committed WAL data is included."""
    connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    target = sqlite3.connect(destination)
    try:
        connection.backup(target)
    finally:
        target.close()
        connection.close()


def sqlite_integrity_ok(path: Path) -> bool:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        return bool(row) and row[0] == "ok"
    finally:
        connection.close()


def migration_version(path: Path) -> int:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        connection.close()


def copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for root, directories, files in os.walk(source):
        root_path = Path(root)
        if root_path.is_symlink():
            raise TrialDataError(f"symlinks are not supported: {root_path}")
        relative = root_path.relative_to(source)
        (destination / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            item = root_path / name
            require_not_symlink(item)
            shutil.copy2(item, destination / relative / name)


def build_manifest(staging: Path, migration: int) -> dict[str, object]:
    files = []
    for path in sorted(staging.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(staging).as_posix()
        files.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "formatVersion": FORMAT_VERSION,
        "createdAt": datetime.now(UTC).isoformat(),
        "migrationVersion": migration,
        "files": files,
    }


def write_manifest(staging: Path, migration: int) -> None:
    (staging / MANIFEST_NAME).write_text(
        json.dumps(build_manifest(staging, migration), ensure_ascii=False, indent=2)
    )


def read_manifest(backup: Path) -> dict[str, object]:
    manifest_path = backup / MANIFEST_NAME
    require_existing_file(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        raise TrialDataError("manifest is not valid JSON") from exc
    if manifest.get("formatVersion") != FORMAT_VERSION:
        raise TrialDataError("unsupported backup format version")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise TrialDataError("manifest files must be a list")
    return manifest


def verify_manifest(backup: Path, manifest: dict[str, object]) -> None:
    files = manifest["files"]
    assert isinstance(files, list)
    for entry in files:
        if not isinstance(entry, dict):
            raise TrialDataError("manifest entries must be objects")
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative:
            raise TrialDataError("manifest path must be a non-empty string")
        item = Path(relative)
        if item.is_absolute() or ".." in item.parts:
            raise TrialDataError(f"manifest path escapes the backup: {relative}")
        target = backup / item
        require_existing_file(target)
        if target.stat().st_size != entry.get("size"):
            raise TrialDataError(f"size mismatch: {relative}")
        if sha256_file(target) != entry.get("sha256"):
            raise TrialDataError(f"hash mismatch: {relative}")
    for name in (DATABASE_NAME, CHECKPOINT_NAME):
        require_existing_file(backup / name)
    if not (backup / ASSETS_NAME).is_dir():
        raise TrialDataError("backup is missing the assets directory")


def backup(
    database: Path,
    checkpoint: Path,
    assets: Path,
    output: Path,
    *,
    confirmed_stopped: bool,
) -> Path:
    if not confirmed_stopped:
        raise TrialDataError("refusing to back up without --confirm-stopped")
    for path in (database, checkpoint, assets, output):
        require_absolute(path)
    require_existing_file(database)
    require_existing_file(checkpoint)
    require_existing_dir(assets)
    require_not_symlink(output)
    reject_broad_target(output)
    if output.exists():
        raise TrialDataError(f"output already exists: {output}")
    if not output.parent.is_dir():
        raise TrialDataError("output parent must exist")
    for source in (database, checkpoint, assets):
        if is_within(output, source) or is_within(source, output):
            raise TrialDataError("output must not overlap the source data")

    staging = output.parent / f"{output.name}.incomplete-{os.getpid()}"
    if staging.exists():
        raise TrialDataError(f"staging directory already exists: {staging}")
    staging.mkdir()
    try:
        sqlite_backup(database, staging / DATABASE_NAME)
        sqlite_backup(checkpoint, staging / CHECKPOINT_NAME)
        copy_tree(assets, staging / ASSETS_NAME)
        if not sqlite_integrity_ok(staging / DATABASE_NAME):
            raise TrialDataError("copied business database failed its integrity check")
        if not sqlite_integrity_ok(staging / CHECKPOINT_NAME):
            raise TrialDataError("copied checkpoint database failed its integrity check")
        write_manifest(staging, migration_version(staging / DATABASE_NAME))
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return output


def restore(backup_dir: Path, destination: Path) -> Path:
    for path in (backup_dir, destination):
        require_absolute(path)
    require_existing_dir(backup_dir)
    require_not_symlink(destination)
    reject_broad_target(destination)
    if destination.exists():
        raise TrialDataError(f"destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise TrialDataError("destination parent must exist")
    manifest = read_manifest(backup_dir)
    verify_manifest(backup_dir, manifest)
    for name in (DATABASE_NAME, CHECKPOINT_NAME):
        if not sqlite_integrity_ok(backup_dir / name):
            raise TrialDataError(f"{name} failed its integrity check")
    destination.mkdir()
    try:
        shutil.copy2(backup_dir / DATABASE_NAME, destination / DATABASE_NAME)
        shutil.copy2(backup_dir / CHECKPOINT_NAME, destination / CHECKPOINT_NAME)
        copy_tree(backup_dir / ASSETS_NAME, destination / ASSETS_NAME)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return destination
