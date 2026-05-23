# Troubleshooting

## Bot Replies `Unauthorized user`

Check `TELEGRAM_ALLOWED_USER_ID`. It must be your numeric Telegram user ID, not username.

## Telegram Webhook Returns 403

Check `TELEGRAM_WEBHOOK_SECRET` and the `secret_token` used when registering the webhook.

## `/portfolio` Says Dhan Is Unavailable

Check:

- `DHAN_API_KEY`
- `DHAN_API_SECRET`
- Dhan consent flow completed at `/api/dhan/auth/start`
- fallback `DHAN_ACCESS_TOKEN`, if using manual token mode
- Dhan API access is enabled.
- Dhan token has not expired.
- Dhan holdings/positions endpoints are reachable.

The app does not create fake portfolio data when Dhan fails.

## Dhan DH-906 Invalid Token

The supplied Dhan token is not accepted by Dhan. If using API-key mode, restart the consent flow:

```text
https://stockbot-rho.vercel.app/api/dhan/auth/start
```

If using manual fallback mode, generate a fresh token in Dhan Web and update `DHAN_ACCESS_TOKEN`.

## AI Model Unavailable

Check:

- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- Gemini quota/free-tier availability

The app will not fabricate AI analysis.

## Finnhub News Unavailable

Check:

- `FINNHUB_API_KEY`
- Finnhub rate limits
- Provider outage

Recommendations can still proceed only if Gemini and portfolio context are available, but the message records news unavailability.

## yfinance Price Missing

yfinance is unofficial. Some symbols may require `.NS` or `.BO` suffixes. The app defaults plain symbols to `.NS`.

## Vercel Cron Not Sending Reports

Check:

- Vercel deployment is active.
- Cron jobs appear in Vercel dashboard.
- `CRON_SECRET` matches authorization.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USER_ID` are set.

## Alembic Cannot Connect

Check `DATABASE_URL`. Supabase passwords with special characters may need URL encoding.
