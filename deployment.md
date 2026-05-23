# Deployment

## 1. Prepare Supabase

Create a Supabase project and copy the Postgres connection string. Use a SQLAlchemy-compatible URL:

```text
postgresql+psycopg://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
```

Run migrations:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## 2. Configure Vercel

Connect the GitHub repository to Vercel.

Set environment variables from `.env.example` in Vercel Project Settings.

Required production variables:

- `APP_ENV=production`
- `DATABASE_URL`
- `TELEGRAM_ALLOWED_USER_ID`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_WEBHOOK_URL`
- `DHAN_ACCESS_TOKEN`
- `GEMINI_API_KEY`
- `FINNHUB_API_KEY`
- `CRON_SECRET`

Optional but recommended:

- `DHAN_CLIENT_ID`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## 3. Deploy

Push to GitHub and deploy through Vercel.

## 4. Register Telegram Webhook

After deployment, register:

```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<your-vercel-domain>/api/telegram/webhook&secret_token=<TELEGRAM_WEBHOOK_SECRET>
```

Do not paste real tokens into shared logs.

## 5. Cron Jobs

`vercel.json` defines:

- Daily morning report: weekdays, 03:00 UTC.
- Daily close report: weekdays, 11:00 UTC.
- Weekly report: Saturday, 03:30 UTC.
- Monthly workflow: 12th of every month, 03:30 UTC.

Cron endpoints require `Authorization: Bearer <CRON_SECRET>` when `CRON_SECRET` is configured.

