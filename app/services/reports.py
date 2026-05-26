from app.core.config import get_settings
from app.repositories.portfolio import PortfolioRepository
from app.repositories.users import UserRepository
from app.services.ai import AIService
from app.services.analytics import PortfolioAnalytics, percent_change
from app.services.market import MarketDataService
from app.services.portfolio import PortfolioService
from app.services.recommendations import RecommendationService
from app.telegram.formatters import (
    format_health,
    format_market_report,
    format_monthly_workflow,
    format_portfolio,
    format_weekly_report,
)


class ReportService:
    def __init__(self, users: UserRepository, portfolio_repo: PortfolioRepository):
        self.settings = get_settings()
        self.users = users
        self.portfolio_repo = portfolio_repo
        self.market = MarketDataService()
        self.analytics = PortfolioAnalytics()
        self.ai = AIService()

    async def daily_morning(self, user_id: str) -> str:
        overview, warnings = await self.market.market_overview()
        news = []
        try:
            news = await self.market.finnhub_market_news()
        except Exception as exc:
            warnings.append(str(exc))
        insight = None
        if self.ai.available():
            try:
                insight = await self.ai.generate(
                    "Create a concise Indian investor morning note from this data only: "
                    f"overview={overview}, news={news[:5]}, warnings={warnings}"
                )
            except Exception as exc:
                warnings.append(f"AI unavailable: {exc}")
        return format_market_report("🌅 Daily Morning Report", overview, news, warnings, insight)

    async def daily_close(self, user_id: str) -> str:
        portfolio = await PortfolioService(self.portfolio_repo).fetch_live_portfolio(user_id, persist=True)
        insight = None
        if self.ai.available():
            try:
                insight = await self.ai.generate(
                    "Create a concise market-close portfolio comment using only this data: "
                    f"{portfolio}"
                )
            except Exception as exc:
                portfolio.statuses.append(type(portfolio.statuses[0])("Gemini", False, str(exc)))
        return format_portfolio(portfolio, insight)

    async def weekly(self, user_id: str) -> str:
        snapshots = self.portfolio_repo.snapshots(user_id, 30)
        latest = snapshots[0] if snapshots else None
        week_old = snapshots[6] if len(snapshots) > 6 else snapshots[-1] if snapshots else None
        if latest is None:
            return "📊 Weekly Report\n\nNo portfolio snapshots are available yet. Run /portfolio first."
        weekly_growth = percent_change(latest.portfolio_value, week_old.portfolio_value if week_old else None)
        holdings = self.portfolio_repo.holdings_for_snapshot(latest.id)
        portfolio_like = {
            "value": latest.portfolio_value,
            "weekly_growth": weekly_growth,
            "allocation": latest.allocation,
            "holdings": [
                {"symbol": h.symbol, "value": h.market_value, "sector": h.sector, "pnl": h.gain_loss}
                for h in holdings
            ],
        }
        return format_weekly_report(portfolio_like)

    async def monthly(self, user_id: str, risk_profile: str) -> str:
        portfolio = await PortfolioService(self.portfolio_repo).fetch_live_portfolio(user_id, persist=True)
        recommendation = await RecommendationService(self.portfolio_repo).suggest(
            user_id=user_id,
            portfolio=portfolio,
            risk_profile=risk_profile,
            budget_inr=self.settings.monthly_investment_budget_inr,
            include_new_cash=True,
            persist=True,
        )
        return format_monthly_workflow(risk_profile, self.settings.monthly_investment_budget_inr, recommendation)

    def health_from_latest(self, user_id: str) -> str:
        latest = self.portfolio_repo.latest_snapshot(user_id)
        if latest is None:
            return "🩺 Portfolio Health\n\nNo portfolio snapshot exists yet. Run /portfolio first."
        holdings = self.portfolio_repo.holdings_for_snapshot(latest.id)
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
        return format_health(self.analytics.health(view))
