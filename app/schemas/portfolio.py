from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderStatus:
    service: str
    ok: bool
    message: str
    cached: bool = False


@dataclass(frozen=True)
class HoldingView:
    symbol: str
    quantity: float
    average_price: float
    market_price: float | None
    market_value: float
    gain_loss: float
    sector: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioView:
    portfolio_value: float
    invested_amount: float
    pnl: float
    daily_pnl: float | None
    allocation: dict[str, float]
    holdings: list[HoldingView]
    statuses: list[ProviderStatus]
    raw: dict = field(default_factory=dict)

