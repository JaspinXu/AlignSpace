from sqlalchemy import text

from alignspace.auth.models import MigrationRow
from alignspace.persistence.tables import Base


def migrate(engine):
    """Version 1 is additive: create auth tables and enforce one member per role.

    Re-running is safe. Existing development databases are never assigned to
    real users by email/ID heuristics.
    """
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS project_member_role "
            "ON project_members(project_id, role)"
        ))
        connection.execute(
            text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:version)"),
            {"version": 1},
        )
    assert MigrationRow.__tablename__ in Base.metadata.tables
