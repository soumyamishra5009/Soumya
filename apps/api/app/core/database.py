"""Database engine, session and FastAPI dependency."""

import logging

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.core.config import settings
from app.models.base import Base

logger = logging.getLogger(__name__)

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
    """Create all tables. Useful for local dev without Alembic.

    Then idempotently add any columns introduced after a dev database was
    first created (``create_all`` only creates missing tables, never missing
    columns). Production should use Alembic migrations instead.
    """
    from app import models  # noqa: F401 - ensure models are registered
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


# (table, column, ddl) — additive changes safe to apply to an existing dev DB
_ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("meetings", "archived", "BOOLEAN NOT NULL DEFAULT FALSE"),
)


def _ensure_columns() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table, column, ddl in _ADDITIVE_COLUMNS:
        if table not in tables:
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        if column in existing:
            continue
        with engine.begin() as conn:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        logger.info("Applied additive column migration: %s.%s", table, column)
