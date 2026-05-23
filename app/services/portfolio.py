from app.db.models import Holding, PortfolioSnapshot
from app.repositories.portfolio import PortfolioRepository
from app.schemas.portfolio import HoldingView, PortfolioView, ProviderStatus
from app.services.analytics import PortfolioAnalytics
from app.services.dhan import DhanService
from app.services.dhan_auth import DhanAuthService
from app.services.market import MarketDataService


class PortfolioService:
    def __init__(self, repository: PortfolioRepository):
        self.repository = repository
        token = DhanAuthService(repository.db).latest_access_token()
        self.dhan = DhanService(access_token=token)
        self.market = MarketDataService()
        self.analytics = PortfolioAnalytics()

    async def fetch_live_portfolio(self, user_id: str, persist: bool = True) -> PortfolioView:
        statuses: list[ProviderStatus] = []
        raw_holdings = await self.dhan.get_holdings()
        raw_positions = await self.dhan.get_positions()
        statuses.append(ProviderStatus("Dhan", True, "Holdings and positions fetched."))

        holdings: list[HoldingView] = []
        for item in raw_holdings:
            symbol = str(item.get("tradingSymbol") or item.get("symbol") or "").strip()
            if not symbol:
                statuses.append(ProviderStatus("Dhan", False, "A holding was skipped due to missing symbol."))
                continue
            quantity = float(item.get("totalQty") or item.get("availableQty") or 0)
            average_price = float(item.get("avgCostPrice") or 0)
            market_price = None
            sector = None
            try:
                quote = await self.market.quote(symbol)
                market_price = float(quote["price"])
                sector = await self.market.sector(symbol)
            except Exception as exc:
                statuses.append(ProviderStatus("yfinance", False, str(exc)))
            market_value = quantity * (market_price if market_price is not None else average_price)
            gain_loss = market_value - (quantity * average_price)
            holdings.append(
                HoldingView(
                    symbol=symbol,
                    quantity=quantity,
                    average_price=average_price,
                    market_price=market_price,
                    market_value=market_value,
                    gain_loss=gain_loss,
                    sector=sector,
                    raw=item,
                )
            )

        portfolio_value = sum(h.market_value for h in holdings)
        invested_amount = sum(h.quantity * h.average_price for h in holdings)
        pnl = portfolio_value - invested_amount
        allocation = self.analytics.allocation(holdings, portfolio_value)
        latest = self.repository.latest_snapshot(user_id)
        daily_pnl = portfolio_value - latest.portfolio_value if latest else None
        view = PortfolioView(
            portfolio_value=portfolio_value,
            invested_amount=invested_amount,
            pnl=pnl,
            daily_pnl=daily_pnl,
            allocation=allocation,
            holdings=holdings,
            statuses=statuses,
            raw={"holdings": raw_holdings, "positions": raw_positions},
        )
        if persist:
            self._persist(user_id, view)
        return view

    def _persist(self, user_id: str, view: PortfolioView) -> PortfolioSnapshot:
        snapshot = PortfolioSnapshot(
            user_id=user_id,
            portfolio_value=view.portfolio_value,
            invested_amount=view.invested_amount,
            pnl=view.pnl,
            daily_pnl=view.daily_pnl,
            allocation=view.allocation,
            raw_payload=view.raw,
        )
        holdings = [
            Holding(
                snapshot_id="",
                symbol=h.symbol,
                quantity=h.quantity,
                average_price=h.average_price,
                market_price=h.market_price,
                market_value=h.market_value,
                gain_loss=h.gain_loss,
                sector=h.sector,
                raw_payload=h.raw,
            )
            for h in view.holdings
        ]
        return self.repository.save_snapshot(snapshot, holdings)
