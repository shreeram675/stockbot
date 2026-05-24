import json
from dataclasses import dataclass
from math import floor

from app.core.errors import ExternalServiceError, MissingConfigurationError
from app.db.models import Recommendation
from app.repositories.portfolio import PortfolioRepository
from app.schemas.portfolio import PortfolioView
from app.services.ai import AIService
from app.services.market import MarketDataService


@dataclass(frozen=True)
class AllocationInstrument:
    symbol: str
    name: str
    category: str
    reason: str


@dataclass(frozen=True)
class AllocationLeg:
    instrument: AllocationInstrument
    target_percent: int
    target_amount: float
    price: float
    quantity: int

    @property
    def deployed_amount(self) -> float:
        return self.price * self.quantity


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

        plan_text, plan_context = await self._model_allocation(portfolio, risk_profile, budget_inr)
        ai_note = await self._short_ai_note(portfolio, risk_profile, news, news_status, plan_context)
        text = plan_text
        if ai_note:
            text = f"{text}\n\n🧠 AI Note\n{ai_note}"
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
                        "model_allocation": plan_context,
                    },
                )
            )
        return text

    async def _model_allocation(
        self,
        portfolio: PortfolioView,
        risk_profile: str,
        budget_inr: int,
    ) -> tuple[str, dict]:
        targets = self._targets_for_risk(risk_profile)
        legs: list[AllocationLeg] = []
        warnings: list[str] = []
        for instrument, target_percent in targets:
            target_amount = budget_inr * target_percent / 100
            try:
                quote = await self.market.quote(instrument.symbol)
                price = float(quote["price"])
            except ExternalServiceError as exc:
                warnings.append(str(exc))
                continue
            quantity = max(floor(target_amount / price), 0)
            legs.append(
                AllocationLeg(
                    instrument=instrument,
                    target_percent=target_percent,
                    target_amount=target_amount,
                    price=price,
                    quantity=quantity,
                )
            )

        deployed = sum(leg.deployed_amount for leg in legs)
        cash_left = max(float(budget_inr) - deployed, 0.0)
        if not legs:
            raise ExternalServiceError("Recommendation", "market prices unavailable for model basket")

        portfolio_state = (
            "empty portfolio"
            if not portfolio.holdings
            else f"{len(portfolio.holdings)} current holding(s)"
        )
        lines = [
            "🎯 This Month's Plan",
            "━━━━━━━━━━━━━━━━━━━━",
            f"Budget: Rs. {budget_inr:,.0f}",
            f"Risk: {risk_profile}",
            f"Portfolio: {portfolio_state}",
            "",
            "🧺 Buy List",
        ]
        for leg in legs:
            if leg.quantity <= 0:
                lines.append(
                    f"• {leg.instrument.name} ({leg.instrument.symbol})\n"
                    f"  Qty: 0 | Price: Rs. {leg.price:,.2f}\n"
                    f"  Reason: target slice too small for 1 unit"
                )
            else:
                lines.append(
                    f"• {leg.instrument.name} ({leg.instrument.symbol})\n"
                    f"  Qty: {leg.quantity} | Approx: Rs. {leg.deployed_amount:,.0f}\n"
                    f"  Price: Rs. {leg.price:,.2f} | Target: {leg.target_percent}%\n"
                    f"  Why: {leg.instrument.reason}"
                )
        lines.extend(
            [
                "",
                f"💰 Used: Rs. {deployed:,.0f}",
                f"🪙 Cash left: Rs. {cash_left:,.0f}",
                "",
                "⚠️ Notes",
                "• Quantities use latest yfinance prices and may differ at order time.",
                "• This is an educational model allocation, not SEBI-registered advice.",
                "• Review liquidity, taxes, brokerage, and your own suitability before placing orders.",
            ]
        )
        if warnings:
            lines.extend(["", "⚠️ Data Gaps", *[f"• {warning}" for warning in warnings[:3]]])
        context = {
            "budget_inr": budget_inr,
            "risk_profile": risk_profile,
            "deployed_amount": round(deployed, 2),
            "cash_left": round(cash_left, 2),
            "legs": [
                {
                    "symbol": leg.instrument.symbol,
                    "name": leg.instrument.name,
                    "category": leg.instrument.category,
                    "target_percent": leg.target_percent,
                    "price": round(leg.price, 2),
                    "quantity": leg.quantity,
                    "deployed_amount": round(leg.deployed_amount, 2),
                }
                for leg in legs
            ],
            "warnings": warnings,
        }
        return "\n".join(lines), context

    async def _short_ai_note(
        self,
        portfolio: PortfolioView,
        risk_profile: str,
        news: list[dict],
        news_status: str,
        plan_context: dict,
    ) -> str | None:
        if not self.ai.available():
            return None
        try:
            return await self.ai.generate(
                "Write only 2 short Telegram bullets. No markdown headings. "
                "Use only the provided data. Do not add new instruments, prices, or quantities. "
                "Mention one risk and one reason the allocation is sensible.\n"
                f"Risk profile: {risk_profile}\n"
                f"Portfolio: {json.dumps(self._portfolio_context(portfolio), ensure_ascii=False)}\n"
                f"Plan: {json.dumps(plan_context, ensure_ascii=False)}\n"
                f"News status: {news_status}\n"
                f"News: {json.dumps(news[:3], ensure_ascii=False)}"
            )
        except Exception:
            return None

    def _targets_for_risk(self, risk_profile: str) -> list[tuple[AllocationInstrument, int]]:
        equity_core = AllocationInstrument(
            "NIFTYBEES",
            "Nippon India ETF Nifty 50 BeES",
            "Large-cap equity ETF",
            "broad Nifty 50 exposure",
        )
        equity_growth = AllocationInstrument(
            "JUNIORBEES",
            "Nippon India ETF Junior BeES",
            "Next 50 equity ETF",
            "adds growth beyond large caps",
        )
        gold = AllocationInstrument(
            "GOLDBEES",
            "Nippon India ETF Gold BeES",
            "Gold commodity ETF",
            "diversifier against equity and currency risk",
        )
        cash = AllocationInstrument(
            "LIQUIDBEES",
            "Nippon India ETF Liquid BeES",
            "Liquid debt ETF",
            "keeps part of the budget stable and liquid",
        )
        mode = risk_profile.strip().title()
        if mode == "Conservative":
            return [(cash, 40), (equity_core, 35), (gold, 25)]
        if mode == "Aggressive":
            return [(equity_core, 60), (equity_growth, 25), (gold, 15)]
        return [(equity_core, 55), (gold, 25), (cash, 20)]

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
