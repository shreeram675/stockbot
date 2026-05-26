import pytest

from app.services.portfolio import PortfolioService


class FakeRepository:
    db = object()

    def latest_snapshot(self, user_id: str):
        return None

    def save_snapshot(self, snapshot, holdings):
        self.snapshot = snapshot
        self.holdings = holdings
        return snapshot


class FakeDhan:
    async def get_holdings(self) -> list[dict]:
        return []

    async def get_positions(self) -> list[dict]:
        return [
            {"tradingSymbol": "LIQUIDCASE", "productType": "CNC", "positionType": "LONG", "netQty": 1, "buyAvg": 999},
            {"tradingSymbol": "NIFTYBEES", "productType": "CNC", "positionType": "LONG", "netQty": 10, "buyAvg": 270},
            {"tradingSymbol": "GOLDIETF", "productType": "CNC", "positionType": "LONG", "netQty": 5, "buyAvg": 72},
            {"tradingSymbol": "ITC", "productType": "CNC", "positionType": "LONG", "netQty": 2, "buyAvg": 430},
            {"tradingSymbol": "SOUTHBANK", "productType": "CNC", "positionType": "LONG", "netQty": 20, "buyAvg": 28},
            {"tradingSymbol": "INTRADAY", "productType": "INTRADAY", "positionType": "LONG", "netQty": 1, "buyAvg": 10},
            {"tradingSymbol": "CLOSED", "productType": "CNC", "positionType": "CLOSED", "netQty": 1, "buyAvg": 10},
        ]


class FakeAuth:
    def __init__(self, db) -> None:
        pass

    def latest_access_token(self):
        return None


class FakeMarket:
    async def quote(self, symbol: str) -> dict:
        prices = {
            "LIQUIDCASE": 999,
            "NIFTYBEES": 270,
            "GOLDIETF": 72,
            "ITC": 430,
            "SOUTHBANK": 28,
        }
        return {"price": prices[symbol]}

    async def sector(self, symbol: str) -> str:
        return "Test"


@pytest.mark.asyncio
async def test_fetch_live_portfolio_uses_long_cnc_positions_when_holdings_empty(monkeypatch) -> None:
    monkeypatch.setattr("app.services.portfolio.DhanAuthService", FakeAuth)
    monkeypatch.setattr("app.services.portfolio.DhanService", lambda access_token=None: FakeDhan())
    monkeypatch.setattr("app.services.portfolio.MarketDataService", lambda: FakeMarket())

    service = PortfolioService(FakeRepository())

    view = await service.fetch_live_portfolio("user-1", persist=False)

    assert [holding.symbol for holding in view.holdings] == [
        "LIQUIDCASE",
        "NIFTYBEES",
        "GOLDIETF",
        "ITC",
        "SOUTHBANK",
    ]
    assert view.portfolio_value == 5479
    assert view.invested_amount == 5479
