Final Writeup

Summary
- Implements a credit-enforced FastAPI over ClickHouse with Redis-first counters and Postgres durability.
- Provides CSV export, admin helpers, and a background sync option.

Key Decisions
- Redis as primary for credits to support atomic, fast decrements under load.
- Postgres mirrors credits for durability and auditing; reconciled via manual or background sync.
- Admin endpoints locked behind a static header for local/demo safety.
- Startup retry for ClickHouse to avoid crash loops during container orchestration.

Endpoints
- User: `/search` (JSON), `/download` (CSV streaming)
- Admin: `/admin/topup`, `/admin/sync-credits`
- Health: `/health`

Operational Notes
- Optional worker controlled via `ENABLE_SYNC_WORKER`, `SYNC_INTERVAL_SECONDS`.
- Admin secret configurable via `ADMIN_SECRET`.
- Simple DB seeding via `sql/init_postgres.sql` and Adminer.

Testing
- Integration test (`tests/test_search_integration.py`) seeds a demo user, tops up credits, and hits `/search`.
- Run inside the API container after rebuild: `docker compose build api && docker compose up -d && docker compose exec api pytest -q`.

Future Improvements
- Authentication for admin endpoints, granular roles.
- Rate limiting and per-endpoint credit pricing.
- Move credits entirely to Redis with write-behind for even stronger consistency at scale.