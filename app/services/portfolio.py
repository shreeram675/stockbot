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
            holding = await self._holding_from_record(item, statuses, source="holding")
            if holding is not None:
                holdings.append(holding)

        holding_symbols = {holding.symbol.upper() for holding in holdings}
        for item in raw_positions:
            if not self._is_long_delivery_position(item):
                continue
            symbol = self._symbol(item)
            if not symbol or symbol.upper() in holding_symbols:
                continue
            holding = await self._holding_from_record(item, statuses, source="position")
            if holding is not None:
                holdings.append(holding)
                holding_symbols.add(holding.symbol.upper())

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

    async def _holding_from_record(
        self,
        item: dict,
        statuses: list[ProviderStatus],
        source: str,
    ) -> HoldingView | None:
        symbol = self._symbol(item)
        if not symbol:
            statuses.append(ProviderStatus("Dhan", False, f"A {source} was skipped due to missing symbol."))
            return None
        quantity = self._quantity(item)
        if quantity <= 0:
            return None
        average_price = self._average_price(item)
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
        return HoldingView(
            symbol=symbol,
            quantity=quantity,
            average_price=average_price,
            market_price=market_price,
            market_value=market_value,
            gain_loss=gain_loss,
            sector=sector,
            raw=item,
        )

    def _symbol(self, item: dict) -> str:
        return str(item.get("tradingSymbol") or item.get("symbol") or "").strip()

    def _quantity(self, item: dict) -> float:
        for key in ("totalQty", "availableQty", "netQty", "quantity", "qty"):
            value = item.get(key)
            if value not in (None, ""):
                return abs(float(value))
        buy_qty = float(item.get("buyQty") or 0)
        sell_qty = float(item.get("sellQty") or 0)
        return max(buy_qty - sell_qty, 0.0)

    def _average_price(self, item: dict) -> float:
        for key in ("avgCostPrice", "buyAvg", "averagePrice", "avgPrice", "costPrice"):
            value = item.get(key)
            if value not in (None, ""):
                return float(value)
        return 0.0

    def _is_long_delivery_position(self, item: dict) -> bool:
        quantity = self._quantity(item)
        if quantity <= 0:
            return False
        position_type = str(item.get("positionType") or item.get("position_type") or "").upper()
        if position_type and position_type not in {"LONG", "OPEN"}:
            return False
        product = str(item.get("productType") or item.get("product") or "").upper()
        return product in {"", "CNC", "DELIVERY", "LONGTERM", "MTF"}

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
