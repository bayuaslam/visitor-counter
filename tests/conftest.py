import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_DB = Path(__file__).with_name("test_labhub.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["LABHUB_ENV"] = "test"
os.environ["LABHUB_COOKIE_SECURE"] = "0"
os.environ["LABHUB_ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["LABHUB_ALLOWED_ORIGINS"] = "http://testserver"
os.environ["LABHUB_SESSION_SECRET"] = "test-session-secret-0123456789-abcdefghijklmnopqrstuvwxyz"
os.environ["LABHUB_EDGE_DEVICE_ID"] = "lab-robotika-01"
os.environ["LABHUB_EDGE_DEVICE_TOKEN"] = "test-edge-device-token-0123456789-abcdef"
os.environ["LABHUB_DEV_SHOW_EMAIL_CODE"] = "0"

import api_server  # noqa: E402
from labhub.database import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(api_server.app) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db():
    yield
    engine.dispose()
    for suffix in ("", "-shm", "-wal", "-journal"):
        path = Path(str(TEST_DB) + suffix)
        if path.exists():
            path.unlink()
