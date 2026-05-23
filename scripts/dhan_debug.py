import base64
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.services.dhan import DhanService


def redact(value: str | None) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 12:
        return f"{value[:2]}...{value[-2:]}"
    return f"{value[:6]}...{value[-6:]} len={len(value)}"


def decode_jwt_payload(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:
        return None


def show_token_diagnostics(token: str | None) -> None:
    print("token_present=", bool(token))
    print("token_redacted=", redact(token))
    if not token:
        return
    parts = token.split(".")
    print("token_dot_parts=", len(parts))
    print("token_looks_like_jwt=", len(parts) == 3 and token.startswith("eyJ"))
    payload = decode_jwt_payload(token)
    print("jwt_payload_decodable=", payload is not None)
    if not payload:
        return
    safe_keys = [key for key in ("sub", "aud", "iss", "iat", "nbf", "exp", "dhanClientId") if key in payload]
    print("jwt_safe_keys=", ",".join(safe_keys))
    exp = payload.get("exp")
    if isinstance(exp, int | float):
        expiry = datetime.fromtimestamp(exp, UTC)
        print("jwt_expiry_utc=", expiry.isoformat())
        print("jwt_expired_now=", expiry <= datetime.now(UTC))


def request(client: httpx.Client, method: str, url: str, headers: dict[str, str]) -> None:
    print(f"request_method= {method}")
    print(f"request_url= {url}")
    print("request_headers= " + json.dumps({key: redact(value) for key, value in headers.items()}))
    response = client.request(method, url, headers=headers)
    print("response_status=", response.status_code)
    try:
        print("response_body=", json.dumps(response.json())[:1200])
    except ValueError:
        print("response_body=", response.text[:1200])


def main() -> None:
    settings = get_settings()
    print("dhan_base_url=", settings.dhan_api_base_url)
    print("client_id_present=", bool(settings.dhan_client_id))
    print("client_id_redacted=", redact(settings.dhan_client_id))
    show_token_diagnostics(settings.dhan_access_token)
    service = DhanService()
    headers = service._headers()
    with httpx.Client(timeout=settings.http_timeout_seconds) as client:
        request(client, "GET", f"{settings.dhan_api_base_url.rstrip('/')}/v2/profile", headers)
        request(client, "GET", f"{settings.dhan_api_base_url.rstrip('/')}/v2/holdings", headers)
        request(client, "GET", f"{settings.dhan_api_base_url.rstrip('/')}/v2/positions", headers)
        renew_headers = {
            "access-token": settings.dhan_access_token or "",
            "dhanClientId": settings.dhan_client_id or "",
        }
        request(client, "GET", f"{settings.dhan_api_base_url.rstrip('/')}/v2/RenewToken", renew_headers)


if __name__ == "__main__":
    main()

