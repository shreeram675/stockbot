# mypy: disable-error-code="union-attr,arg-type,index,assignment"

import structlog
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from app.core.config import get_settings
from app.core.errors import ExternalServiceError, MissingConfigurationError
from app.db.session import get_session
from app.repositories.portfolio import PortfolioRepository
from app.repositories.users import UserRepository
from app.services.ai import AIService
from app.services.analytics import PortfolioAnalytics, percent_change
from app.services.portfolio import PortfolioService
from app.services.recommendations import RecommendationService
from app.telegram.formatters import (
    format_health,
    format_holdings,
    format_performance,
    format_portfolio,
)

logger = structlog.get_logger(__name__)
TELEGRAM_MESSAGE_LIMIT = 3900
RISK_MODE_ALIASES = {
    "low": "Conservative",
    "low risk": "Conservative",
    "conservative": "Conservative",
    "safe": "Conservative",
    "balanced": "Balanced",
    "medium": "Balanced",
    "normal": "Balanced",
    "aggressive": "Aggressive",
    "agressive": "Aggressive",
    "agrrecive": "Aggressive",
    "high": "Aggressive",
    "high risk": "Aggressive",
    "custom": "Custom",
}
BOT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Start the assistant"),
    ("help", "Show available commands"),
    ("portfolio", "Portfolio value, P&L, allocation"),
    ("holdings", "Current holdings"),
    ("performance", "Daily, weekly, monthly trends"),
    ("risk", "Show or set risk profile"),
    ("health", "Portfolio health score"),
    ("suggest", "Monthly rebalance plan"),
    ("why", "Explain latest recommendation"),
    ("ask", "Ask a portfolio question"),
    ("simulate", "Projection with assumptions"),
)


def telegram_bot_commands() -> list[BotCommand]:
    return [BotCommand(command, description) for command, description in BOT_COMMANDS]


def help_text() -> str:
    special = {
        "risk": "/risk [Balanced|Conservative|Aggressive|Custom] - show or set risk profile",
        "ask": "/ask <question> - ask portfolio question",
        "simulate": "/simulate 5000 10y - projection with assumptions",
    }
    lines = [
        "🧭 Commands",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for command, description in BOT_COMMANDS[2:]:
        lines.append(special.get(command, f"/{command} - {description[0].lower()}{description[1:]}"))
    return "\n".join(lines)


def _authorized(update: Update) -> bool:
    settings = get_settings()
    user = update.effective_user
    return bool(user and settings.telegram_allowed_user_id and user.id == settings.telegram_allowed_user_id)


async def _reject(update: Update) -> None:
    await _reply(update, "Unauthorized user.")


async def _reply(update: Update, text: str) -> None:
    if update.effective_message:
        await _reply_to_message(update.effective_message, text)


async def _reply_to_message(message, text: str) -> None:
    for chunk in _telegram_chunks(text):
        try:
            await message.reply_text(chunk)
        except TelegramError as exc:
            logger.warning("telegram_reply_failed", error=str(exc))
            return


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


def _parse_risk_mode(args: list[str]) -> tuple[str | None, str | None]:
    raw = " ".join(args).strip()
    if not raw:
        return None, None
    lowered = raw.lower()
    for alias in sorted(RISK_MODE_ALIASES, key=len, reverse=True):
        if lowered == alias or lowered.startswith(f"{alias} "):
            mode = RISK_MODE_ALIASES[alias]
            custom_notes = raw[len(alias):].strip() or None
            return mode, custom_notes
    return None, None


def _repos():
    db = next(get_session())
    return db, UserRepository(db), PortfolioRepository(db)


async def require_user(update: Update):
    if not _authorized(update):
        await _reject(update)
        return None
    try:
        db, users, portfolio = _repos()
    except MissingConfigurationError as exc:
        await _reply(
            update,
            f"⚠️ Database unavailable.\n\n{exc}\n\nTelegram is reachable, but portfolio features need DATABASE_URL.",
        )
        return None
    tg_user = update.effective_user
    assert tg_user is not None
    user = users.get_or_create(tg_user.id, tg_user.full_name)
    latest = users.latest_risk(user.id)
    if latest is None:
        users.set_risk(user.id, get_settings().default_risk_profile)
    return db, users, portfolio, user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _reject(update)
        return
    await _reply(
        update,
        "👋 Stockbot is ready.\n\n"
        "Use /portfolio, /holdings, /performance, /risk, /health, /suggest, /why, /ask, or /simulate."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _reject(update)
        return
    await _reply(update, help_text())


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = await require_user(update)
    if state is None:
        return
    _, users, portfolio_repo, user = state
    try:
        view = await PortfolioService(portfolio_repo).fetch_live_portfolio(user.id, persist=True)
        commentary = None
        ai = AIService()
        if ai.available():
            try:
                commentary = await ai.generate(f"Give concise portfolio commentary using only this data: {view}")
            except Exception as exc:
                view.statuses.append(type(view.statuses[0])("Gemini", False, str(exc)))
        await _reply(update, format_portfolio(view, commentary))
    except (MissingConfigurationError, ExternalServiceError) as exc:
        await _reply(update, f"⚠️ Portfolio unavailable.\n\n{exc}")


async def holdings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = await require_user(update)
    if state is None:
        return
    _, _, portfolio_repo, user = state
    try:
        view = await PortfolioService(portfolio_repo).fetch_live_portfolio(user.id, persist=True)
        await _reply(update, format_holdings(view))
    except (MissingConfigurationError, ExternalServiceError) as exc:
        await _reply(update, f"⚠️ Holdings unavailable.\n\n{exc}")


async def performance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = await require_user(update)
    if state is None:
        return
    _, _, portfolio_repo, user = state
    snapshots = portfolio_repo.snapshots(user.id, 60)
    latest = snapshots[0] if snapshots else None
    if latest is None:
        await _reply(update, "📈 Performance\n\nNo snapshots yet. Run /portfolio first.")
        return
    daily = snapshots[1] if len(snapshots) > 1 else None
    weekly = snapshots[6] if len(snapshots) > 6 else None
    monthly = snapshots[29] if len(snapshots) > 29 else None
    holdings = portfolio_repo.holdings_for_snapshot(latest.id)
    top = max(holdings, key=lambda h: h.gain_loss, default=None)
    worst = min(holdings, key=lambda h: h.gain_loss, default=None)
    perf = {
        "daily_return": percent_change(latest.portfolio_value, daily.portfolio_value if daily else None),
        "weekly_return": percent_change(latest.portfolio_value, weekly.portfolio_value if weekly else None),
        "monthly_return": percent_change(latest.portfolio_value, monthly.portfolio_value if monthly else None),
        "top_performer": top.symbol if top else None,
        "worst_performer": worst.symbol if worst else None,
        "trend": "Based only on persisted snapshots; run /portfolio daily for better trend quality.",
    }
    await _reply(update, format_performance(perf))


async def risk_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _reject(update)
        return
    state = await require_user(update)
    if state is None:
        if not context.args:
            await _reply(
                update,
                "🛡 Risk Profile\n━━━━━━━━━━━━━━━━━━━━\n"
                f"Current default: {get_settings().default_risk_profile}\n\n"
                "Persistence unavailable until DATABASE_URL is configured.",
            )
        return
    _, users, _, user = state
    allowed = {"Conservative", "Balanced", "Aggressive", "Custom"}
    if context.args:
        mode = context.args[0].strip().title()
        custom_notes = " ".join(context.args[1:]).strip() or None
        if mode not in allowed:
            await _reply(
                update,
                "⚠️ Supported risk modes: Conservative, Balanced, Aggressive, Custom."
            )
            return
        pref = users.set_risk(user.id, mode, custom_notes)
        await _reply(update, f"✅ Risk profile updated: {pref.mode}")
        return
    latest = users.latest_risk(user.id)
    await _reply(
        update,
        f"🛡 Risk Profile\n━━━━━━━━━━━━━━━━━━━━\nCurrent: {latest.mode if latest else 'Balanced'}"
    )


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _reject(update)
        return
    state = await require_user(update)
    if state is None:
        if context.args:
            await _reply(update, "Model switching needs DATABASE_URL so the setting can be saved.")
        else:
            await _reply(
                update,
                "Recommendation Model\n"
                f"Current default: {get_settings().default_risk_profile}\n\n"
                "Use /model low risk, /model balanced, or /model aggressive.",
            )
        return
    _, users, _, user = state
    if not context.args:
        latest = users.latest_risk(user.id)
        await _reply(
            update,
            "Recommendation Model\n"
            f"Current: {latest.mode if latest else get_settings().default_risk_profile}\n\n"
            "Use /model low risk, /model balanced, or /model aggressive.",
        )
        return
    mode, custom_notes = _parse_risk_mode(context.args)
    if mode is None or mode == "Custom":
        await _reply(update, "Use: /model low risk, /model balanced, or /model aggressive.")
        return
    pref = users.set_risk(user.id, mode, custom_notes)
    await _reply(update, f"Recommendation model switched to {pref.mode}.")


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = await require_user(update)
    if state is None:
        return
    _, _, portfolio_repo, user = state
    latest = portfolio_repo.latest_snapshot(user.id)
    if latest is None:
        try:
            view = await PortfolioService(portfolio_repo).fetch_live_portfolio(user.id, persist=True)
            health = PortfolioAnalytics().health(view)
        except Exception as exc:
            await _reply(update, f"⚠️ Health unavailable.\n\n{exc}")
            return
    else:
        holdings = portfolio_repo.holdings_for_snapshot(latest.id)
        total = max(latest.portfolio_value, 1)
        view = type(
            "PortfolioLike",
            (),
            {
                "portfolio_value": latest.portfolio_value,
                "holdings": holdings,
                "allocation": {h.symbol: round(h.market_value / total * 100, 2) for h in holdings},
            },
        )
        health = PortfolioAnalytics().health(view)
    await _reply(update, format_health(health))


async def suggest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = await require_user(update)
    if state is None:
        return
    _, users, portfolio_repo, user = state
    risk = users.latest_risk(user.id)
    try:
        view = await PortfolioService(portfolio_repo).fetch_live_portfolio(user.id, persist=True)
        text = await RecommendationService(portfolio_repo).suggest(
            user.id,
            view,
            risk.mode if risk else get_settings().default_risk_profile,
            get_settings().monthly_investment_budget_inr,
            persist=True,
        )
        await _reply(update, f"💡 Monthly Rebalance Plan\n━━━━━━━━━━━━━━━━━━━━\n{text}")
    except MissingConfigurationError as exc:
        await _reply(
            update,
            f"⚠️ Suggestion unavailable.\n\n{exc}\n\nAI recommendations require Gemini and provider keys."
        )
    except ExternalServiceError as exc:
        await _reply(update, f"⚠️ Suggestion unavailable.\n\n{exc}")


async def why_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = await require_user(update)
    if state is None:
        return
    _, _, portfolio_repo, user = state
    recommendation = portfolio_repo.latest_recommendation(user.id)
    if recommendation is None:
        await _reply(update, "🤔 No stored recommendation yet. Run /suggest first.")
        return
    question = " ".join(context.args).strip() or "Explain the reasoning behind the latest recommendation."
    try:
        answer = await AIService().generate(
            f"Use only this stored recommendation and context to answer.\nQuestion: {question}\n"
            f"Recommendation: {recommendation.recommendation}\nContext: {recommendation.context}"
        )
        await _reply(update, f"🧠 Why\n━━━━━━━━━━━━━━━━━━━━\n{answer}")
    except Exception as exc:
        await _reply(update, f"⚠️ AI model unavailable.\n\n{exc}")


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = await require_user(update)
    if state is None:
        return
    _, _, portfolio_repo, user = state
    question = " ".join(context.args).strip()
    if not question:
        await _reply(update, "Ask like this: /ask What is my biggest concentration risk?")
        return
    latest = portfolio_repo.latest_snapshot(user.id)
    if latest is None:
        await _reply(update, "Run /portfolio first so I have grounded portfolio data.")
        return
    holdings = portfolio_repo.holdings_for_snapshot(latest.id)
    try:
        answer = await AIService().generate(
            "Answer using only this portfolio data. If unavailable, say so.\n"
            f"Question: {question}\nSnapshot: {latest.raw_payload}\nHoldings: {[h.raw_payload for h in holdings]}"
        )
        await _reply(update, f"💬 Answer\n━━━━━━━━━━━━━━━━━━━━\n{answer}")
    except Exception as exc:
        await _reply(update, f"⚠️ AI model unavailable.\n\n{exc}")


async def simulate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _reject(update)
        return
    try:
        amount = float(context.args[0]) if context.args else float(get_settings().monthly_investment_budget_inr)
        years_arg = context.args[1].lower() if len(context.args) > 1 else "10y"
        years = int(years_arg.removesuffix("y"))
    except Exception:
        await _reply(update, "Use: /simulate 5000 10y")
        return
    rates = [0.06, 0.10, 0.14]
    lines = [
        "🧮 Simulation",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Monthly investment: Rs. {amount:,.0f}",
        f"Duration: {years} years",
        "",
        "Assumptions: monthly SIP, annualized return scenarios, no taxes/costs/inflation.",
        "These are projections, not guarantees.",
        "",
    ]
    months = years * 12
    for rate in rates:
        monthly = rate / 12
        future_value = amount * (((1 + monthly) ** months - 1) / monthly) * (1 + monthly)
        lines.append(f"{rate * 100:.0f}% CAGR: Rs. {future_value:,.0f}")
    await _reply(update, "\n".join(lines))


def monthly_risk_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Conservative", callback_data="monthly_risk:Conservative"),
                InlineKeyboardButton("Balanced", callback_data="monthly_risk:Balanced"),
            ],
            [
                InlineKeyboardButton("Aggressive", callback_data="monthly_risk:Aggressive"),
                InlineKeyboardButton("Custom", callback_data="monthly_risk:Custom"),
            ],
        ]
    )


async def monthly_risk_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        if update.callback_query:
            await update.callback_query.answer("Unauthorized", show_alert=True)
        return
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    mode = query.data.split(":", 1)[1]
    state = await require_user(update)
    if state is None:
        return
    _, users, portfolio_repo, user = state
    users.set_risk(user.id, mode)
    await query.edit_message_text(
        f"🗓 Monthly workflow started\n\nRisk selected: {mode}\nPreparing grounded recommendation..."
    )
    try:
        view = await PortfolioService(portfolio_repo).fetch_live_portfolio(user.id, persist=True)
        text = await RecommendationService(portfolio_repo).suggest(
            user.id,
            view,
            mode,
            get_settings().monthly_investment_budget_inr,
            persist=True,
        )
        await _reply_to_message(
            query.message,
            "🗓 Monthly Investment Recommendation\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Risk: {mode}\n"
            f"Budget: Rs. {get_settings().monthly_investment_budget_inr:,}\n\n"
            f"{text}"
        )
    except Exception as exc:
        await _reply_to_message(query.message, f"⚠️ Monthly recommendation unavailable.\n\n{exc}")


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise MissingConfigurationError("TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("portfolio", portfolio_command))
    app.add_handler(CommandHandler("holdings", holdings_command))
    app.add_handler(CommandHandler("performance", performance_command))
    app.add_handler(CommandHandler("risk", risk_command))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(CommandHandler("health", health_command))
    app.add_handler(CommandHandler("suggest", suggest_command))
    app.add_handler(CommandHandler("why", why_command))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(CommandHandler("simulate", simulate_command))
    app.add_handler(CallbackQueryHandler(monthly_risk_callback, pattern=r"^monthly_risk:"))
    return app
