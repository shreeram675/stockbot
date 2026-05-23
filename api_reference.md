# API Reference

## `GET /`

Basic service status.

## `GET /api/health`

Returns:

```json
{
  "status": "ok"
}
```

## `POST /api/telegram/webhook`

Telegram webhook endpoint.

Security:

- Validates `X-Telegram-Bot-Api-Secret-Token` when `TELEGRAM_WEBHOOK_SECRET` is configured.
- Telegram command handlers also enforce `TELEGRAM_ALLOWED_USER_ID`.

## `GET /api/cron/daily-morning`

Sends daily morning market report to the authorized Telegram user.

## `GET /api/cron/daily-close`

Fetches portfolio snapshot and sends market-close report.

## `GET /api/cron/weekly`

Sends weekly portfolio report from persisted snapshots.

## `GET /api/cron/monthly`

Runs monthly investment workflow using configured risk profile and budget.

## Cron Auth

When `CRON_SECRET` is set, cron routes require:

```text
Authorization: Bearer <CRON_SECRET>
```

