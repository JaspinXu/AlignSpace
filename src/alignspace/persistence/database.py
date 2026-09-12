from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from alignspace.persistence.migrations import migrate


@contextmanager
def read_transaction(session_factory: sessionmaker):
    """Hold one read transaction so several SELECTs share a single snapshot.

    pysqlite runs reads in autocommit unless a transaction is opened explicitly,
    so separate queries would otherwise observe different committed versions.
    """
    with session_factory() as session:
        session.execute(text("BEGIN"))
        try:
            yield session
        finally:
            session.rollback()


def create_engine_and_session(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})
    if url.startswith("sqlite"):
        event.listen(
            engine,
            "connect",
            lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
        )
    migrate(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
