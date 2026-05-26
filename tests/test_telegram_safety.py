from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.telegram.bot import (
    _parse_risk_mode,
    ask_command,
    build_application,
    help_command,
    model_command,
    portfolio_command,
    risk_command,
    start,
    suggest_command,
    telegram_bot_commands,
)


class FakeMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.full_name = "Test User"


class FakeUpdate:
    def __init__(self, user_id: int) -> None:
        self.effective_user = FakeUser(user_id)
        self.effective_message = FakeMessage()
        self.callback_query = None


def configure_telegram_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.db.session as db_session

    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABCDEF")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    db_session.engine = None
    db_session.SessionLocal = None
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_unauthorized_user_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_telegram_only(monkeypatch)
    update = FakeUpdate(222)
    await start(update, SimpleNamespace(args=[]))
    assert update.effective_message.replies == ["Unauthorized user."]


@pytest.mark.asyncio
async def test_authorized_start_works_without_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_telegram_only(monkeypatch)
    update = FakeUpdate(111)
    await start(update, SimpleNamespace(args=[]))
    assert "Stockbot is ready" in update.effective_message.replies[0]
    assert "/model" not in update.effective_message.replies[0]


@pytest.mark.asyncio
async def test_help_lists_primary_commands_without_duplicate_model_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_telegram_only(monkeypatch)
    update = FakeUpdate(111)
    await help_command(update, SimpleNamespace(args=[]))
    reply = update.effective_message.replies[0]
    assert "/risk [Balanced|Conservative|Aggressive|Custom] - show or set risk profile" in reply
    assert "/model" not in reply
    assert reply.count("/risk") == 1


@pytest.mark.asyncio
async def test_provider_backed_commands_return_transparent_database_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_telegram_only(monkeypatch)
    for command, args in [
        (portfolio_command, []),
        (ask_command, ["What", "is", "my", "risk?"]),
        (suggest_command, []),
    ]:
        update = FakeUpdate(111)
        await command(update, SimpleNamespace(args=args))
        assert "Database unavailable" in update.effective_message.replies[0]
        assert "DATABASE_URL" in update.effective_message.replies[0]


@pytest.mark.asyncio
async def test_risk_view_falls_back_to_default_without_database(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_telegram_only(monkeypatch)
    update = FakeUpdate(111)
    await risk_command(update, SimpleNamespace(args=[]))
    assert "Current default: Balanced" in update.effective_message.replies[-1]
    assert "Persistence unavailable" in update.effective_message.replies[-1]


@pytest.mark.asyncio
async def test_model_command_falls_back_without_database(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_telegram_only(monkeypatch)
    update = FakeUpdate(111)
    await model_command(update, SimpleNamespace(args=[]))
    assert "Current default: Balanced" in update.effective_message.replies[-1]
    assert "low risk" in update.effective_message.replies[-1]


def test_model_risk_aliases() -> None:
    assert _parse_risk_mode(["low", "risk"]) == ("Conservative", None)
    assert _parse_risk_mode(["balanced"]) == ("Balanced", None)
    assert _parse_risk_mode(["agrrecive"]) == ("Aggressive", None)


def test_command_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_telegram_only(monkeypatch)
    app = build_application()
    names = [
        getattr(handler.callback, "__name__", type(handler).__name__)
        for group in app.handlers.values()
        for handler in group
    ]
    assert names == [
        "start",
        "help_command",
        "portfolio_command",
        "holdings_command",
        "performance_command",
        "risk_command",
        "model_command",
        "health_command",
        "suggest_command",
        "why_command",
        "ask_command",
        "simulate_command",
        "monthly_risk_callback",
    ]


def test_telegram_command_menu_excludes_legacy_model_alias() -> None:
    commands = [command.command for command in telegram_bot_commands()]
    assert "model" not in commands
    assert commands == [
        "start",
        "help",
        "portfolio",
        "holdings",
        "performance",
        "risk",
        "health",
        "suggest",
        "why",
        "ask",
        "simulate",
    ]
