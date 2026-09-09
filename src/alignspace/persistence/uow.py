from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from alignspace.persistence.repository import IdempotencyRepository, ProjectRepository


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._committed = False

    def __enter__(self) -> Self:
        self.session = self._session_factory()
        self.projects = ProjectRepository(self.session)
        self.idempotency = IdempotencyRepository(self.session)
        self._committed = False
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if exc_type is not None or not self._committed:
            self.session.rollback()
        self.session.close()

    def commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self._committed = True
