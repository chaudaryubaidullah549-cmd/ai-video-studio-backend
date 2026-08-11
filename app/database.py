"""
Database setup.

Design choice: projects are stored as a single JSON document per row
(`projects.data`) rather than fully normalized tables. The Project /
Scene / Character models are naturally document-shaped (nested lists that
are always read/written together), and this keeps the repository layer
trivial while still going through SQLAlchemy - so swapping SQLite for
Postgres is a one-line DATABASE_URL change (see app/config.py). If the
project later needs to query *inside* scenes at the SQL level (e.g. "find
all scenes with status=failed across all projects"), promote `scenes` to
its own table at that point; the repository interface below would not
need to change from the service layer's point of view.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


class ProjectRecord(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True)
    status = Column(String(50), nullable=False, index=True)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
