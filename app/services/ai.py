from google import genai

from app.core.config import get_settings
from app.core.errors import ExternalServiceError, MissingConfigurationError


class AIService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def available(self) -> bool:
        return bool(self.settings.gemini_api_key)

    async def generate(self, prompt: str) -> str:
        if not self.settings.gemini_api_key:
            raise MissingConfigurationError("GEMINI_API_KEY")
        try:
            client = genai.Client(api_key=self.settings.gemini_api_key)
            response = await self._to_thread(
                lambda: client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=prompt,
                )
            )
            text = getattr(response, "text", None)
        except Exception as exc:
            raise ExternalServiceError("Gemini", f"AI model unavailable: {exc}") from exc
        if not text:
            raise ExternalServiceError("Gemini", "AI model returned an empty response")
        return str(text).strip()

    async def _to_thread(self, func):
        import asyncio

        return await asyncio.to_thread(func)

