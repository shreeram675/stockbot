import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import ExternalServiceError, MissingConfigurationError
from app.db.session import build_engine
from app.services.ai import AIService
from app.services.dhan import DhanService
from app.services.market import MarketDataService


def line(key: str, value) -> None:
    print(f"{key}={value}")


def validate_db() -> None:
    engine = build_engine()
    with engine.connect() as connection:
        line("db_select_1", connection.execute(text("select 1")).scalar())
        tables = [
            "users",
            "risk_preferences",
            "portfolio_snapshots",
            "holdings",
            "recommendations",
            "system_logs",
            "alert_logs",
            "alembic_version",
        ]
        rows = connection.execute(
            text(
                "select tablename from pg_tables "
                "where schemaname='public' and tablename = any(:tables) order by tablename"
            ),
            {"tables": tables},
        ).scalars()
        line("db_tables", ",".join(rows))


async def validate_dhan() -> None:
    service = DhanService()
    try:
        holdings = await service.get_holdings()
        positions = await service.get_positions()
        line("dhan_holdings_ok", True)
        line("dhan_holdings_count", len(holdings))
        line("dhan_positions_ok", True)
        line("dhan_positions_count", len(positions))
        if holdings:
            first = holdings[0]
            safe_keys = [
                key
                for key in ("tradingSymbol", "securityId", "exchangeSegment", "totalQty", "avgCostPrice")
                if key in first
            ]
            line("dhan_first_holding_keys", ",".join(safe_keys))
    except (MissingConfigurationError, ExternalServiceError) as exc:
        line("dhan_error", str(exc))


async def validate_gemini() -> None:
    try:
        text = await AIService().generate(
            "Reply with exactly: Gemini validation OK. Do not add anything else."
        )
        line("gemini_ok", "Gemini validation OK" in text)
        line("gemini_response", text[:120].replace("\n", " "))
    except (MissingConfigurationError, ExternalServiceError) as exc:
        line("gemini_error", str(exc))


async def validate_finnhub() -> None:
    market = MarketDataService()
    try:
        news = await market.finnhub_market_news()
        line("finnhub_ok", True)
        line("finnhub_news_count", len(news))
        if news:
            line("finnhub_first_headline_present", bool(news[0].get("headline")))
    except (MissingConfigurationError, ExternalServiceError) as exc:
        line("finnhub_error", str(exc))


async def validate_yfinance() -> None:
    market = MarketDataService()
    for symbol in ["^NSEI", "RELIANCE"]:
        try:
            quote = await market.quote(symbol)
            line(f"yfinance_{symbol}_ok", True)
            line(f"yfinance_{symbol}_price_present", bool(quote.get("price")))
        except ExternalServiceError as exc:
            line(f"yfinance_{symbol}_error", str(exc))


async def main() -> None:
    settings = get_settings()
    line("app_env", settings.app_env)
    line("gemini_model", settings.gemini_model)
    line("telegram_webhook_url_present", bool(settings.telegram_webhook_url))
    validate_db()
    await validate_dhan()
    await validate_gemini()
    await validate_finnhub()
    await validate_yfinance()


if __name__ == "__main__":
    asyncio.run(main())

