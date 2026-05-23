# Database Schema

Managed by SQLAlchemy models and Alembic migration:

```text
migrations/versions/20260523_0001_initial_schema.py
```

## Tables

### users

Stores the single authorized Telegram user record.

Columns:

- `id`
- `telegram_user_id`
- `display_name`
- `created_at`
- `updated_at`

### risk_preferences

Stores risk preference history.

Modes:

- Conservative
- Balanced
- Aggressive
- Custom

### portfolio_snapshots

Stores historical portfolio state:

- portfolio value
- invested amount
- P&L
- daily P&L
- allocation JSON
- raw Dhan payload

### holdings

Stores holdings tied to a snapshot:

- symbol
- quantity
- average price
- market price
- market value
- gain/loss
- sector when available
- raw payload

### recommendations

Stores AI-generated recommendations with grounded context.

### system_logs

Reserved for structured operational events.

### alert_logs

Stores scheduled report delivery attempts and alert state.

## Supabase Security Note

This app connects from a trusted server using direct PostgreSQL. Do not expose the database connection string or service role key to any frontend. This project has no frontend.

