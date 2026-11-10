"""Test database selection.

If TEST_DATABASE_URL is set (a PostgreSQL URL for a scratch database) the schema is built by running the real
Alembic migrations. Otherwise tests run on in-memory SQLite with metadata.create_all plus the same currency seed.
"""
import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db import Base, get_db
from app.main import app
from app.models import Currency
from app.seed import CURRENCIES

PG_URL = os.environ.get("TEST_DATABASE_URL")


def alembic_config(url: str) -> Config:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture()
def engine():
    if PG_URL:
        eng = create_engine(PG_URL)
        with eng.begin() as c:
            c.exec_driver_sql("DROP SCHEMA public CASCADE")
            c.exec_driver_sql("CREATE SCHEMA public")
        command.upgrade(alembic_config(PG_URL), "head")
    else:
        eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(eng)
        with sessionmaker(bind=eng)() as s:
            s.add_all(Currency(code=c, name=n, symbol=sym, exponent=e) for c, n, sym, e in CURRENCIES)
            s.commit()
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture()
def client(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
