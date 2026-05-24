import httpx

from app.core.config import get_settings
from app.core.errors import ExternalServiceError, MissingConfigurationError
from app.services.http import async_client


class DhanService:
    def __init__(self, access_token: str | None = None) -> None:
        self.settings = get_settings()
        self.access_token = access_token

    def _headers(self) -> dict[str, str]:
        token = self.access_token or self.settings.dhan_access_token
        if not token:
            raise MissingConfigurationError("DHAN_ACCESS_TOKEN")
        return {"Content-Type": "application/json", "access-token": token}

    def _error_message(self, response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            body = response.text[:500]
        return f"HTTP {response.status_code}: {body}"

    def _is_no_holdings_response(self, response: httpx.Response) -> bool:
        try:
            body = response.json()
        except ValueError:
            return False
        return (
            isinstance(body, dict)
            and body.get("errorCode") == "DH-1111"
            and str(body.get("errorMessage", "")).lower() == "no holdings available"
        )

    async def get_holdings(self) -> list[dict]:
        url = f"{self.settings.dhan_api_base_url.rstrip('/')}/v2/holdings"
        try:
            async with async_client() as client:
                response = await client.get(url, headers=self._headers())
                if self._is_no_holdings_response(response):
                    return []
                if response.is_error:
                    raise ExternalServiceError("Dhan", f"holdings request failed: {self._error_message(response)}")
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
                if response.is_error:
                    raise ExternalServiceError("Dhan", f"positions request failed: {self._error_message(response)}")
                data = response.json()
        except MissingConfigurationError:
            raise
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Dhan", f"positions request failed: {exc}") from exc
        if not isinstance(data, list):
            raise ExternalServiceError("Dhan", "positions response was not a list")
        return data
