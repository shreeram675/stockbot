from datetime import UTC, datetime

import httpx
import yfinance as yf

from app.core.config import get_settings
from app.core.errors import ExternalServiceError, MissingConfigurationError
from app.services.http import async_client


class MarketDataService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def yahoo_symbol(self, symbol: str) -> str:
        clean = symbol.strip().upper()
        if clean.startswith("^") or clean.endswith((".NS", ".BO")) or "=" in clean:
            return clean
        return f"{clean}.NS"

    async def quote(self, symbol: str) -> dict:
        yahoo_symbol = self.yahoo_symbol(symbol)
        try:
            price, previous_close, source = await self._quote_from_yahoo_chart(yahoo_symbol)
        except Exception:
            try:
                price, previous_close, source = await self._to_thread(
                    lambda: (*self._quote_from_history(yahoo_symbol), "yfinance")
                )
            except Exception as exc:
                raise ExternalServiceError("yfinance", f"quote unavailable for {symbol}: {exc}") from exc
        try:
            if price <= 0:
                raise ValueError("missing current price")
            return {
                "symbol": symbol,
                "price": price,
                "previous_close": previous_close or None,
                "change": price - previous_close if previous_close else None,
                "change_percent": ((price - previous_close) / previous_close * 100)
                if previous_close
                else None,
                "source": source,
            }
        except Exception as exc:
            raise ExternalServiceError("yfinance", f"quote unavailable for {symbol}: {exc}") from exc

    def _quote_from_history(self, yahoo_symbol: str) -> tuple[float, float]:
        history = yf.download(
            yahoo_symbol,
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if history.empty:
            raise ValueError("empty price history")
        close = history["Close"].dropna()
        if close.empty:
            raise ValueError("missing close prices")
        price = float(close.iloc[-1])
        previous_close = float(close.iloc[-2]) if len(close) > 1 else 0.0
        return price, previous_close

    async def _quote_from_yahoo_chart(self, yahoo_symbol: str) -> tuple[float, float, str]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
        params = {"range": "5d", "interval": "1d"}
        headers = {"User-Agent": "Mozilla/5.0"}
        async with async_client() as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        result = data.get("chart", {}).get("result")
        if not isinstance(result, list) or not result:
            raise ValueError("empty Yahoo chart result")
        item = result[0]
        meta = item.get("meta", {})
        price = meta.get("regularMarketPrice")
        previous_close = meta.get("chartPreviousClose") or meta.get("previousClose") or 0.0
        if not price:
            quote = item.get("indicators", {}).get("quote", [{}])[0]
            closes = [value for value in quote.get("close", []) if value is not None]
            if not closes:
                raise ValueError("missing chart close prices")
            price = closes[-1]
            previous_close = closes[-2] if len(closes) > 1 else previous_close
        return float(price), float(previous_close or 0.0), "yfinance-yahoo-chart"

    async def sector(self, symbol: str) -> str | None:
        ticker = yf.Ticker(self.yahoo_symbol(symbol))
        try:
            info = await self._to_thread(lambda: ticker.info)
            sector = info.get("sector")
            return str(sector) if sector else None
        except Exception:
            return None

    async def market_overview(self) -> tuple[dict, list[str]]:
        symbols = {"NIFTY 50": "^NSEI", "Gold": "GC=F", "USDINR": "INR=X", "S&P 500": "^GSPC"}
        overview: dict[str, dict] = {}
        warnings: list[str] = []
        for label, symbol in symbols.items():
            try:
                overview[label] = await self.quote(symbol)
            except ExternalServiceError as exc:
                warnings.append(exc.message)
        return overview, warnings

    async def finnhub_market_news(self) -> list[dict]:
        if not self.settings.finnhub_api_key:
            raise MissingConfigurationError("FINNHUB_API_KEY")
        url = "https://finnhub.io/api/v1/news"
        params = {"category": "general"}
        headers = {"X-Finnhub-Token": self.settings.finnhub_api_key}
        try:
            async with async_client() as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Finnhub", f"market news request failed: {exc}") from exc
        if not isinstance(data, list):
            raise ExternalServiceError("Finnhub", "market news response was not a list")
        return data[:5]

    async def _to_thread(self, func):
        import asyncio

        return await asyncio.to_thread(func)


def today_iso() -> str:
    return datetime.now(UTC).date().isoformat()
