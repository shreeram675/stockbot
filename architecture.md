# Architecture

## Runtime

Vercel hosts a Python FastAPI app through `api/index.py`. Telegram calls `/api/telegram/webhook`. Vercel Cron calls `/api/cron/*` routes.

The app is request-driven. It does not use Telegram polling or a resident worker.

## Layers

- `app/api`: FastAPI HTTP routes.
- `app/telegram`: Telegram command handlers and message formatters.
- `app/services`: Dhan, market data, Finnhub news, Gemini, portfolio analytics, reports, recommendations.
- `app/repositories`: SQLAlchemy persistence boundary.
- `app/db`: database session and models.
- `migrations`: Alembic migrations.
- `tests`: unit tests for critical pure logic and formatting.

## Data Flow

1. Telegram sends an update to `/api/telegram/webhook`.
2. The webhook validates Telegram secret token when configured.
3. The command handler rejects unauthorized Telegram users.
4. Portfolio commands fetch Dhan holdings and positions.
5. Market data enrichment uses yfinance.
6. Snapshots and recommendations are persisted to Supabase Postgres.
7. Gemini receives only grounded JSON context.
8. Telegram response is formatted for readability and includes degradation notes.

## External Providers

- Dhan: holdings and positions.
- yfinance: market price enrichment and basic index/asset quotes.
- Finnhub: general market news only.
- Gemini: commentary, natural language answers, recommendations.
- Supabase: managed PostgreSQL.
- Telegram: user interaction only.

## Known Design Constraints

- Vercel Hobby is serverless, so no long-running processes.
- Cron schedules in `vercel.json` are UTC. The configured schedules approximate India-market timing.
- yfinance is unofficial; failures are expected and surfaced.
- Finnhub general news is not guaranteed to be India-specific on free tier.
- Sector exposure is computed only when sector data is actually available.

