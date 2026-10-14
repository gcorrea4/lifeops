from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.settings import settings

def _connect_args() -> dict:
    """TLS options for managed MySQL; empty (plain connection) when DB_SSL_CA is not set."""
    return {"ssl": {"ca": settings.DB_SSL_CA}} if settings.DB_SSL_CA else {}


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # reconnect if a stale connection is returned from pool
    connect_args=_connect_args(),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session and ensures it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
