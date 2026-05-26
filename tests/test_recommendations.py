from types import SimpleNamespace

import pytest

from app.schemas.portfolio import PortfolioView
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
async def test_suggestion_is_presented_as_long_term_investing_not_trading() -> None:
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

    assert "Monthly Investment Plan" in text
    assert "Long-Term Allocation" in text
    assert "not trading" in text
    assert "Suggested monthly qty" in text
    assert "Qty: 0" not in text
    assert "Buy List" not in text
    assert "This Month's Plan" not in text
    assert "Universe scanned: 20" in text
