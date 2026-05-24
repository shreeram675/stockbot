# Personal AI Telegram Investment Assistant

Production-structured FastAPI backend for a single-user Telegram investment assistant focused on Indian market portfolio tracking through Dhan.

The assistant runs in Telegram only. There is no dashboard and no frontend.

## What It Does

- Accepts Telegram webhook updates.
- Rejects every Telegram user except `TELEGRAM_ALLOWED_USER_ID`.
- Fetches Dhan holdings and positions.
- Supports Dhan API-key consent authentication with encrypted token persistence.
- Enriches holdings with `yfinance` market data where available.
- Stores portfolio snapshots in Supabase PostgreSQL through SQLAlchemy.
- Generates portfolio reports, health scoring, and Gemini-grounded analysis.
- Sends scheduled reports from Vercel Cron routes.
- Uses Finnhub only for news. NewsAPI is intentionally not supported.

## Important Transparency

This is software, not registered investment advice.

The bot does not fabricate missing broker data, prices, sectors, news, or AI output. If Dhan, yfinance, Finnhub, Gemini, Telegram, or Supabase fails, the user-facing Telegram message should say that clearly.

## Quick Start

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Fill `.env`, then run checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app
```

## Dhan Authentication

Production Dhan auth should use the API-key consent flow, not manual 24-hour tokens.

Start the consent flow from:

```text
https://stockbot-rho.vercel.app/api/dhan/auth/start
```

Dhan redirects back to:

```text
https://stockbot-rho.vercel.app/api/dhan/callback
```

Dhan postbacks should use:

```text
https://stockbot-rho.vercel.app/api/dhan/postback
```

`DHAN_ACCESS_TOKEN` is still supported as a backward-compatible fallback.

Local API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## Telegram Commands

- `/start`
- `/help`
- `/portfolio`
- `/holdings`
- `/performance`
- `/risk`
- `/risk Balanced`
- `/model low risk`
- `/model balanced`
- `/model aggressive`
- `/health`
- `/suggest`
- `/why`
- `/ask What is my biggest concentration risk?`
- `/simulate 5000 10y`

## Docs

- [Architecture](architecture.md)
- [Deployment](deployment.md)
- [Database Schema](database_schema.md)
- [API Reference](api_reference.md)
- [Manual Steps](manual_steps.md)
- [Troubleshooting](troubleshooting.md)
