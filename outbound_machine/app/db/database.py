"""
Database connection, session factory, and table initialisation.
Supports both SQLite (local dev) and PostgreSQL (production).
"""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import settings
from app.db.models import Base

logger = logging.getLogger(__name__)

# Build engine — SQLite needs some pragmas for reasonable behaviour
engine = create_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    # SQLite specific: allow multi-threaded access
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

if "sqlite" in settings.database_url:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call multiple times."""
    logger.info("Initialising database at: %s", settings.database_url)
    Base.metadata.create_all(bind=engine)
    logger.info("Database ready.")


def get_session() -> Session:
    """Return a new session. Caller is responsible for closing it."""
    return SessionLocal()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for a database session with automatic commit/rollback."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
