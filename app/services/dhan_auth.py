import base64
import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import quote

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ExternalServiceError, MissingConfigurationError
from app.db.models import DhanAuthToken
from app.services.http import async_client


def jwt_expiry(token: str) -> datetime | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:
        return None
    exp = data.get("exp")
    if not isinstance(exp, int | float):
        return None
    return datetime.fromtimestamp(exp, UTC)


class DhanTokenCipher:
    def __init__(self) -> None:
        settings = get_settings()
        secret = settings.dhan_api_secret
        if not secret:
            raise MissingConfigurationError("DHAN_API_SECRET")
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        self.fernet = Fernet(key)

    def encrypt(self, token: str) -> str:
        return self.fernet.encrypt(token.encode()).decode()

    def decrypt(self, encrypted_token: str) -> str:
        try:
            return self.fernet.decrypt(encrypted_token.encode()).decode()
        except InvalidToken as exc:
            raise ExternalServiceError("Dhan", "stored access token could not be decrypted") from exc


class DhanAuthService:
    def __init__(self, db: Session | None = None) -> None:
        self.settings = get_settings()
        self.db = db

    def _require_api_credentials(self) -> tuple[str, str, str]:
        if not self.settings.dhan_client_id:
            raise MissingConfigurationError("DHAN_CLIENT_ID")
        if not self.settings.dhan_api_key:
            raise MissingConfigurationError("DHAN_API_KEY")
        if not self.settings.dhan_api_secret:
            raise MissingConfigurationError("DHAN_API_SECRET")
        return self.settings.dhan_client_id, self.settings.dhan_api_key, self.settings.dhan_api_secret

    async def generate_consent(self) -> dict:
        client_id, api_key, api_secret = self._require_api_credentials()
        url = f"{self.settings.dhan_auth_base_url.rstrip('/')}/app/generate-consent"
        try:
            async with async_client() as client:
                response = await client.post(
                    url,
                    params={"client_id": client_id},
                    headers={"app_id": api_key, "app_secret": api_secret},
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Dhan", f"generate consent request failed: {exc}") from exc
        data = self._json_or_error(response, "generate consent")
        consent_id = data.get("consentAppId") or data.get("consentId") or data.get("id")
        if not consent_id:
            raise ExternalServiceError("Dhan", f"generate consent returned no consent id: {data}")
        login_url = (
            f"{self.settings.dhan_auth_base_url.rstrip('/')}/login/consentApp-login"
            f"?consentAppId={quote(str(consent_id))}"
        )
        return {"consent_id": str(consent_id), "login_url": login_url, "raw": data}

    async def consume_consent(self, token_id: str) -> dict:
        _, api_key, api_secret = self._require_api_credentials()
        url = f"{self.settings.dhan_auth_base_url.rstrip('/')}/app/consumeApp-consent"
        try:
            async with async_client() as client:
                response = await client.get(
                    url,
                    params={"tokenId": token_id},
                    headers={"app_id": api_key, "app_secret": api_secret},
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Dhan", f"consume consent request failed: {exc}") from exc
        data = self._json_or_error(response, "consume consent")
        access_token = data.get("accessToken") or data.get("access_token") or data.get("token")
        if not access_token:
            raise ExternalServiceError("Dhan", f"consume consent returned no access token: {data}")
        if self.db is not None:
            self.persist_access_token(str(access_token))
        return {"access_token": str(access_token), "token_expiry": jwt_expiry(str(access_token)), "raw": data}

    def persist_access_token(self, access_token: str, user_id: str | None = None) -> DhanAuthToken:
        if self.db is None:
            raise MissingConfigurationError("DATABASE_URL")
        encrypted = DhanTokenCipher().encrypt(access_token)
        token = DhanAuthToken(
            user_id=user_id,
            client_id=self.settings.dhan_client_id,
            encrypted_access_token=encrypted,
            token_expiry=jwt_expiry(access_token),
            token_source="api_key_consent",
        )
        self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token

    def latest_access_token(self) -> str | None:
        if self.settings.dhan_access_token:
            return self.settings.dhan_access_token
        if self.db is None:
            return None
        row = self.db.scalar(
            select(DhanAuthToken)
            .where(DhanAuthToken.client_id == self.settings.dhan_client_id)
            .order_by(DhanAuthToken.created_at.desc())
        )
        if row is None:
            return None
        if row.token_expiry and row.token_expiry <= datetime.now(UTC):
            raise ExternalServiceError(
                "Dhan",
                "stored API-key access token is expired; visit /api/dhan/auth/start to reconnect",
            )
        return DhanTokenCipher().decrypt(row.encrypted_access_token)

    def _json_or_error(self, response: httpx.Response, action: str) -> dict:
        try:
            data = response.json()
        except ValueError as exc:
            raise ExternalServiceError("Dhan", f"{action} returned non-JSON HTTP {response.status_code}") from exc
        if response.is_error:
            raise ExternalServiceError("Dhan", f"{action} failed HTTP {response.status_code}: {data}")
        if not isinstance(data, dict):
            raise ExternalServiceError("Dhan", f"{action} returned unexpected payload: {data}")
        return data
