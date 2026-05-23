from app.schemas.portfolio import HoldingView, PortfolioView
from app.services.analytics import PortfolioAnalytics, percent_change


def test_percent_change() -> None:
    assert percent_change(110, 100) == 10
    assert percent_change(100, 0) is None
    assert percent_change(100, None) is None


def test_health_uses_available_sector_data() -> None:
    portfolio = PortfolioView(
        portfolio_value=1000,
        invested_amount=900,
        pnl=100,
        daily_pnl=None,
        allocation={"A": 50, "B": 30, "C": 20},
        holdings=[
            HoldingView("A", 1, 100, 500, 500, 400, "IT"),
            HoldingView("B", 1, 100, 300, 300, 200, "Banking"),
            HoldingView("C", 1, 100, 200, 200, 100, "FMCG"),
        ],
        statuses=[],
    )
    health = PortfolioAnalytics().health(portfolio)
    assert 0 <= health["score"] <= 100
    assert "sector_exposure" in health["components"]

