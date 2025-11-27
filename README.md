Project: Credit-Based Search API (FastAPI, ClickHouse, Postgres, Redis)

This project implements a credit‑metered search API backed by FastAPI, ClickHouse, Redis, and Postgres. User endpoints (search, person lookup, CSV download) consume credits that are enforced atomically via Redis Lua scripts, while Postgres provides durable storage of users and credit balances. Admin tools support credit top‑ups and reconciliation/sync operations, and ingestion utilities populate ClickHouse with processed data for querying.

Overview
- FastAPI service enforcing per-user credits for a ClickHouse-backed search endpoint.
- Redis holds the real-time credit counter; Postgres stores durable credits and users.
- Admin endpoints help you demo credit flows without manual SQL.

Why Redis-first?
- Atomic credit decrements via Redis Lua scripts prevent race conditions under concurrent load.
- Low-latency counters keep the hot path fast without frequent DB round trips.
- Strong concurrency guarantees for single-key operations; scales with bursty traffic.
- Postgres mirrors balances for durability, auditability, and reporting; periodic sync reconciles state.
- Fallback path uses Postgres when Redis is unavailable, maintaining service continuity.

Rate Limiting
- Per API key, fixed-window requests-per-minute (RPM). Configure via `RATE_LIMIT_RPM` (default `60`).
- Exceeding the limit returns `429 Too Many Requests`.
- Implemented with Redis counters; windowed keys expire automatically.
- Example: set `RATE_LIMIT_RPM: 5` in `docker-compose.yml` to demo locally.

Stack
- API: FastAPI (Python)
- Databases: Postgres (credits/users), ClickHouse (search data)
- Cache/Counter: Redis
- Orchestration: Docker Compose

Prerequisites
- Docker and Docker Compose installed
- `curl` available; `jq` is optional for pretty JSON

Getting Started
- Build and run services:
  - `docker compose up -d`
- Verify API is healthy:
  - `curl -s http://localhost:8000/health | jq .`
  - Expected: `{ "ok": true, "postgres": true, "redis": true, "clickhouse": true }`

Load ClickHouse Data (optional demo dataset)
- From the project root:
  - `bash scripts/clickhouse_load.sh`
- This loads sample processed data into ClickHouse for search demos.

Seed a Test User
- Create an active user with an API key in Postgres (one-time):
  - `docker compose exec postgres psql -U admin -d credits_db -c "INSERT INTO users (email, api_key, is_active) VALUES ('demo@example.com', 'demo-key', true) ON CONFLICT DO NOTHING;"`
- You can now use header `x-api-key: demo-key` for `/search` requests.

Admin API Endpoints (Protected by Secret Header)
- Top up credits for a user:
  - `curl -s -X POST http://localhost:8000/admin/topup -H 'x-admin-secret: local-admin' -H 'Content-Type: application/json' -d '{"user_id": 1, "amount": 10}' | jq .`
  - Response includes new balance. This updates Redis and upserts Postgres.
- Sync Redis credits back to Postgres:
  - `curl -s -X POST http://localhost:8000/admin/sync-credits -H 'x-admin-secret: local-admin' | jq .`
  - Useful after heavy Redis-only activity; ensures DB reflects current balances.

Configure Admin Secret
- Default secret is `local-admin`. To set your own:
  - In `docker-compose.yml`, under `api.environment`, add `ADMIN_SECRET=local-admin` (or your value).
  - Restart API: `docker compose restart api`
  - Use the same value in the `x-admin-secret` request header.

Using the Search Endpoint
- Example request:
  - `curl -s -H 'x-api-key: demo-key' "http://localhost:8000/search?q=Acme" | jq .`
- Each successful search decrements 1 credit (Redis-first with Postgres fallback) and mirrors the updated balance to Postgres immediately for visibility.
- When credits reach 0, the API returns a 402-like error with a helpful message.

Using the Download Endpoint
- Stream CSV for a query (consumes 1 credit):
  - `curl -s -H 'x-api-key: demo-key' "http://localhost:8000/download?q=Acme&limit=5" > download.csv`
- Inspect a few lines:
  - `head -n 5 download.csv`

Using the Person Endpoint
- Fetch a single person by exact `id` (case-sensitive, ClickHouse `Nullable(String)`):
  - `curl -s -H 'x-api-key: demo-key' "http://localhost:8000/person/54a4f3f67468693b8cd7b470" | jq .`

Background Sync Worker (Optional)
- Disabled by default; enable with environment variables in `docker-compose.yml`:
  - `ENABLE_SYNC_WORKER=true`
  - `SYNC_INTERVAL_SECONDS=60`
- On startup, a background thread periodically syncs Redis → Postgres. With immediate Postgres mirroring on deduction, this worker serves as a safety net and for reconciling any Redis-only changes.

Troubleshooting
- ClickHouse readiness: the API retries connecting ~24s at startup to avoid crash loops.
- If `health` shows a service as false, check logs:
  - `docker compose logs -f api`
- Postgres schema: created by `sql/init_postgres.sql` via the Compose init process.
- Adminer (if included) can be used to inspect DB contents.

Testing Guide
- Health check:
  - `curl -s http://localhost:8000/health | jq .`
- Top up then search:
  1) `curl -s -X POST http://localhost:8000/admin/topup -H 'x-admin-secret: local-admin' -H 'Content-Type: application/json' -d '{"user_id": 1, "amount": 5}' | jq .`
  2) `curl -s -H 'x-api-key: demo-key' "http://localhost:8000/search?q=Acme" | jq .`
  3) Confirm credits in Postgres:
     - `docker compose exec postgres psql -U admin -d credits_db -c "SELECT user_id, credits_remaining FROM credits ORDER BY user_id;"`
- Optional: run `/admin/sync-credits` to reconcile any Redis-only changes (requires `x-admin-secret`):
  - `curl -s -X POST http://localhost:8000/admin/sync-credits -H 'x-admin-secret: local-admin' | jq .`

Submission Checklist (Mandatory)
- Include the following in your hand-in:
  - `README.md` (this file)
  - `docker-compose.yml`
  - `Dockerfile`
  - `requirements.txt`
  - `src/api/app.py`
  - `sql/init_postgres.sql`
  - `scripts/clickhouse_load.sh` (if used)
- Provide evidence of a working run:
  - Health response JSON
  - A top-up response JSON
  - A search response JSON
  - Postgres `credits_remaining` query output showing changes
- Note any non-default environment variables you used.

Testing
- Run integration test (requires services running):
  - Rebuild the API image to pick up test deps: `docker compose build api`
  - Start services: `docker compose up -d`
  - Execute tests inside API container: `docker compose exec api pytest -q`
  - Expected: the test seeds a demo user, tops up credits, and exercises `/search`.

Notes
- Admin endpoints require header `x-admin-secret` (default `local-admin`).
- For production, protect admin endpoints and consider moving credits fully to Redis with a write-behind strategy.

Docs
- Detailed endpoint specs and examples:
  - `docs/api-spec.md` — endpoints, authentication, curl examples
  - `docs/sample_outputs.md` — representative responses
  - `docs/architecture.md` — mermaid diagram and data flow
  - `docs/schema.md` — Postgres, ClickHouse, and Redis schema overview