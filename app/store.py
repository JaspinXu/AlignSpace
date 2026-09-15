from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable

def _hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProjectNotFoundError(KeyError):
    pass


class StaleStateError(RuntimeError):
    pass


class ProjectStore:
    def __init__(self, database_path: str | Path | None = None) -> None:
        configured = database_path or os.getenv("ALIGNSPACE_DB_PATH", "data/alignspace.db")
        self.database_path = Path(configured)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    state_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    before_hash TEXT,
                    after_hash TEXT NOT NULL,
                    state_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE INDEX IF NOT EXISTS audit_project_sequence
                    ON audit_events(project_id, sequence DESC);
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT,
                    created REAL, status TEXT, metrics_json TEXT);
                CREATE INDEX IF NOT EXISTS analysis_runs_project
                    ON analysis_runs(project_id, created DESC);
                CREATE INDEX IF NOT EXISTS analysis_runs_created
                    ON analysis_runs(created DESC);
                CREATE INDEX IF NOT EXISTS projects_updated
                    ON projects(updated_at DESC);
                """
            )

    def create(self, state: dict[str, Any], actor: str = "system") -> dict[str, Any]:
        payload = json.dumps(state, separators=(",", ":"))
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO projects(id, state_json, state_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (state["id"], payload, state["stateVersion"], state["createdAt"], state["updatedAt"]),
            )
            connection.execute(
                """
                INSERT INTO audit_events(project_id, action, actor, before_hash, after_hash, state_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (state["id"], "project_created", actor, None, _hash(state), state["stateVersion"], state["updatedAt"]),
            )
        return state

    def get(self, project_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError(project_id)
        return json.loads(row["state_json"])

    def list(self, project_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """Pass project_ids to avoid deserialising projects the caller cannot see."""
        if project_ids is None:
            query, parameters = "SELECT state_json FROM projects ORDER BY updated_at DESC", ()
        else:
            parameters = tuple(dict.fromkeys(project_ids))
            if not parameters:
                return []
            placeholders = ",".join("?" * len(parameters))
            query = f"SELECT state_json FROM projects WHERE id IN ({placeholders}) ORDER BY updated_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [json.loads(row["state_json"]) for row in rows]

    def mutate(
        self,
        project_id: str,
        action: str,
        actor: str,
        mutation: Callable[[dict[str, Any]], dict[str, Any]],
        expected_state_version: int | None = None,
    ) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state_json, state_version FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if row is None:
                raise ProjectNotFoundError(project_id)
            if expected_state_version is not None and row["state_version"] != expected_state_version:
                raise StaleStateError(
                    f"Expected state version {expected_state_version}, found {row['state_version']}"
                )
            before = json.loads(row["state_json"])
            after = mutation(json.loads(row["state_json"]))
            connection.execute(
                """
                UPDATE projects
                SET state_json = ?, state_version = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    json.dumps(after, separators=(",", ":")),
                    after["stateVersion"],
                    after["updatedAt"],
                    project_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO audit_events(project_id, action, actor, before_hash, after_hash, state_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    action,
                    actor,
                    _hash(before),
                    _hash(after),
                    after["stateVersion"],
                    after["updatedAt"],
                ),
            )
            connection.commit()
        return after

    def audit(self, project_id: str, limit: int = 50) -> list[dict[str, Any]]:
        self.get(project_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sequence, action, actor, before_hash, after_hash, state_version, created_at
                FROM audit_events
                WHERE project_id = ?
                ORDER BY sequence DESC
                LIMIT ?
                """,
                (project_id, min(max(limit, 1), 200)),
            ).fetchall()
        return [dict(row) for row in rows]

    def reserve_analysis(self, project_id: str) -> int:
        """Persist reservations before network I/O; failures also consume the cap."""
        with self._lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM analysis_runs WHERE project_id=? AND created>?', (project_id, time.time()-10)).fetchone():
                raise ValueError('Wait 10 seconds between analysis requests')
            per_project = db.execute('SELECT COUNT(*) FROM analysis_runs WHERE project_id=?', (project_id,)).fetchone()[0]
            daily = db.execute('SELECT COUNT(*) FROM analysis_runs WHERE created>?', (time.time()-86400,)).fetchone()[0]
            if per_project >= int(os.getenv('ALIGNSPACE_PROJECT_RUN_LIMIT','20')) or daily >= int(os.getenv('ALIGNSPACE_DAILY_RUN_LIMIT','100')):
                raise ValueError('Analysis request limit reached. Manual decisions remain available.')
            row = db.execute('INSERT INTO analysis_runs(project_id,created,status,metrics_json) VALUES (?,?,?,?)',
                             (project_id,time.time(),'reserved','{}'))
            return row.lastrowid

    def finish_analysis(self, run_id, status, metrics):
        with self._connect() as db:
            db.execute('UPDATE analysis_runs SET status=?,metrics_json=? WHERE id=?', (status,json.dumps(metrics),run_id))

    def analysis_runs(self, project_id):
        with self._connect() as db:
            rows = db.execute('SELECT id,created,status,metrics_json FROM analysis_runs WHERE project_id=? ORDER BY id DESC LIMIT 50', (project_id,)).fetchall()
        return [{'id':r['id'],'created':r['created'],'status':r['status'],**json.loads(r['metrics_json'])} for r in rows]
