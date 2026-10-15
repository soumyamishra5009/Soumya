"""Database engine, session and FastAPI dependency."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.core.config import settings
from app.models.base import Base

_connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    # Required for FastAPI's threadpool usage of SQLite connections.
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_connect_args,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Useful for local dev without Alembic."""
    from app import models  # noqa: F401 - ensure models are registered
    Base.metadata.create_all(bind=engine)
