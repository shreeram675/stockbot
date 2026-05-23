import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings


def retry_policy():
    settings = get_settings()
    return retry(
        reraise=True,
        stop=stop_after_attempt(settings.http_retry_attempts),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    )


def async_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(timeout=settings.http_timeout_seconds)

