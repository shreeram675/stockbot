import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings


def fingerprint(value: str | None) -> str:
    if not value:
        return "missing"
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def masked(value: str | None) -> str:
    if not value:
        return "missing"
    if len(value) <= 8:
        return f"len={len(value)} sha256={fingerprint(value)}"
    return f"{value[:4]}...{value[-4:]} len={len(value)} sha256={fingerprint(value)}"


def printable_response(response: httpx.Response) -> str:
    text = response.text
    try:
        data = response.json()
    except ValueError:
        return text
    if response.is_success:
        data = redact_token_fields(data)
    return json.dumps(data, indent=2, ensure_ascii=False)


def redact_token_fields(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if key.lower() in {"accesstoken", "access_token", "token", "jwttoken", "jwt_token"}:
                redacted[key] = masked(str(item)) if item is not None else item
            else:
                redacted[key] = redact_token_fields(item)
        return redacted
    if isinstance(value, list):
        return [redact_token_fields(item) for item in value]
    return value


@dataclass(frozen=True)
class Case:
    name: str
    token_id: str
    include_client_id_header: bool = False
    token_as_raw_query: bool = False


def build_headers(include_client_id_header: bool) -> dict[str, str]:
    settings = get_settings()
    headers = {
        "app_id": settings.dhan_api_key or "",
        "app_secret": settings.dhan_api_secret or "",
    }
    if include_client_id_header and settings.dhan_client_id:
        headers["client_id"] = settings.dhan_client_id
    return headers


def print_request(case: Case, url: str, headers: dict[str, str]) -> None:
    redacted_headers = {
        name: masked(value)
        for name, value in headers.items()
    }
    print(f"\n=== {case.name} ===")
    print(f"request_url={url}")
    print("method=GET")
    print(f"token_id_present={bool(case.token_id)}")
    print(f"token_id_length={len(case.token_id)}")
    print(f"token_id_sha256={fingerprint(case.token_id)}")
    print(f"headers={json.dumps(redacted_headers, indent=2)}")


def run_case(case: Case) -> httpx.Response:
    settings = get_settings()
    base_url = settings.dhan_auth_base_url.rstrip("/")
    headers = build_headers(case.include_client_id_header)
    if case.token_as_raw_query:
        url = f"{base_url}/app/consumeApp-consent?tokenId={case.token_id}"
    else:
        url = f"{base_url}/app/consumeApp-consent?tokenId={quote(case.token_id, safe='')}"
    print_request(case, url, headers)
    with httpx.Client(timeout=settings.http_timeout_seconds, follow_redirects=False) as client:
        response = client.get(url, headers=headers)
    print(f"status={response.status_code}")
    print("response_headers=" + json.dumps(dict(response.headers), indent=2))
    print("raw_response_text:")
    print(printable_response(response))
    return response


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep debug Dhan consume-consent locally.")
    parser.add_argument("token_id", help="Real tokenId from Dhan callback. It will not be printed in full.")
    parser.add_argument(
        "--repeat-after-success",
        action="store_true",
        help="If the first request succeeds, repeat it to check whether tokenId is single-use.",
    )
    args = parser.parse_args()

    settings = get_settings()
    print("env:")
    print(f"DHAN_API_KEY={masked(settings.dhan_api_key)}")
    print(f"DHAN_API_SECRET={masked(settings.dhan_api_secret)}")
    print(f"DHAN_CLIENT_ID={masked(settings.dhan_client_id)}")
    print(f"DHAN_AUTH_BASE_URL={settings.dhan_auth_base_url}")

    raw_token = args.token_id
    stripped_token = raw_token.strip()
    decoded_token = unquote(stripped_token)

    print("\ntoken_format_comparison:")
    print(f"raw_length={len(raw_token)} sha256={fingerprint(raw_token)}")
    print(f"stripped_length={len(stripped_token)} sha256={fingerprint(stripped_token)}")
    print(f"url_decoded_length={len(decoded_token)} sha256={fingerprint(decoded_token)}")
    print(f"raw_equals_stripped={raw_token == stripped_token}")
    print(f"stripped_equals_url_decoded={stripped_token == decoded_token}")

    primary = run_case(Case("A headers_only_stripped_token_urlencoded", stripped_token))

    if primary.is_success:
        if args.repeat_after_success:
            run_case(Case("D repeat_same_token_after_success", stripped_token))
        print("\nresult_hint=primary Dhan-documented request succeeded; tokenId and credentials are accepted.")
        return 0

    run_case(Case("B headers_plus_client_id_header", stripped_token, include_client_id_header=True))

    if raw_token != stripped_token:
        run_case(Case("C1 raw_token_preserving_outer_whitespace", raw_token))
    if decoded_token != stripped_token:
        run_case(Case("C2 url_decoded_token", decoded_token))
    run_case(Case("C3 stripped_token_without_url_encoding", stripped_token, token_as_raw_query=True))

    print(
        "\nresult_hint=primary request failed; compare statuses and bodies above to separate "
        "credential rejection from tokenId or request-format rejection."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
