from fastapi import APIRouter, Header, HTTPException, Request
from telegram import Bot, Update

from app.core.config import get_settings
from app.core.errors import MissingConfigurationError
from app.db.session import get_session
from app.repositories.portfolio import PortfolioRepository
from app.repositories.users import UserRepository
from app.services.reports import ReportService
from app.telegram.bot import build_application, monthly_risk_keyboard

router = APIRouter()


def _assert_cron_auth(authorization: str | None) -> None:
    settings = get_settings()
    if settings.app_env == "production" and not settings.cron_secret:
        raise HTTPException(status_code=500, detail="CRON_SECRET is required in production")
    if settings.cron_secret and authorization != f"Bearer {settings.cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized cron request")


@router.post("/api/telegram/webhook")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(None)):
    settings = get_settings()
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid Telegram secret token")
    data = await request.json()
    app = build_application()
    await app.initialize()
    try:
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
    finally:
        await app.shutdown()
    return {"ok": True}


async def _send_report(kind: str, authorization: str | None) -> dict[str, str]:
    _assert_cron_auth(authorization)
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise MissingConfigurationError("TELEGRAM_BOT_TOKEN")
    if not settings.telegram_allowed_user_id:
        raise MissingConfigurationError("TELEGRAM_ALLOWED_USER_ID")
    db = next(get_session())
    users = UserRepository(db)
    portfolio = PortfolioRepository(db)
    user = users.get_or_create(settings.telegram_allowed_user_id, "Owner")
    service = ReportService(users, portfolio)
    bot = Bot(settings.telegram_bot_token)
    if kind == "daily-morning":
        text = await service.daily_morning(user.id)
    elif kind == "daily-close":
        text = await service.daily_close(user.id)
    elif kind == "weekly":
        text = await service.weekly(user.id)
    elif kind == "monthly":
        await bot.send_message(
            settings.telegram_allowed_user_id,
            text=(
                "🗓 Monthly Investment Workflow\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"Budget: Rs. {settings.monthly_investment_budget_inr:,}\n\n"
                "Choose the risk profile for this month's recommendation."
            ),
            reply_markup=monthly_risk_keyboard(),
        )
        return {"status": "sent", "kind": kind}
    else:
        raise HTTPException(status_code=404, detail="Unknown report")
    await bot.send_message(settings.telegram_allowed_user_id, text=text)
    return {"status": "sent", "kind": kind}


@router.get("/api/cron/daily-morning")
async def daily_morning(authorization: str | None = Header(None)):
    return await _send_report("daily-morning", authorization)


@router.get("/api/cron/daily-close")
async def daily_close(authorization: str | None = Header(None)):
    return await _send_report("daily-close", authorization)


@router.get("/api/cron/weekly")
async def weekly(authorization: str | None = Header(None)):
    return await _send_report("weekly", authorization)


@router.get("/api/cron/monthly")
async def monthly(authorization: str | None = Header(None)):
    return await _send_report("monthly", authorization)
