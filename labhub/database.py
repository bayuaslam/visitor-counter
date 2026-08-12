import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_FILE = BASE_DIR / "labhub.db"


def _database_url() -> str:
    configured = os.getenv("DATABASE_URL", "").strip()
    if not configured:
        return f"sqlite:///{DATABASE_FILE.as_posix()}"
    if configured.startswith("postgres://"):
        return configured.replace("postgres://", "postgresql+psycopg://", 1)
    if configured.startswith("postgresql://"):
        return configured.replace("postgresql://", "postgresql+psycopg://", 1)
    return configured


DATABASE_URL = _database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite:")

connect_args = {"check_same_thread": False, "timeout": 5} if IS_SQLITE else {}
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


class Base(DeclarativeBase):
    pass


if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_database():
    from labhub import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_session():
    with SessionLocal() as session:
        yield session
