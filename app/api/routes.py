import hashlib
import json
import os

import httpx
import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from telegram import Bot, Update

from app.core.config import get_settings
from app.core.errors import ExternalServiceError, MissingConfigurationError
from app.db.session import get_session
from app.repositories.portfolio import PortfolioRepository
from app.repositories.users import UserRepository
from app.services.analytics import PortfolioAnalytics
from app.services.dhan_auth import DhanAuthService
from app.services.http import async_client
from app.services.portfolio import PortfolioService
from app.services.recommendations import RecommendationService
from app.services.reports import ReportService
from app.telegram.bot import build_application, monthly_risk_keyboard, telegram_bot_commands
from app.telegram.formatters import format_health, format_portfolio

router = APIRouter()
logger = structlog.get_logger(__name__)
TELEGRAM_MESSAGE_LIMIT = 3900


def _assert_cron_auth(authorization: str | None) -> None:
    settings = get_settings()
    if settings.app_env == "production" and not settings.cron_secret:
        raise HTTPException(status_code=500, detail="CRON_SECRET is required in production")
    if settings.cron_secret and authorization != f"Bearer {settings.cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized cron request")


def _fingerprint(value: str | None) -> str:
    if not value:
        return "missing"
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def _mask(value: str | None) -> str:
    if not value:
        return "missing"
    if len(value) <= 8:
        return f"len={len(value)} sha256={_fingerprint(value)}"
    return f"{value[:4]}...{value[-4:]} len={len(value)} sha256={_fingerprint(value)}"


def _redact_token_fields(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if key.lower() in {"accesstoken", "access_token", "token", "jwttoken", "jwt_token"}:
                redacted[key] = _mask(str(item)) if item is not None else item
            else:
                redacted[key] = _redact_token_fields(item)
        return redacted
    if isinstance(value, list):
        return [_redact_token_fields(item) for item in value]
    return value


def _response_text(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text
    if response.is_success:
        data = _redact_token_fields(data)
    return json.dumps(data, ensure_ascii=False)


def _deployment_metadata() -> dict[str, str]:
    return {
        "vercel_deployment_id": os.getenv("VERCEL_DEPLOYMENT_ID") or "missing",
        "vercel_git_commit_sha": os.getenv("VERCEL_GIT_COMMIT_SHA") or "missing",
        "vercel_git_commit_ref": os.getenv("VERCEL_GIT_COMMIT_REF") or "missing",
        "vercel_url": os.getenv("VERCEL_URL") or "missing",
    }


def _assert_dhan_debug_auth(authorization: str | None, debug_fingerprint: str | None) -> None:
    settings = get_settings()
    if settings.cron_secret and authorization == f"Bearer {settings.cron_secret}":
        return
    expected = hashlib.sha256((settings.dhan_api_secret or "").encode()).hexdigest()
    if settings.dhan_api_secret and debug_fingerprint == expected:
        return
    raise HTTPException(status_code=403, detail="Unauthorized Dhan debug request")


def _telegram_chunks(text: str) -> list[str]:
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= TELEGRAM_MESSAGE_LIMIT:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, TELEGRAM_MESSAGE_LIMIT)
        if split_at < 1000:
            split_at = TELEGRAM_MESSAGE_LIMIT
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return chunks


async def _send_telegram_text(bot: Bot, chat_id: int, text: str) -> None:
    for chunk in _telegram_chunks(text):
        await bot.send_message(chat_id, text=chunk)


async def _send_authenticated_daily_activity(db, bot: Bot) -> None:
    settings = get_settings()
    if not settings.telegram_allowed_user_id:
        return
    users = UserRepository(db)
    portfolio_repo = PortfolioRepository(db)
    user = users.get_or_create(settings.telegram_allowed_user_id, "Owner")
    risk = users.latest_risk(user.id)
    try:
        view = await PortfolioService(portfolio_repo).fetch_live_portfolio(user.id, persist=True)
        health = PortfolioAnalytics().health(view)
        await _send_telegram_text(bot, settings.telegram_allowed_user_id, format_portfolio(view))
        await _send_telegram_text(bot, settings.telegram_allowed_user_id, format_health(health))
        try:
            recommendation = await RecommendationService(portfolio_repo).suggest(
                user_id=user.id,
                portfolio=view,
                risk_profile=risk.mode if risk else settings.default_risk_profile,
                budget_inr=settings.monthly_investment_budget_inr,
                persist=True,
            )
            await _send_telegram_text(
                bot,
                settings.telegram_allowed_user_id,
                (
                    "💡 Today's Investing Allocation\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"{recommendation}"
                ),
            )
        except Exception as exc:
            await _send_telegram_text(
                bot,
                settings.telegram_allowed_user_id,
                f"⚠️ Investing allocation unavailable today.\n\n{exc}",
            )
    except Exception as exc:
        await _send_telegram_text(
            bot,
            settings.telegram_allowed_user_id,
            f"⚠️ Dhan authenticated, but today's portfolio activity failed.\n\n{exc}",
        )


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


@router.post("/api/telegram/commands/sync")
async def sync_telegram_commands(authorization: str | None = Header(None)):
    _assert_cron_auth(authorization)
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise MissingConfigurationError("TELEGRAM_BOT_TOKEN")
    commands = telegram_bot_commands()
    async with Bot(settings.telegram_bot_token) as bot:
        await bot.set_my_commands(commands)
    return {
        "ok": True,
        "commands": [command.command for command in commands],
    }


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
    logger.info(
        "dhan_callback_received",
        query_param_names=sorted(request.query_params.keys()),
        token_id_present=bool(token_id),
        token_id_length=len(token_id or ""),
        token_id_sha256=_fingerprint(token_id),
        **_deployment_metadata(),
    )
    if not token_id:
        return HTMLResponse(
            "Dhan callback received, but tokenId was missing. Authentication was not completed.",
            status_code=400,
        )
    db = next(get_session())
    try:
        result = await DhanAuthService(db).consume_consent(token_id)
    except (MissingConfigurationError, ExternalServiceError) as exc:
        logger.warning(
            "dhan_callback_auth_failed",
            error=str(exc),
            query_param_names=sorted(request.query_params.keys()),
            token_id_length=len(token_id),
            token_id_sha256=_fingerprint(token_id),
            **_deployment_metadata(),
        )
        return HTMLResponse(f"Dhan authentication failed: {exc}", status_code=400)
    except Exception as exc:
        logger.exception(
            "dhan_callback_unexpected_failure",
            error_type=type(exc).__name__,
            query_param_names=sorted(request.query_params.keys()),
            token_id_length=len(token_id),
            token_id_sha256=_fingerprint(token_id),
            **_deployment_metadata(),
        )
        return HTMLResponse(
            "Dhan authentication failed because the server hit an unexpected runtime error. "
            "Check Vercel logs for dhan_callback_unexpected_failure.",
            status_code=500,
        )
    expiry = result["token_expiry"].isoformat() if result["token_expiry"] else "unknown"
    settings = get_settings()
    if settings.telegram_bot_token and settings.telegram_allowed_user_id:
        bot = Bot(settings.telegram_bot_token)
        await bot.send_message(
            settings.telegram_allowed_user_id,
            text=(
                "✅ Dhan authenticated for today\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"Token expiry: {expiry}\n\n"
                "Running today's portfolio activity now."
            ),
        )
        await _send_authenticated_daily_activity(db, bot)
    return HTMLResponse(f"Dhan authentication completed. Token expiry: {expiry}. You can close this tab.")


@router.get("/api/dhan/debug/consume")
async def dhan_debug_consume(
    request: Request,
    authorization: str | None = Header(None),
    x_dhan_debug_fingerprint: str | None = Header(None),
):
    _assert_dhan_debug_auth(authorization, x_dhan_debug_fingerprint)
    settings = get_settings()
    token_id = request.query_params.get("tokenId") or request.query_params.get("token_id")
    if not token_id:
        raise HTTPException(status_code=400, detail="tokenId query parameter is required")
    if not settings.dhan_api_key:
        raise MissingConfigurationError("DHAN_API_KEY")
    if not settings.dhan_api_secret:
        raise MissingConfigurationError("DHAN_API_SECRET")
    url = f"{settings.dhan_auth_base_url.rstrip('/')}/app/consumeApp-consent"
    headers = {"app_id": settings.dhan_api_key, "app_secret": settings.dhan_api_secret}
    persist_requested = request.query_params.get("persist", "").lower() in {"1", "true", "yes"}
    try:
        async with async_client() as client:
            response = await client.get(url, params={"tokenId": token_id}, headers=headers)
    except httpx.HTTPError as exc:
        raise ExternalServiceError("Dhan", f"debug consume request failed: {exc}") from exc
    query_params = {
        key: {
            "length": len(value),
            "sha256": _fingerprint(value),
        }
        for key, value in request.query_params.items()
    }
    debug_payload = {
        "deployment": _deployment_metadata(),
        "env_fingerprints": {
            "DHAN_API_KEY": _mask(settings.dhan_api_key),
            "DHAN_API_SECRET": _mask(settings.dhan_api_secret),
            "DHAN_CLIENT_ID": _mask(settings.dhan_client_id),
        },
        "callback_query_params_received": query_params,
        "consume_request": {
            "method": "GET",
            "url": f"{url}?tokenId=<redacted len={len(token_id)} sha256={_fingerprint(token_id)}>",
            "headers": {"app_id": _mask(settings.dhan_api_key), "app_secret": _mask(settings.dhan_api_secret)},
        },
        "consume_response": {
            "status": response.status_code,
            "raw_text": _response_text(response),
        },
    }
    if persist_requested:
        try:
            db = next(get_session())
            result = await DhanAuthService(db).consume_consent(token_id)
            debug_payload["persistence"] = {
                "status": "success",
                "token_expiry": result["token_expiry"].isoformat() if result["token_expiry"] else "unknown",
            }
        except Exception as exc:
            debug_payload["persistence"] = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    return debug_payload


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
    if kind != "daily-auth" and not DhanAuthService(db).has_valid_stored_token():
        return {
            "status": "skipped",
            "kind": kind,
            "reason": "No valid stored Dhan token. Daily activity waits for user re-authentication.",
        }
    service = ReportService(users, portfolio)
    bot = Bot(settings.telegram_bot_token)
    if kind == "daily-auth":
        auth_url = DhanAuthService(db).auth_start_url()
        await bot.send_message(
            settings.telegram_allowed_user_id,
            text=(
                "🔐 Dhan Re-authentication\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"Authenticate for today's portfolio updates and suggestions:\n{auth_url}\n\n"
                "If you skip this, today's Dhan-backed activity will be skipped. "
                "No portfolio data will be refreshed without a valid token."
            ),
        )
        return {"status": "sent", "kind": kind}
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


@router.get("/api/cron/daily-auth")
async def daily_auth(authorization: str | None = Header(None)):
    return await _send_report("daily-auth", authorization)


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
