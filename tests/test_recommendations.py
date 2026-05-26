from types import SimpleNamespace

import pytest

from app.schemas.portfolio import HoldingView, PortfolioView
from app.services.recommendations import RecommendationService


class FakeRepository:
    def save_recommendation(self, recommendation) -> None:
        self.recommendation = recommendation


class FakeMarket:
    async def finnhub_market_news(self) -> list[dict]:
        return []

    async def quote(self, symbol: str) -> dict:
        prices = {
            "NIFTYBEES": 260,
            "HDFCNIFTY": 270,
            "ICICINIFTY": 280,
            "SETFNIF50": 250,
            "UTINIFTETF": 255,
            "JUNIORBEES": 750,
            "HDFCNEXT50": 730,
            "ICICINXT50": 740,
            "MID150BEES": 220,
            "MOM100": 80,
            "HDFCMID150": 210,
            "MIDCAPETF": 190,
            "GOLDBEES": 70,
            "HDFCGOLD": 75,
            "GOLDIETF": 73,
            "AXISGOLD": 72,
            "SETFGOLD": 74,
            "LIQUIDBEES": 1000,
            "LIQUIDIETF": 999,
            "LIQUIDCASE": 1000,
        }
        return {"price": prices[symbol], "volume": 1_000_000, "source": "test"}


@pytest.mark.asyncio
async def test_suggestion_is_presented_as_monthly_rebalance_not_intraday_trading() -> None:
    service = RecommendationService(FakeRepository())
    service.market = FakeMarket()
    service.ai = SimpleNamespace(available=lambda: False)
    portfolio = PortfolioView(
        portfolio_value=0,
        invested_amount=0,
        pnl=0,
        daily_pnl=None,
        allocation={},
        holdings=[],
        statuses=[],
    )

    text = await service.suggest("user-1", portfolio, "Balanced", 5000, persist=False)

    assert "Monthly Rebalance Plan" in text
    assert "This Month's Actions" in text
    assert "not intraday trading" in text
    assert "BUY:" in text
    assert "Monthly model qty" in text
    assert "Qty: 0" not in text
    assert "Buy List" not in text
    assert "This Month's Plan" not in text
    assert "Universe scanned: 20" in text


@pytest.mark.asyncio
async def test_rebalance_plan_compares_existing_holdings_for_trim_and_swap_reviews() -> None:
    service = RecommendationService(FakeRepository())
    service.market = FakeMarket()
    service.ai = SimpleNamespace(available=lambda: False)
    portfolio = PortfolioView(
        portfolio_value=8000,
        invested_amount=7000,
        pnl=1000,
        daily_pnl=None,
        allocation={"SETFNIF50": 75, "INFY": 25},
        holdings=[
            HoldingView("SETFNIF50", 24, 200, 250, 6000, 1200),
            HoldingView("INFY", 1, 1500, 2000, 2000, 500),
        ],
        statuses=[],
    )

    text = await service.suggest("user-1", portfolio, "Balanced", 5000, persist=False)

    assert "REVIEW TRIM: SBI Nifty 50 ETF (SETFNIF50)" in text
    assert "REVIEW SWAP: INFY (INFY)" in text
    assert "Sell/trim/swap rows are review actions" in text
