from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from telegram import Bot, Update

from app.core.config import get_settings
from app.core.errors import ExternalServiceError, MissingConfigurationError
from app.db.session import get_session
from app.repositories.portfolio import PortfolioRepository
from app.repositories.users import UserRepository
from app.services.dhan_auth import DhanAuthService
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


@router.get("/api/dhan/auth/start")
async def dhan_auth_start():
    db = next(get_session())
    try:
        consent = await DhanAuthService(db).generate_consent()
    except (MissingConfigurationError, ExternalServiceError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RedirectResponse(consent["login_url"], status_code=302)


@router.get("/api/dhan/callback")
async def dhan_callback(request: Request):
    token_id = request.query_params.get("tokenId") or request.query_params.get("token_id")
    if not token_id:
        return HTMLResponse(
            "Dhan callback received, but tokenId was missing. Authentication was not completed.",
            status_code=400,
        )
    db = next(get_session())
    try:
        result = await DhanAuthService(db).consume_consent(token_id)
    except (MissingConfigurationError, ExternalServiceError) as exc:
        return HTMLResponse(f"Dhan authentication failed: {exc}", status_code=400)
    expiry = result["token_expiry"].isoformat() if result["token_expiry"] else "unknown"
    return HTMLResponse(f"Dhan authentication completed. Token expiry: {expiry}. You can close this tab.")


@router.post("/api/dhan/postback")
async def dhan_postback(request: Request):
    payload = await request.json()
    db = next(get_session())
    from app.repositories.logs import LogRepository

    LogRepository(db).alert(
        alert_type="dhan_postback",
        message="Dhan postback received",
        delivery_status="received",
        details=payload if isinstance(payload, dict) else {"payload": payload},
    )
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
    if kind == "monthly":
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
    try:
        if kind == "daily-morning":
            text = await service.daily_morning(user.id)
        elif kind == "daily-close":
            text = await service.daily_close(user.id)
        elif kind == "weekly":
            text = await service.weekly(user.id)
        else:
            raise HTTPException(status_code=404, detail="Unknown report")
    except (MissingConfigurationError, ExternalServiceError) as exc:
        text = f"⚠️ Scheduled report unavailable\n\n{exc}"
        await bot.send_message(settings.telegram_allowed_user_id, text=text)
        return {"status": "degraded", "kind": kind, "error": str(exc)}
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
