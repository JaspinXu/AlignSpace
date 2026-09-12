import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from alignspace.persistence.database import create_engine_and_session
from alignspace.persistence.tables import ProjectMemberRow, ProjectRow


def test_migrate_is_idempotent_and_creates_auth_tables(tmp_path):
    url = f"sqlite:///{tmp_path / 'repeat.db'}"
    first_engine, _ = create_engine_and_session(url)
    first_engine.dispose()

    engine, _ = create_engine_and_session(url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {
            "users",
            "auth_sessions",
            "refresh_tokens",
            "rate_limits",
            "project_join_codes",
            "schema_migrations",
            "project_members",
        } <= tables
        indexes = {index["name"] for index in inspector.get_indexes("project_members")}
        assert "project_member_role" in indexes
    finally:
        engine.dispose()


def test_unique_role_index_blocks_a_second_member_in_the_same_role(tmp_path):
    engine, session_factory = create_engine_and_session(
        f"sqlite:///{tmp_path / 'roles.db'}"
    )
    try:
        with session_factory() as session:
            session.add(
                ProjectRow(
                    id="p1",
                    state_version=0,
                    status="draft",
                    completeness=0,
                    consent=False,
                )
            )
            session.flush()
            session.add(
                ProjectMemberRow(
                    project_id="p1", member_id="homeowner-1",
                    role="homeowner", payload={},
                )
            )
            session.commit()
            session.add(
                ProjectMemberRow(
                    project_id="p1", member_id="homeowner-2",
                    role="homeowner", payload={},
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()
