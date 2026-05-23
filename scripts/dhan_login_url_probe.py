import json
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings


def redact_headers(headers: httpx.Headers) -> dict[str, str]:
    interesting = ["location", "content-type", "server", "set-cookie"]
    result = {}
    for key in interesting:
        value = headers.get(key)
        if value:
            result[key] = "<present>" if key == "set-cookie" else value[:500]
    return result


def fetch(client: httpx.Client, url: str) -> None:
    print(f"candidate_url={url}")
    for follow in (False, True):
        response = client.get(url, follow_redirects=follow)
        print(
            json.dumps(
                {
                    "follow_redirects": follow,
                    "status_code": response.status_code,
                    "final_url": str(response.url),
                    "headers": redact_headers(response.headers),
                    "body_prefix": response.text[:500].replace("\n", " "),
                    "history": [
                        {"status_code": item.status_code, "url": str(item.url)}
                        for item in response.history
                    ],
                },
                indent=2,
            )
        )


def main() -> None:
    settings = get_settings()
    generate_url = (
        f"{settings.dhan_auth_base_url.rstrip('/')}/app/generate-consent"
        f"?client_id={quote(settings.dhan_client_id or '')}"
    )
    headers = {
        "app_id": settings.dhan_api_key or "",
        "app_secret": settings.dhan_api_secret or "",
    }
    with httpx.Client(timeout=settings.http_timeout_seconds) as client:
        response = client.post(generate_url, headers=headers)
        print("generate_consent_status=", response.status_code)
        print("generate_consent_body=", response.text)
        data = response.json()
        consent_app_id = data.get("consentAppId")
        print("consentAppId=", consent_app_id)
        if not consent_app_id:
            raise SystemExit("No consentAppId returned")
        url_a = f"{settings.dhan_auth_base_url.rstrip('/')}/app/login?consentAppId={quote(consent_app_id)}"
        url_b = (
            f"{settings.dhan_auth_base_url.rstrip('/')}/login/consentApp-login"
            f"?consentAppId={quote(consent_app_id)}"
        )
        print("constructed_login_url_source=app/services/dhan_auth.py uses /app/login")
        print("constructed_login_url=", url_a)
        print("docs_reference_a=dhan-ts authentication docs show /app/login")
        print("docs_reference_b=Postman DhanHQ API v2 collection shows /login/consentApp-login")
        print("--- candidate A ---")
        fetch(client, url_a)
        print("--- candidate B ---")
        fetch(client, url_b)


if __name__ == "__main__":
    main()

