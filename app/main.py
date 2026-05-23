from fastapi import FastAPI, Request

from app.api.routes import router
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(
    title="Personal AI Telegram Investment Assistant",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.include_router(router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "stockbot"}


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response

