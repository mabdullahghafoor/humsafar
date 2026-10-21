"""
SQLAlchemy engine, session factory, and declarative base.

Task 0.3: working DB connection.
Task 1.1: added a MetaData naming convention so every constraint and index gets
a deterministic name. Alembic (Task 1.2) needs this to generate stable,
reviewable migrations and to drop/alter constraints reliably later.
"""

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))


def get_db():
    """
    FastAPI dependency — yields a DB session per request, closes it after.
    Usage in routers: `db: Session = Depends(get_db)`
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
