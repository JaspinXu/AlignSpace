from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from alignspace.persistence.tables import Base


def create_engine_and_session(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
