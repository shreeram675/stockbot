# Manual Setup Steps

These steps must be completed with real credentials. The app does not invent or mock them.

## 1. Telegram BotFather

1. Open Telegram.
2. Message `@BotFather`.
3. Create a bot with `/newbot`.
4. Copy the bot token into `TELEGRAM_BOT_TOKEN`.
5. Generate a random webhook secret and set `TELEGRAM_WEBHOOK_SECRET`.
6. Get your numeric Telegram user ID and set `TELEGRAM_ALLOWED_USER_ID`.

## 2. Supabase

1. Create a Supabase project.
2. Copy the PostgreSQL connection string.
3. Convert it to SQLAlchemy format if needed:

```text
postgresql+psycopg://...
```

4. Set `DATABASE_URL`.
5. Run:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## 3. Dhan

1. Log in to Dhan Web.
2. Go to Profile / DhanHQ Trading APIs.
3. Request access if needed.
4. Generate access token.
5. Set:

```text
DHAN_CLIENT_ID=
DHAN_ACCESS_TOKEN=
DHAN_API_BASE_URL=https://api.dhan.co
```

The implementation uses documented Dhan v2 endpoints:

- `GET /v2/holdings`
- `GET /v2/positions`

## 4. Gemini

1. Create or open a Google AI Studio project.
2. Enable Gemini API access.
3. Create an API key.
4. Set:

```text
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
```

If Gemini is not configured, `/ask`, `/suggest`, `/why`, and AI commentary report AI unavailability.

## 5. Finnhub

1. Create a Finnhub account.
2. Generate API key.
3. Set:

```text
NEWS_PROVIDER=finnhub
FINNHUB_API_KEY=
```

NewsAPI is intentionally unsupported.

## 6. Vercel

1. Connect GitHub repo `shreeram675/stockbot`.
2. Set all production environment variables.
3. Deploy.
4. Copy the deployment URL into `TELEGRAM_WEBHOOK_URL`.
5. Register the Telegram webhook.

## 7. GitHub Secrets

If CI later needs deployment or database migration automation, add only the required secrets. The current CI runs tests, linting, and type checks and does not need production secrets.

## 8. Monthly Defaults

Configured defaults:

- Timezone: `Asia/Kolkata`
- Budget: `Rs. 5,000`
- Workflow date: `12th`
- Risk profile: `Balanced`

