from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_read_root() -> None:
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"


def test_health_when_db_connected(monkeypatch) -> None:
    async def _ok() -> bool:
        return True

    monkeypatch.setattr("app.main.check_database_connection", _ok)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_health_when_db_disconnected(monkeypatch) -> None:
    async def _fail() -> bool:
        return False

    monkeypatch.setattr("app.main.check_database_connection", _fail)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "disconnected"}


def test_settings_defaults() -> None:
    settings = get_settings()
    assert settings.game_languages == ["tr", "en"]
    assert settings.turn_duration_hours_options == [12, 24, 48, 72]
    assert settings.default_ui_language == "tr"
