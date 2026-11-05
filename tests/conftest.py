from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure settings/env are test-friendly before app imports bind the engine.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["BOT_USERNAME"] = "demo"
os.environ["BOT_PASSWORD"] = "demo"
os.environ["SELENIUM_REMOTE_URL"] = ""
os.environ["BOT_STEALTH"] = "false"
os.environ["HUMANIZE_DELAYS"] = "false"

from app.config import get_settings

get_settings.cache_clear()


@pytest.fixture()
def db_session(tmp_path: Path):
    from app.db.database import Base
    from app.db import models  # noqa: F401

    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    from app.db.database import get_db
    from app.main import app

    def _override_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
