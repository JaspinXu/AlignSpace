import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from alignspace.persistence.database import create_engine_and_session
from alignspace.persistence.migrations import migrate
from alignspace.persistence.tables import ImageAssetRow, ProjectMemberRow, ProjectRow


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


def test_migration_adds_soft_delete_column_and_is_repeatable(tmp_path):
    url = f"sqlite:///{tmp_path / 'soft-delete.db'}"
    first_engine, _ = create_engine_and_session(url)
    first_engine.dispose()

    engine, _ = create_engine_and_session(url)
    try:
        columns = {
            row[1] for row in engine.connect().exec_driver_sql("PRAGMA table_info(image_assets)")
        }
        assert "deleted_at" in columns
        versions = {
            row[0]
            for row in engine.connect().exec_driver_sql(
                "SELECT version FROM schema_migrations"
            )
        }
        assert versions == {1, 2, 3, 4, 5, 6, 7, 8}
    finally:
        engine.dispose()


def test_migration_creates_candidate_preference_tables(tmp_path):
    engine, _ = create_engine_and_session(f"sqlite:///{tmp_path / 'candidates.db'}")
    try:
        tables = set(inspect(engine).get_table_names())
        assert {"analysis_runs", "design_entries", "candidate_preferences", "space_versions", "space_bindings", "space_approvals"} <= tables
    finally:
        engine.dispose()


def test_migration_tombstones_legacy_image_asset_payloads(tmp_path):
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'legacy.db'}")
    try:
        with session_factory() as session:
            session.add(
                ProjectRow(
                    id="legacy-project",
                    state_version=0,
                    status="draft",
                    completeness=0,
                    consent=False,
                )
            )
            session.flush()
            session.add(
                ImageAssetRow(
                    project_id="legacy-project",
                    id="legacy-asset",
                    payload={"fixtureId": "x", "mediaType": "image/jpeg", "sizeBytes": 1},
                    deleted_at=None,
                )
            )
            session.commit()

        migrate(engine)

        with session_factory() as session:
            asset = session.get(ImageAssetRow, ("legacy-project", "legacy-asset"))
            assert asset is not None
            assert asset.deleted_at is not None
        versions = {
            row[0]
            for row in engine.connect().exec_driver_sql(
                "SELECT version FROM schema_migrations"
            )
        }
        assert 3 in versions
    finally:
        engine.dispose()
