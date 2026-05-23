from statistics import mean
from typing import Any

from app.schemas.portfolio import HoldingView, PortfolioView


def percent_change(current: float, previous: float | None) -> float | None:
    if previous is None or previous == 0:
        return None
    return (current - previous) / previous * 100


class PortfolioAnalytics:
    def allocation(self, holdings: list[HoldingView], total_value: float) -> dict[str, float]:
        if total_value <= 0:
            return {}
        return {h.symbol: round(h.market_value / total_value * 100, 2) for h in holdings}

    def top_holding_weight(self, portfolio: PortfolioView) -> float:
        return max(portfolio.allocation.values(), default=0.0)

    def concentration_score(self, portfolio: PortfolioView) -> tuple[int, str]:
        top_weight = self.top_holding_weight(portfolio)
        if top_weight <= 20:
            return 25, "Top holding concentration is within a healthy range."
        if top_weight <= 35:
            return 17, "Top holding concentration is moderate."
        return 8, "Top holding concentration is high."

    def diversification_score(self, portfolio: PortfolioView) -> tuple[int, str]:
        count = len(portfolio.holdings)
        if count >= 12:
            return 25, "Holding count supports broad diversification."
        if count >= 6:
            return 17, "Holding count is acceptable but can improve."
        return 8, "Holding count is low, so idiosyncratic risk is higher."

    def sector_score(self, portfolio: PortfolioView) -> tuple[int, str]:
        sectors = [h.sector for h in portfolio.holdings if h.sector]
        if not sectors:
            return 0, "Sector data was unavailable, so this component is excluded from confidence."
        weights: dict[str, float] = {}
        for h in portfolio.holdings:
            if h.sector:
                weights[h.sector] = weights.get(h.sector, 0) + h.market_value
        top = max(weights.values()) / max(sum(weights.values()), 1) * 100
        if top <= 30:
            return 25, "Sector exposure appears diversified from available data."
        if top <= 45:
            return 17, "Largest known sector exposure is moderate."
        return 8, "Largest known sector exposure is high."

    def pnl_quality_score(self, portfolio: PortfolioView) -> tuple[int, str]:
        losses = [h.gain_loss for h in portfolio.holdings if h.gain_loss < 0]
        gains = [h.gain_loss for h in portfolio.holdings if h.gain_loss >= 0]
        if not portfolio.holdings:
            return 0, "No holdings available."
        gain_ratio = len(gains) / len(portfolio.holdings)
        avg_loss = abs(mean(losses)) if losses else 0
        if gain_ratio >= 0.65 and avg_loss < max(portfolio.portfolio_value * 0.03, 1):
            return 25, "Most holdings are positive or drawdowns are contained."
        if gain_ratio >= 0.4:
            return 17, "Portfolio has mixed winners and laggards."
        return 8, "Many holdings are currently below cost."

    def health(self, portfolio: PortfolioView | Any) -> dict:
        components = {
            "diversification": self.diversification_score(portfolio),
            "concentration": self.concentration_score(portfolio),
            "sector_exposure": self.sector_score(portfolio),
            "pnl_quality": self.pnl_quality_score(portfolio),
        }
        score = sum(value for value, _ in components.values())
        return {
            "score": score,
            "components": {
                name: {"score": value, "reason": reason}
                for name, (value, reason) in components.items()
            },
        }
