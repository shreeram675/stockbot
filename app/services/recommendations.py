from dataclasses import dataclass, replace
from math import floor

from app.core.config import get_settings
from app.core.errors import ExternalServiceError, MissingConfigurationError
from app.db.models import Recommendation
from app.repositories.portfolio import PortfolioRepository
from app.schemas.portfolio import PortfolioView
from app.services.ai import AIService
from app.services.llm_prompts import recommendation_note_prompt
from app.services.market import MarketDataService


@dataclass(frozen=True)
class AllocationInstrument:
    symbol: str
    name: str
    issuer: str
    category: str
    reason: str


@dataclass(frozen=True)
class AllocationLeg:
    instrument: AllocationInstrument
    target_percent: int
    target_amount: float
    price: float
    quantity: int
    volume: int | None
    score: float
    scanned_count: int

    @property
    def deployed_amount(self) -> float:
        return self.price * self.quantity


@dataclass(frozen=True)
class RebalanceAction:
    action: str
    symbol: str
    name: str
    quantity: int | None
    amount: float
    reason: str
    estimated_cost: float = 0.0
    estimated_benefit: float | None = None


class RecommendationService:
    def __init__(self, repository: PortfolioRepository):
        self.repository = repository
        self.settings = get_settings()
        self.ai = AIService()
        self.market = MarketDataService()

    async def suggest(
        self,
        user_id: str,
        portfolio: PortfolioView,
        risk_profile: str,
        budget_inr: int,
        include_new_cash: bool = False,
        persist: bool = True,
    ) -> str:
        news: list[dict] = []
        news_status = "Finnhub news unavailable."
        try:
            news = await self.market.finnhub_market_news()
            news_status = "Finnhub news included."
        except (MissingConfigurationError, ExternalServiceError) as exc:
            news_status = str(exc)

        plan_text, plan_context = await self._model_allocation(
            portfolio,
            risk_profile,
            budget_inr,
            include_new_cash,
        )
        ai_note = None
        if plan_context.get("status") != "no_review_base":
            ai_note = await self._short_ai_note(portfolio, risk_profile, news, news_status, plan_context)
        text = f"{plan_text}\n\n🧠 AI Note\n{ai_note}" if ai_note else plan_text
        if persist:
            self.repository.save_recommendation(
                Recommendation(
                    user_id=user_id,
                    risk_used=risk_profile,
                    recommendation=text,
                    context={
                        "budget_inr": budget_inr,
                        "include_new_cash": include_new_cash,
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
        include_new_cash: bool,
    ) -> tuple[str, dict]:
        if not include_new_cash and budget_inr <= 0 and portfolio.portfolio_value <= 0:
            portfolio_state = (
                "empty portfolio"
                if not portfolio.holdings
                else f"{len(portfolio.holdings)} current holding(s) with no market value"
            )
            lines = [
                "🎯 Holdings Rebalance Review",
                "━━━━━━━━━━━━━━━━━━━━",
                "New cash: Rs. 0 - reviewing current holdings only",
                f"Portfolio value: Rs. {portfolio.portfolio_value:,.0f}",
                "Review base: Rs. 0",
                f"Risk: {risk_profile}",
                "Style: in-between-month holdings review, no new investment assumed",
                f"Portfolio: {portfolio_state}",
                "",
                "🧺 This Month's Actions",
                "• No rebalance actions available because portfolio value is Rs. 0.",
                "• Refresh holdings or add portfolio data before reviewing target allocations.",
                "",
                "⚠️ Notes",
                "• No target mix is shown until there is a portfolio value or new cash budget to allocate.",
                "• This is an educational model allocation, not SEBI-registered advice.",
            ]
            context = {
                "status": "no_review_base",
                "budget_inr": budget_inr,
                "include_new_cash": include_new_cash,
                "risk_profile": risk_profile,
                "portfolio_value": round(portfolio.portfolio_value, 2),
                "review_base": 0,
                "cash_used": 0,
                "cash_left": 0,
                "universe_symbols": [],
                "legs": [],
                "actions": [],
                "warnings": ["portfolio value is zero"],
            }
            return "\n".join(lines), context

        targets = self._targets_for_risk(risk_profile)
        legs: list[AllocationLeg] = []
        warnings: list[str] = []
        scanned_universe: list[str] = []
        used_issuers: set[str] = set()
        held_symbols = {self._normalize_symbol(holding.symbol) for holding in portfolio.holdings}

        for label, candidates, target_percent in targets:
            target_amount = budget_inr * target_percent / 100 if include_new_cash else 0.0
            evaluated: list[tuple[float, AllocationInstrument, float, int | None, int]] = []
            for instrument in candidates:
                scanned_universe.append(instrument.symbol)
                try:
                    quote = await self.market.quote(instrument.symbol)
                    price = float(quote["price"])
                    volume = quote.get("volume")
                    quantity = max(floor(target_amount / price), 0)
                    fit_score = self._budget_fit_score(target_amount, price, quantity)
                    liquidity_score = min(float(volume or 0) / 500_000, 1)
                    issuer_penalty = 0.08 if instrument.issuer in used_issuers else 0
                    existing_holding_bonus = (
                        0.5 if self._normalize_symbol(instrument.symbol) in held_symbols else 0
                    )
                    score = (
                        (fit_score * 0.65)
                        + (liquidity_score * 0.35)
                        + existing_holding_bonus
                        - issuer_penalty
                    )
                    evaluated.append((score, instrument, price, int(volume) if volume else None, quantity))
                except ExternalServiceError as exc:
                    warnings.append(f"{instrument.symbol}: {exc.message}")
            if not evaluated:
                warnings.append(f"{label}: no live prices available")
                continue
            score, instrument, price, volume, quantity = max(evaluated, key=lambda item: item[0])
            used_issuers.add(instrument.issuer)
            legs.append(
                AllocationLeg(
                    instrument=instrument,
                    target_percent=target_percent,
                    target_amount=target_amount,
                    price=price,
                    quantity=quantity,
                    volume=volume,
                    score=score,
                    scanned_count=len(candidates),
                )
            )

        if not legs:
            raise ExternalServiceError("Recommendation", "market prices unavailable for model basket")

        if include_new_cash:
            legs = self._use_remaining_cash_for_zero_quantity_legs(legs, budget_inr)
        actions, cash_used, cash_left = self._rebalance_actions(
            portfolio,
            legs,
            budget_inr if include_new_cash else 0,
        )
        portfolio_state = "empty portfolio" if not portfolio.holdings else f"{len(portfolio.holdings)} current holding(s)"
        total_after_budget = portfolio.portfolio_value + (budget_inr if include_new_cash else 0)
        title = "🎯 Monthly New-Cash Rebalance Plan" if include_new_cash else "🎯 Holdings Rebalance Review"
        scope = (
            f"New monthly cash: Rs. {budget_inr:,.0f}"
            if include_new_cash
            else "New cash: Rs. 0 - reviewing current holdings only"
        )
        style = (
            "Style: scheduled monthly investing + portfolio rebalance"
            if include_new_cash
            else "Style: in-between-month holdings review, no new investment assumed"
        )
        lines = [
            title,
            "━━━━━━━━━━━━━━━━━━━━",
            scope,
            f"Portfolio value: Rs. {portfolio.portfolio_value:,.0f}",
            f"Review base: Rs. {total_after_budget:,.0f}",
            f"Risk: {risk_profile}",
            style,
            f"Portfolio: {portfolio_state}",
            f"Universe scanned: {len(set(scanned_universe))} NSE ETF/equity/commodity candidates",
            "",
            "🎚 Target Mix",
        ]
        for leg in legs:
            lines.append(self._format_leg(leg, include_new_cash))
        lines.extend(["", "🧺 This Month's Actions"])
        if actions:
            lines.extend(self._format_action(action) for action in actions)
        else:
            lines.append("• No buy/sell actions from available data. Keep cash until prices/portfolio data are available.")
        lines.extend(
            [
                "",
                f"💰 New cash used: Rs. {cash_used:,.0f}",
                f"🪙 Cash left: Rs. {cash_left:,.0f}",
                "",
                "⚠️ Notes",
                "• Quantities use latest Yahoo/yfinance prices and may differ at order time.",
                "• Sell/trim/swap rows are review actions based on allocation drift, not automatic orders.",
                "• Sell/swap actions are skipped when estimated gain does not clear brokerage/transaction costs.",
                "• Check taxes, brokerage, liquidity, and your conviction before selling anything.",
                "• Diversification is spread across multiple equity sleeves plus gold/stability where data is available.",
                "• This is an educational model allocation, not SEBI-registered advice.",
                "• Review liquidity, taxes, brokerage, and suitability before placing orders.",
            ]
        )
        if warnings:
            lines.extend(["", f"⚠️ Data: skipped {len(warnings)} candidate(s) with unavailable live prices."])

        context = {
            "budget_inr": budget_inr,
            "include_new_cash": include_new_cash,
            "risk_profile": risk_profile,
            "portfolio_value": round(portfolio.portfolio_value, 2),
            "review_base": round(total_after_budget, 2),
            "cash_used": round(cash_used, 2),
            "cash_left": round(cash_left, 2),
            "universe_symbols": sorted(set(scanned_universe)),
            "legs": [
                {
                    "symbol": leg.instrument.symbol,
                    "name": leg.instrument.name,
                    "issuer": leg.instrument.issuer,
                    "category": leg.instrument.category,
                    "target_percent": leg.target_percent,
                    "price": round(leg.price, 2),
                    "quantity": leg.quantity,
                    "volume": leg.volume,
                    "score": round(leg.score, 4),
                    "monthly_amount": round(leg.deployed_amount, 2),
                }
                for leg in legs
            ],
            "actions": [action.__dict__ for action in actions],
            "warnings": warnings,
        }
        return "\n".join(lines), context

    def _budget_fit_score(self, target_amount: float, price: float, quantity: int) -> float:
        if quantity <= 0:
            return 0
        deployed = quantity * price
        return 1 - max(target_amount - deployed, 0) / max(target_amount, 1)

    def _use_remaining_cash_for_zero_quantity_legs(
        self,
        legs: list[AllocationLeg],
        budget_inr: int,
    ) -> list[AllocationLeg]:
        deployed = sum(leg.deployed_amount for leg in legs)
        adjusted: list[AllocationLeg] = []
        for leg in legs:
            if leg.quantity == 0 and leg.price <= max(float(budget_inr) - deployed, 0):
                leg = replace(leg, quantity=1)
                deployed += leg.price
            adjusted.append(leg)
        return adjusted

    def _format_leg(self, leg: AllocationLeg, include_new_cash: bool) -> str:
        if not include_new_cash:
            volume_text = f" | Vol: {leg.volume:,}" if leg.volume else ""
            return (
                f"• {leg.instrument.name} ({leg.instrument.symbol})\n"
                f"  Price: Rs. {leg.price:,.2f} | Target: {leg.target_percent}%{volume_text}\n"
                f"  Why: {leg.instrument.reason}\n"
                f"  Picked from {leg.scanned_count} options"
            )
        if leg.quantity <= 0:
            return (
                f"• {leg.instrument.name} ({leg.instrument.symbol})\n"
                f"  Monthly qty: 0 | Price: Rs. {leg.price:,.2f}\n"
                "  Reason: target allocation too small for 1 unit"
            )
        volume_text = f" | Vol: {leg.volume:,}" if leg.volume else ""
        return (
            f"• {leg.instrument.name} ({leg.instrument.symbol})\n"
            f"  Monthly model qty: {leg.quantity} | Approx: Rs. {leg.deployed_amount:,.0f}\n"
            f"  Price: Rs. {leg.price:,.2f} | Target: {leg.target_percent}%{volume_text}\n"
            f"  Why: {leg.instrument.reason}\n"
            f"  Picked from {leg.scanned_count} options"
        )

    def _rebalance_actions(
        self,
        portfolio: PortfolioView,
        legs: list[AllocationLeg],
        budget_inr: int,
    ) -> tuple[list[RebalanceAction], float, float]:
        total_after_budget = portfolio.portfolio_value + budget_inr
        holding_values = {
            self._normalize_symbol(holding.symbol): holding.market_value
            for holding in portfolio.holdings
        }
        holding_quantities = {
            self._normalize_symbol(holding.symbol): holding.quantity
            for holding in portfolio.holdings
        }
        holding_gains = {
            self._normalize_symbol(holding.symbol): holding.gain_loss
            for holding in portfolio.holdings
        }
        target_symbols = {self._normalize_symbol(leg.instrument.symbol) for leg in legs}
        actions: list[RebalanceAction] = []
        available_cash = float(budget_inr)

        for leg in legs:
            symbol = self._normalize_symbol(leg.instrument.symbol)
            target_value = total_after_budget * leg.target_percent / 100
            current_value = holding_values.get(symbol, 0.0)
            difference = target_value - current_value
            tolerance = max(target_value * 0.10, leg.price)
            if difference > tolerance:
                if available_cash >= leg.price:
                    buy_amount = min(difference, available_cash)
                    quantity = floor(buy_amount / leg.price)
                    if quantity > 0:
                        amount = quantity * leg.price
                        available_cash -= amount
                        actions.append(
                            RebalanceAction(
                                action="BUY",
                                symbol=leg.instrument.symbol,
                                name=leg.instrument.name,
                                quantity=quantity,
                                amount=amount,
                                reason=f"below {leg.target_percent}% target by approx Rs. {difference:,.0f}",
                            )
                        )
                else:
                    actions.append(
                        RebalanceAction(
                            action="UNDERWEIGHT",
                            symbol=leg.instrument.symbol,
                            name=leg.instrument.name,
                            quantity=None,
                            amount=difference,
                            reason=f"below {leg.target_percent}% target; no new cash assumed in this review",
                        )
                    )
            elif difference < -tolerance:
                excess = abs(difference)
                quantity = min(floor(excess / leg.price), floor(holding_quantities.get(symbol, 0.0)))
                sell_amount = quantity * leg.price if quantity > 0 else min(excess, current_value)
                estimated_cost = self._estimated_transaction_cost(sell_amount, orders=1)
                estimated_benefit = self._proportional_gain(
                    holding_gains.get(symbol, 0.0),
                    current_value,
                    sell_amount,
                )
                if not self._clears_transaction_cost(estimated_benefit, estimated_cost):
                    actions.append(
                        RebalanceAction(
                            action="HOLD",
                            symbol=leg.instrument.symbol,
                            name=leg.instrument.name,
                            quantity=None,
                            amount=current_value,
                            reason=(
                                "trim skipped: estimated gain does not clear brokerage/"
                                "transaction costs with buffer"
                            ),
                            estimated_cost=estimated_cost,
                            estimated_benefit=estimated_benefit,
                        )
                    )
                    continue
                actions.append(
                    RebalanceAction(
                        action="REVIEW TRIM",
                        symbol=leg.instrument.symbol,
                        name=leg.instrument.name,
                        quantity=quantity if quantity > 0 else None,
                        amount=excess,
                        reason=(
                            f"above {leg.target_percent}% target by approx Rs. {excess:,.0f}; "
                            "estimated gain clears transaction costs"
                        ),
                        estimated_cost=estimated_cost,
                        estimated_benefit=estimated_benefit,
                    )
                )
            elif current_value > 0:
                actions.append(
                    RebalanceAction(
                        action="HOLD",
                        symbol=leg.instrument.symbol,
                        name=leg.instrument.name,
                        quantity=None,
                        amount=current_value,
                        reason=f"near {leg.target_percent}% target band",
                    )
                )

        for holding in sorted(portfolio.holdings, key=lambda item: item.market_value, reverse=True):
            symbol = self._normalize_symbol(holding.symbol)
            if symbol in target_symbols or holding.market_value <= 0:
                continue
            estimated_cost = self._estimated_transaction_cost(holding.market_value * 2, orders=2)
            estimated_benefit = holding.gain_loss
            if not self._clears_transaction_cost(estimated_benefit, estimated_cost):
                actions.append(
                    RebalanceAction(
                        action="HOLD",
                        symbol=holding.symbol,
                        name=holding.symbol,
                        quantity=None,
                        amount=holding.market_value,
                        reason=(
                            "swap skipped: estimated gain does not clear sell+buy brokerage/"
                            "transaction costs with buffer"
                        ),
                        estimated_cost=estimated_cost,
                        estimated_benefit=estimated_benefit,
                    )
                )
                continue
            actions.append(
                RebalanceAction(
                    action="REVIEW SWAP",
                    symbol=holding.symbol,
                    name=holding.symbol,
                    quantity=floor(holding.quantity) if holding.quantity > 0 else None,
                    amount=holding.market_value,
                    reason=(
                        "not part of this month's selected diversified model basket; "
                        "estimated gain clears sell+buy transaction costs"
                    ),
                    estimated_cost=estimated_cost,
                    estimated_benefit=estimated_benefit,
                )
            )

        cash_used = float(budget_inr) - available_cash
        return actions, cash_used, max(available_cash, 0.0)

    def _estimated_transaction_cost(self, turnover: float, orders: int) -> float:
        if turnover <= 0 or orders <= 0:
            return 0.0
        return (
            (float(orders) * self.settings.rebalance_flat_fee_per_order_inr)
            + (turnover * self.settings.rebalance_variable_cost_rate)
        )

    def _proportional_gain(self, total_gain: float, holding_value: float, trade_value: float) -> float:
        if holding_value <= 0 or trade_value <= 0:
            return 0.0
        return total_gain * min(trade_value / holding_value, 1.0)

    def _clears_transaction_cost(self, estimated_benefit: float, estimated_cost: float) -> bool:
        required = estimated_cost * self.settings.rebalance_min_benefit_cost_ratio
        return estimated_benefit > required

    def _format_action(self, action: RebalanceAction) -> str:
        quantity = f" | Qty: {action.quantity}" if action.quantity else ""
        cost_text = ""
        if action.estimated_cost > 0:
            benefit = action.estimated_benefit or 0.0
            cost_text = f"\n  Est. benefit/cost: Rs. {benefit:,.0f} / Rs. {action.estimated_cost:,.0f}"
        return (
            f"• {action.action}: {action.name} ({action.symbol}){quantity}\n"
            f"  Approx: Rs. {action.amount:,.0f}\n"
            f"  Why: {action.reason}"
            f"{cost_text}"
        )

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.strip().upper().removesuffix(".NS").removesuffix(".BO")

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
                recommendation_note_prompt(
                    portfolio=self._portfolio_context(portfolio),
                    risk_profile=risk_profile,
                    plan_context=plan_context,
                    news_status=news_status,
                    news=news,
                )
            )
        except Exception:
            return None

    def _targets_for_risk(
        self,
        risk_profile: str,
    ) -> list[tuple[str, list[AllocationInstrument], int]]:
        equity_core = [
            AllocationInstrument("NIFTYBEES", "Nifty 50 ETF", "Nippon", "Large-cap equity ETF", "broad Nifty 50 exposure"),
            AllocationInstrument("HDFCNIFTY", "HDFC Nifty 50 ETF", "HDFC", "Large-cap equity ETF", "broad Nifty 50 exposure"),
            AllocationInstrument("ICICINIFTY", "ICICI Nifty 50 ETF", "ICICI", "Large-cap equity ETF", "broad Nifty 50 exposure"),
            AllocationInstrument("SETFNIF50", "SBI Nifty 50 ETF", "SBI", "Large-cap equity ETF", "broad Nifty 50 exposure"),
            AllocationInstrument("UTINIFTETF", "UTI Nifty 50 ETF", "UTI", "Large-cap equity ETF", "broad Nifty 50 exposure"),
        ]
        equity_growth = [
            AllocationInstrument("JUNIORBEES", "Nifty Next 50 ETF", "Nippon", "Next 50 equity ETF", "adds growth beyond large caps"),
            AllocationInstrument("HDFCNEXT50", "HDFC Nifty Next 50 ETF", "HDFC", "Next 50 equity ETF", "adds growth beyond large caps"),
            AllocationInstrument("ICICINXT50", "ICICI Nifty Next 50 ETF", "ICICI", "Next 50 equity ETF", "adds growth beyond large caps"),
        ]
        equity_mid = [
            AllocationInstrument("MID150BEES", "Nifty Midcap 150 ETF", "Nippon", "Mid-cap equity ETF", "adds mid-cap diversification"),
            AllocationInstrument("MOM100", "Nifty Midcap 100 ETF", "Motilal Oswal", "Mid-cap equity ETF", "adds mid-cap diversification"),
            AllocationInstrument("HDFCMID150", "HDFC Nifty Midcap 150 ETF", "HDFC", "Mid-cap equity ETF", "adds mid-cap diversification"),
            AllocationInstrument("MIDCAPETF", "Mirae Midcap ETF", "Mirae", "Mid-cap equity ETF", "adds mid-cap diversification"),
        ]
        large_cap_stocks = [
            AllocationInstrument("RELIANCE", "Reliance Industries", "Reliance", "Large-cap stock", "adds broad market leader exposure"),
            AllocationInstrument("HDFCBANK", "HDFC Bank", "HDFC Bank", "Large-cap stock", "adds banking exposure"),
            AllocationInstrument("INFY", "Infosys", "Infosys", "Large-cap stock", "adds IT services exposure"),
            AllocationInstrument("ITC", "ITC", "ITC", "Large-cap stock", "adds defensive consumption exposure"),
            AllocationInstrument("LT", "Larsen & Toubro", "L&T", "Large-cap stock", "adds infrastructure/capex exposure"),
        ]
        gold = [
            AllocationInstrument("GOLDBEES", "Gold ETF", "Nippon", "Gold commodity ETF", "diversifier against equity/currency risk"),
            AllocationInstrument("HDFCGOLD", "HDFC Gold ETF", "HDFC", "Gold commodity ETF", "diversifier against equity/currency risk"),
            AllocationInstrument("GOLDIETF", "ICICI Gold ETF", "ICICI", "Gold commodity ETF", "diversifier against equity/currency risk"),
            AllocationInstrument("AXISGOLD", "Axis Gold ETF", "Axis", "Gold commodity ETF", "diversifier against equity/currency risk"),
            AllocationInstrument("SETFGOLD", "SBI Gold ETF", "SBI", "Gold commodity ETF", "diversifier against equity/currency risk"),
        ]
        liquid = [
            AllocationInstrument("LIQUIDBEES", "Liquid ETF", "Nippon", "Liquid debt ETF", "keeps budget stable and liquid"),
            AllocationInstrument("LIQUIDIETF", "ICICI Liquid ETF", "ICICI", "Liquid debt ETF", "keeps budget stable and liquid"),
            AllocationInstrument("LIQUIDCASE", "Liquid ETF", "Zerodha", "Liquid debt ETF", "keeps budget stable and liquid"),
        ]
        mode = risk_profile.strip().title()
        if mode == "Conservative":
            return [
                ("Stability", liquid, 30),
                ("Core equity", equity_core, 25),
                ("Gold", gold, 25),
                ("Quality large-cap stock", large_cap_stocks, 20),
            ]
        if mode == "Aggressive":
            return [
                ("Core equity", equity_core, 30),
                ("Growth equity", equity_growth, 25),
                ("Mid-cap equity", equity_mid, 25),
                ("Quality large-cap stock", large_cap_stocks, 10),
                ("Gold", gold, 10),
            ]
        return [
            ("Core equity", equity_core, 30),
            ("Growth equity", equity_growth, 20),
            ("Mid-cap equity", equity_mid, 15),
            ("Gold", gold, 20),
            ("Stability", liquid, 15),
        ]

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
