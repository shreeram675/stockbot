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
async def test_monthly_workflow_includes_new_cash_buys() -> None:
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

    text = await service.suggest(
        "user-1",
        portfolio,
        "Balanced",
        5000,
        include_new_cash=True,
        persist=False,
    )

    assert "Monthly New-Cash Rebalance Plan" in text
    assert "New monthly cash: Rs. 5,000" in text
    assert "This Month's Actions" in text
    assert "BUY:" in text
    assert "Monthly model qty" in text
    assert "Qty: 0" not in text
    assert "Buy List" not in text
    assert "This Month's Plan" not in text
    assert "Universe scanned: 20" in text


@pytest.mark.asyncio
async def test_suggest_reviews_current_holdings_without_new_cash() -> None:
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

    text = await service.suggest(
        "user-1",
        portfolio,
        "Balanced",
        0,
        include_new_cash=False,
        persist=False,
    )

    assert "Holdings Rebalance Review" in text
    assert "New cash: Rs. 0 - reviewing current holdings only" in text
    assert "New monthly cash" not in text
    assert "BUY:" not in text
    assert "UNDERWEIGHT:" in text
    assert "REVIEW TRIM: SBI Nifty 50 ETF (SETFNIF50)" in text
    assert "REVIEW SWAP: INFY (INFY)" in text
    assert "Sell/trim/swap rows are review actions" in text


@pytest.mark.asyncio
async def test_zero_value_holdings_review_does_not_show_target_mix() -> None:
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

    text = await service.suggest(
        "user-1",
        portfolio,
        "Conservative",
        0,
        include_new_cash=False,
        persist=False,
    )

    assert "Holdings Rebalance Review" in text
    assert "Portfolio value: Rs. 0" in text
    assert "No rebalance actions available because portfolio value is Rs. 0." in text
    assert "Target Mix" not in text
    assert "Universe scanned" not in text
    assert "AI Note" not in text


@pytest.mark.asyncio
async def test_small_gain_swap_is_skipped_when_costs_are_higher() -> None:
    service = RecommendationService(FakeRepository())
    service.market = FakeMarket()
    service.ai = SimpleNamespace(available=lambda: False)
    portfolio = PortfolioView(
        portfolio_value=1000,
        invested_amount=995,
        pnl=5,
        daily_pnl=None,
        allocation={"INFY": 100},
        holdings=[
            HoldingView("INFY", 1, 995, 1000, 1000, 5),
        ],
        statuses=[],
    )

    text = await service.suggest(
        "user-1",
        portfolio,
        "Balanced",
        0,
        include_new_cash=False,
        persist=False,
    )

    assert "REVIEW SWAP: INFY (INFY)" not in text
    assert "HOLD: INFY (INFY)" in text
    assert "swap skipped: estimated gain does not clear sell+buy brokerage/transaction costs" in text
    assert "Est. benefit/cost: Rs. 5 / Rs. 43" in text
