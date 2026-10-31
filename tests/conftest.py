"""Shared pytest fixtures for blueprint-level tests."""

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Flask test client fully isolated from the repository.

    - CWD (hence uploads/) is pointed at a temp dir.
    - SQLALCHEMY_DATABASE_URI is overridden to a temp-file SQLite database so
      tests never read/write the repo's instance/ai_local_support.db, which
      the default relative URI would resolve to regardless of CWD.
    """
    monkeypatch.chdir(tmp_path)
    from app_factory import create_app

    app = create_app(
        config_overrides={
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        }
    )
    app.config["TESTING"] = True
    return app.test_client()
