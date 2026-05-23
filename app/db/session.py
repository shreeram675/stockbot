from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import MissingConfigurationError


class Base(DeclarativeBase):
    pass


def build_engine():
    settings = get_settings()
    if not settings.database_url:
        raise MissingConfigurationError("DATABASE_URL")
    return create_engine(settings.database_url, pool_pre_ping=True, pool_size=2, max_overflow=2)


engine = None
SessionLocal: sessionmaker[Session] | None = None


def init_db() -> None:
    global engine, SessionLocal
    if engine is None:
        engine = build_engine()
        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_session() -> Generator[Session, None, None]:
    init_db()
    assert SessionLocal is not None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

