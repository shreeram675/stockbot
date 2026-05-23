import json

from app.core.errors import ExternalServiceError, MissingConfigurationError
from app.db.models import Recommendation
from app.repositories.portfolio import PortfolioRepository
from app.schemas.portfolio import PortfolioView
from app.services.ai import AIService
from app.services.market import MarketDataService


class RecommendationService:
    def __init__(self, repository: PortfolioRepository):
        self.repository = repository
        self.ai = AIService()
        self.market = MarketDataService()

    async def suggest(
        self,
        user_id: str,
        portfolio: PortfolioView,
        risk_profile: str,
        budget_inr: int,
        persist: bool = True,
    ) -> str:
        news: list[dict] = []
        news_status = "Finnhub news unavailable."
        try:
            news = await self.market.finnhub_market_news()
            news_status = "Finnhub news included."
        except (MissingConfigurationError, ExternalServiceError) as exc:
            news_status = str(exc)

        prompt = self._prompt(portfolio, risk_profile, budget_inr, news, news_status)
        text = await self.ai.generate(prompt)
        if persist:
            self.repository.save_recommendation(
                Recommendation(
                    user_id=user_id,
                    risk_used=risk_profile,
                    recommendation=text,
                    context={
                        "budget_inr": budget_inr,
                        "portfolio": self._portfolio_context(portfolio),
                        "news_status": news_status,
                        "news": news[:5],
                    },
                )
            )
        return text

    def _prompt(
        self,
        portfolio: PortfolioView,
        risk_profile: str,
        budget_inr: int,
        news: list[dict],
        news_status: str,
    ) -> str:
        return (
            "You are a cautious Indian-market portfolio analyst. Use only the provided data. "
            "Do not invent prices, sectors, news, broker data, or guarantees. If data is missing, say so. "
            "Provide a Telegram-friendly recommendation with sections, concise reasoning, and explicit risks. "
            "This is not SEBI-registered investment advice; frame as educational analysis.\n\n"
            f"Risk profile: {risk_profile}\n"
            f"Monthly budget INR: {budget_inr}\n"
            f"News status: {news_status}\n"
            f"Portfolio JSON:\n{json.dumps(self._portfolio_context(portfolio), ensure_ascii=False)}\n"
            f"News JSON:\n{json.dumps(news[:5], ensure_ascii=False)}"
        )

    def _portfolio_context(self, portfolio: PortfolioView) -> dict:
        return {
            "portfolio_value": portfolio.portfolio_value,
            "invested_amount": portfolio.invested_amount,
            "pnl": portfolio.pnl,
            "allocation": portfolio.allocation,
            "holdings": [
                {
                    "symbol": h.symbol,
                    "quantity": h.quantity,
                    "average_price": h.average_price,
                    "market_price": h.market_price,
                    "market_value": h.market_value,
                    "gain_loss": h.gain_loss,
                    "sector": h.sector,
                }
                for h in portfolio.holdings
            ],
            "provider_statuses": [status.__dict__ for status in portfolio.statuses],
        }

