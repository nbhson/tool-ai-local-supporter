"""Tests for the /health (a.k.a. /api/health) endpoint."""


def test_health_reports_ok_with_temp_db(client, monkeypatch):
    """DB reachable + Ollama/Celery unreachable must still yield a 200 overall."""
    # Simulate Ollama/Celery being down so the test never depends on local services
    import requests as _requests

    def _raise(*args, **kwargs):
        raise _requests.ConnectionError("no ollama in test env")

    monkeypatch.setattr(_requests.Session, "get", _raise, raising=False)
    monkeypatch.setattr(_requests, "get", _raise, raising=False)

    res = client.get("/health")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "healthy"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["ollama"]["status"] == "unavailable"
    assert body["checks"]["celery"]["status"] in ("ok", "unreachable")


def test_health_alias_api_health(client):
    res = client.get("/api/health")
    assert res.status_code in (200, 503)
    body = res.get_json()
    assert "checks" in body
    assert set(body["checks"].keys()) == {"database", "ollama", "celery"}


def test_health_returns_503_when_db_fails(client, monkeypatch):
    from services.database import db

    res = client.get("/health")
    # Sanity: healthy with temp sqlite DB before we break the probe
    assert res.status_code == 200

    # Now break the DB probe and expect 503
    def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(type(db.session), "execute", _boom)
    res2 = client.get("/health")
    assert res2.status_code == 503
    body = res2.get_json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["database"]["status"] == "error"
