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
3. Request API-key access if needed.
4. Create API key and API secret.
5. Configure Dhan URLs:

```text
Redirect URL: https://stockbot-rho.vercel.app/api/dhan/callback
Postback URL: https://stockbot-rho.vercel.app/api/dhan/postback
```

6. Set:

```text
DHAN_CLIENT_ID=
DHAN_API_KEY=
DHAN_API_SECRET=
DHAN_API_BASE_URL=https://api.dhan.co
DHAN_AUTH_BASE_URL=https://auth.dhan.co
DHAN_REDIRECT_URL=https://stockbot-rho.vercel.app/api/dhan/callback
DHAN_POSTBACK_URL=https://stockbot-rho.vercel.app/api/dhan/postback
```

7. After deployment, start auth:

```text
https://stockbot-rho.vercel.app/api/dhan/auth/start
```

The app supports `DHAN_ACCESS_TOKEN` as a fallback, but production should use API-key consent auth because manual tokens expire.

The implementation uses documented Dhan v2 endpoints:

- `GET /v2/holdings`
- `GET /v2/positions`
- `POST /app/generate-consent`
- `GET /app/consumeApp-consent`
- `POST /api/dhan/postback`

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
6. Sync Telegram's command menu:

```bash
curl -X POST https://stockbot-rho.vercel.app/api/telegram/commands/sync \
  -H "Authorization: Bearer <CRON_SECRET>"
```

## 7. GitHub Secrets

If CI later needs deployment or database migration automation, add only the required secrets. The current CI runs tests, linting, and type checks and does not need production secrets.

## 8. Monthly Defaults

Configured defaults:

- Timezone: `Asia/Kolkata`
- Budget: `Rs. 5,000`
- Workflow date: `12th`
- Risk profile: `Balanced`
