from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_telegram_command_sync_requires_configured_secret(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABCDEF")
    monkeypatch.setenv("CRON_SECRET", "")
    get_settings.cache_clear()

    response = TestClient(app).post("/api/telegram/commands/sync")

    assert response.status_code == 500
    assert response.json()["detail"] == "CRON_SECRET is required for this operation"


def test_telegram_command_sync_rejects_missing_bearer(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABCDEF")
    monkeypatch.setenv("CRON_SECRET", "secret")
    get_settings.cache_clear()

    response = TestClient(app).post("/api/telegram/commands/sync")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized request"
