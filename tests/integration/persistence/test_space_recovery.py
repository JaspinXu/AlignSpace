"""Space persistence recovery and concurrent-write behaviour.

The space draft must survive an application restart with the exact same plan
and hash, and a concurrent write based on a stale version must be rejected
rather than merged silently.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from alignspace.domain.enums import Role
from alignspace.domain.models import ProjectState
from alignspace.domain.policies import StaleStateError
from alignspace.domain.space import (
    SpacePlan,
    SpaceVersion,
    build_rectangular_room,
    calculate_space_content_hash,
)
from alignspace.persistence.database import create_engine_and_session
from alignspace.persistence.repository import ProjectRepository


def _version(version: int, *, name: str = "客厅", previous: int | None = None) -> SpaceVersion:
    plan = SpacePlan(rooms=[build_rectangular_room(room_id="room-1", name=name, width=4000, depth=5000)])
    payload = plan.model_dump(mode="json")
    return SpaceVersion(
        version=version,
        content_hash=calculate_space_content_hash(payload),
        payload=payload,
        created_by="homeowner-1",
        created_role=Role.HOMEOWNER,
        source="rectangular_dimensions",
        previous_version=previous,
    )


def test_space_plan_survives_an_application_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'space-restart.db'}"
    engine, session_factory = create_engine_and_session(url)
    with session_factory() as session:
        ProjectRepository(session).create(ProjectState(project_id="project-restart"))
        session.commit()
    with session_factory() as session:
        repository = ProjectRepository(session)
        state = repository.load("project-restart")
        updated = state.model_copy(
            update={"state_version": 1, "space_versions": [_version(1)]}
        )
        repository.save(updated, expected_version=0)
        session.commit()
    engine.dispose()

    # Re-open the same database as a fresh process would.
    engine, session_factory = create_engine_and_session(url)
    try:
        with session_factory() as session:
            reloaded = ProjectRepository(session).load("project-restart")
        assert [item.version for item in reloaded.space_versions] == [1]
        restored = reloaded.space_versions[0]
        assert restored.payload == _version(1).payload
        assert restored.content_hash == _version(1).content_hash
    finally:
        engine.dispose()


def test_concurrent_space_write_with_a_stale_version_is_rejected(tmp_path):
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'space-race.db'}")
    try:
        with session_factory() as session:
            ProjectRepository(session).create(ProjectState(project_id="project-race"))
            session.commit()

        with session_factory() as session_one, session_factory() as session_two:
            repository_one = ProjectRepository(session_one)
            repository_two = ProjectRepository(session_two)
            first = repository_one.load("project-race")
            second = repository_two.load("project-race")

            repository_one.save(
                first.model_copy(update={"state_version": 1, "space_versions": [_version(1)]}),
                expected_version=0,
            )
            session_one.commit()

            with pytest.raises((StaleStateError, IntegrityError)):
                repository_two.save(
                    second.model_copy(
                        update={"state_version": 1, "space_versions": [_version(1, name="会客厅")]}
                    ),
                    expected_version=0,
                )
                session_two.commit()
    finally:
        engine.dispose()
