import httpx

from app.core.config import get_settings
from app.core.errors import ExternalServiceError, MissingConfigurationError
from app.services.http import async_client


class DhanService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        if not self.settings.dhan_access_token:
            raise MissingConfigurationError("DHAN_ACCESS_TOKEN")
        return {"Content-Type": "application/json", "access-token": self.settings.dhan_access_token}

    async def get_holdings(self) -> list[dict]:
        url = f"{self.settings.dhan_api_base_url.rstrip('/')}/v2/holdings"
        try:
            async with async_client() as client:
                response = await client.get(url, headers=self._headers())
                response.raise_for_status()
                data = response.json()
        except MissingConfigurationError:
            raise
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Dhan", f"holdings request failed: {exc}") from exc
        if not isinstance(data, list):
            raise ExternalServiceError("Dhan", "holdings response was not a list")
        return data

    async def get_positions(self) -> list[dict]:
        url = f"{self.settings.dhan_api_base_url.rstrip('/')}/v2/positions"
        try:
            async with async_client() as client:
                response = await client.get(url, headers=self._headers())
                response.raise_for_status()
                data = response.json()
        except MissingConfigurationError:
            raise
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Dhan", f"positions request failed: {exc}") from exc
        if not isinstance(data, list):
            raise ExternalServiceError("Dhan", "positions response was not a list")
        return data

