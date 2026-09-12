from sqlalchemy import text

from alignspace.auth.models import MigrationRow
from alignspace.persistence.tables import Base


def migrate(engine):
    """Additive migrations. Re-running is safe.

    Version 1 adds auth tables and one member per role. Version 2 adds the
    image soft-delete column. Existing development databases are never assigned
    to real users by email/ID heuristics.
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
    assert MigrationRow.__tablename__ in Base.metadata.tables
