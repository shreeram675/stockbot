import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.main import app


def make_update(update_id: int, user_id: int, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(time.time()),
            "chat": {"id": user_id, "type": "private", "first_name": "Validation"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Validation"},
            "text": text,
            "entities": [{"offset": 0, "length": len(text.split()[0]), "type": "bot_command"}],
        },
    }


def main() -> None:
    settings = get_settings()
    if settings.telegram_allowed_user_id is None:
        raise SystemExit("TELEGRAM_ALLOWED_USER_ID is not configured")
    headers = {}
    if settings.telegram_webhook_secret:
        headers["X-Telegram-Bot-Api-Secret-Token"] = settings.telegram_webhook_secret
    client = TestClient(app)
    commands = [
        "/start",
        "/help",
        "/portfolio",
        "/holdings",
        "/performance",
        "/risk",
        "/health",
        "/ask Why did my portfolio fall?",
        "/suggest",
        "/simulate 5000 10y",
    ]
    base = int(time.time())
    for index, command in enumerate(commands, start=1):
        response = client.post(
            "/api/telegram/webhook",
            headers=headers,
            json=make_update(base + index, settings.telegram_allowed_user_id, command),
        )
        print(f"{command} status={response.status_code} body={response.text[:200]}")
    unauthorized = client.post(
        "/api/telegram/webhook",
        headers=headers,
        json=make_update(base + 999, settings.telegram_allowed_user_id + 1, "/start"),
    )
    print(f"unauthorized /start status={unauthorized.status_code} body={unauthorized.text[:200]}")


if __name__ == "__main__":
    main()
