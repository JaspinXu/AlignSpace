import pytest

from alignspace.domain.models import ProjectState
from alignspace.domain.policies import StaleStateError
from alignspace.persistence.database import create_engine_and_session
from alignspace.persistence.uow import SqlAlchemyUnitOfWork


def test_repository_rejects_stale_version(tmp_path) -> None:
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'test.db'}")
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.projects.create(ProjectState(project_id="project-1"))
        uow.commit()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        current = uow.projects.load("project-1")
        uow.projects.save(current.model_copy(update={"state_version": 1}), expected_version=0)
        uow.commit()
    with (
        pytest.raises(StaleStateError, match="project project-1 changed concurrently"),
        SqlAlchemyUnitOfWork(session_factory) as uow,
    ):
        uow.projects.save(
            current.model_copy(update={"state_version": 1}),
            expected_version=0,
        )
        uow.commit()
    engine.dispose()


def test_repository_requires_each_save_to_increment_the_expected_version(tmp_path) -> None:
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'test.db'}")
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.projects.create(ProjectState(project_id="project-1"))
        uow.commit()

    with (
        pytest.raises(ValueError, match="state_version must increment expected_version"),
        SqlAlchemyUnitOfWork(session_factory) as uow,
    ):
        uow.projects.save(ProjectState(project_id="project-1"), expected_version=0)
        uow.commit()
    engine.dispose()


def test_project_creation_requires_version_zero(tmp_path) -> None:
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'test.db'}")

    with (
        pytest.raises(ValueError, match="new projects must start at state_version 0"),
        SqlAlchemyUnitOfWork(session_factory) as uow,
    ):
        uow.projects.create(ProjectState(project_id="project-1", state_version=1))
        uow.commit()
    engine.dispose()
