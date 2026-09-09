from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from alignspace.persistence.tables import Base


def create_engine_and_session(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})
    if url.startswith("sqlite"):
        event.listen(
            engine,
            "connect",
            lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
        )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
