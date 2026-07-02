from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


TEST_DB_DIR = Path(__file__).resolve().parent / "_data"
TEST_DB_DIR.mkdir(exist_ok=True)
TEST_DB_PATH = TEST_DB_DIR / "test.sqlite"

os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["FLASK_ENV"] = "development"
os.environ["MAIL_HOST"] = "smtp.gmail.com"
os.environ["MAIL_PORT"] = "587"
os.environ["MAIL_USERNAME"] = "sender@gmail.com"
os.environ["MAIL_PASSWORD"] = "app-password"
os.environ["MAIL_FROM"] = "sender@gmail.com"
os.environ["MAIL_USE_TLS"] = "true"

sys.modules.pop("app", None)
import app as app_module  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return app_module.app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def reset_database():
    with app_module.app.app_context():
        app_module.db.session.remove()
        app_module.db.drop_all()
        app_module.db.create_all()
    yield
    with app_module.app.app_context():
        app_module.db.session.remove()
        app_module.db.drop_all()


@pytest.fixture()
def app_api():
    return app_module
