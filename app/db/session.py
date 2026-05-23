from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import MissingConfigurationError


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


class Base(DeclarativeBase):
    pass


def build_engine():
    settings = get_settings()
    if not settings.database_url:
        raise MissingConfigurationError("DATABASE_URL")
    database_url = normalize_database_url(settings.database_url)
    return create_engine(database_url, pool_pre_ping=True, pool_size=2, max_overflow=2)


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
