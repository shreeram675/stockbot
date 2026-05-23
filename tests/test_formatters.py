from app.schemas.portfolio import HoldingView, PortfolioView, ProviderStatus
from app.telegram.formatters import format_holdings, format_portfolio


def test_format_portfolio_includes_warnings() -> None:
    portfolio = PortfolioView(
        portfolio_value=100,
        invested_amount=90,
        pnl=10,
        daily_pnl=1,
        allocation={"ABC": 100},
        holdings=[HoldingView("ABC", 1, 90, 100, 100, 10)],
        statuses=[ProviderStatus("Gemini", False, "AI model unavailable.")],
    )
    text = format_portfolio(portfolio)
    assert "Portfolio Snapshot" in text
    assert "AI model unavailable" in text


def test_format_holdings() -> None:
    portfolio = PortfolioView(
        portfolio_value=100,
        invested_amount=90,
        pnl=10,
        daily_pnl=None,
        allocation={},
        holdings=[HoldingView("ABC", 1, 90, 100, 100, 10)],
        statuses=[],
    )
    assert "ABC" in format_holdings(portfolio)

