import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.telegram.bot import ask_command, portfolio_command, risk_command, start, suggest_command


class FakeMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.full_name = "Validation User"


class FakeUpdate:
    def __init__(self, user_id: int) -> None:
        self.effective_user = FakeUser(user_id)
        self.effective_message = FakeMessage()
        self.callback_query = None


async def main() -> None:
    settings = get_settings()
    if settings.telegram_allowed_user_id is None:
        raise SystemExit("TELEGRAM_ALLOWED_USER_ID is not configured.")
    allowed = settings.telegram_allowed_user_id
    cases = [
        ("authorized /start", start, allowed, []),
        ("unauthorized /start", start, allowed + 1, []),
        ("authorized /portfolio", portfolio_command, allowed, []),
        ("authorized /ask", ask_command, allowed, ["Why", "did", "it", "fall?"]),
        ("authorized /suggest", suggest_command, allowed, []),
        ("authorized /risk", risk_command, allowed, []),
    ]
    for name, command, user_id, args in cases:
        update = FakeUpdate(user_id)
        await command(update, SimpleNamespace(args=args))
        reply = update.effective_message.replies[-1] if update.effective_message.replies else "<no reply>"
        print(f"--- {name}")
        print(reply.encode("ascii", "backslashreplace").decode())


if __name__ == "__main__":
    asyncio.run(main())
