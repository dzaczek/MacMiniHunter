from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Session:
    """Create a new database session."""
    return SessionLocal()
