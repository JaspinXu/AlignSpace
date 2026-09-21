from sqlalchemy import text

from alignspace.auth.models import MigrationRow
from alignspace.persistence.tables import Base


def migrate(engine):
    """Additive migrations. Re-running is safe.

    Version 1 adds auth tables and one member per role. Version 2 adds the
    image soft-delete column. Version 3 tombstones legacy fixture assets that
    cannot be read from content-addressed storage. Existing development
    databases are never assigned to real users by email/ID heuristics.
    """
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS project_member_role "
            "ON project_members(project_id, role)"
        ))
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(image_assets)"))
        }
        if "deleted_at" not in columns:
            connection.execute(text("ALTER TABLE image_assets ADD COLUMN deleted_at INTEGER"))
        connection.execute(
            text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:version)"),
            {"version": 1},
        )
        connection.execute(
            text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:version)"),
            {"version": 2},
        )
        connection.execute(
            text(
                "UPDATE image_assets SET deleted_at = 0 "
                "WHERE json_extract(payload, '$.storage_key') IS NULL "
                "AND deleted_at IS NULL"
            )
        )
        connection.execute(
            text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:version)"),
            {"version": 3},
        )
        project_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(projects)"))
        }
        if "brief_stale" not in project_columns:
            connection.execute(
                text("ALTER TABLE projects ADD COLUMN brief_stale INTEGER NOT NULL DEFAULT 0")
            )
        connection.execute(
            text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:version)"),
            {"version": 4},
        )
        idempotency_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(idempotency_records)"))
        }
        if "completed" not in idempotency_columns:
            # Existing rows were written by operations that completed atomically.
            connection.execute(
                text(
                    "ALTER TABLE idempotency_records "
                    "ADD COLUMN completed INTEGER NOT NULL DEFAULT 1"
                )
            )
        connection.execute(
            text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:version)"),
            {"version": 5},
        )
        # Version 6 adds the candidate preference analysis tables
        # (analysis_runs, design_entries, candidate_preferences). They are created
        # by create_all above; this marker records the schema level. Older projects
        # simply have no rows, so the existing brief-only flow keeps working and no
        # historical analysis is fabricated.
        connection.execute(
            text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:version)"),
            {"version": 6},
        )
        # Version 7 adds space_versions. Historical projects have no rows, so they
        # keep the original brief-only flow and no space approval is fabricated.
        connection.execute(
            text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:version)"),
            {"version": 7},
        )
    assert MigrationRow.__tablename__ in Base.metadata.tables
