API Specification

Overview
- FastAPI service providing search over ClickHouse with per-user credit enforcement.
- Admin helpers for local/demo use, protected by a static header.

Auth
- User auth header: `x-api-key: <user-api-key>`
- Admin auth header: `x-admin-secret: <secret>` (default `local-admin`, configurable via `ADMIN_SECRET` env var)
 - Rate limiting: per API key, fixed-window RPM (`RATE_LIMIT_RPM`, default 60). Exceeding the limit returns `429`.

OpenAPI (Summary)
- Base: `http://localhost:8000`
- Endpoints:
  - `GET /health` → `{ ok, postgres, redis, clickhouse }`
  - `POST /admin/topup` → body `{ user_id: int, amount: int }` → `{ ok, user_id, added, balance }`
  - `POST /admin/sync-credits` → `{ ok, updated }`
  - `GET /search` → query supports:
    - `q` (string, optional)
    - `title` (string, optional)
    - `country` (string, optional)
    - `email_domain` (string, optional, e.g. `gmail.com`)
    - `score_min` (int, optional)
    - `score_max` (int, optional)
    - `page` (int, default 1)
    - `limit` (int, default 50; clamped by `MAX_ITEMS`)
    → Response `{ results: [...], count, total_records, page, limit, credits_used, exec_ms }`
  - `GET /download` → same filter parameters as `/search` except `page` (CSV export does not paginate), `limit` clamped by `MAX_ITEMS` → `text/csv` streaming with header `Content-Disposition: attachment; filename="download.csv"`
  - `GET /person/{person_id}` → path `{ person_id }` exact match on `id` (`Nullable(String)`), returns `{ record: {...}, exec_ms }`

Curl Examples
- Health:
  - `curl -s http://localhost:8000/health | jq .`
- Seed demo key (one-time; Postgres):
  - `docker compose exec postgres psql -U admin -d credits_db -c "INSERT INTO users (email, api_key, is_active) VALUES ('demo@example.com', 'demo-key', true) ON CONFLICT DO NOTHING;"`
- Admin topup (requires admin secret header):
  - `curl -s -X POST http://localhost:8000/admin/topup -H 'x-admin-secret: local-admin' -H 'Content-Type: application/json' -d '{"user_id": 3, "amount": 10}' | jq .`
- Search (consumes 1 credit):
  - `curl -s -H 'x-api-key: demo-key' "http://localhost:8000/search?q=Acme&limit=5&page=1" | jq .`
  - Filter examples:
    - `curl -s -H 'x-api-key: demo-key' "http://localhost:8000/search?title=Engineer&country=United%20States&limit=10" | jq .`
    - `curl -s -H 'x-api-key: demo-key' "http://localhost:8000/search?email_domain=gmail.com&score_min=10&limit=20" | jq .`
- Get person by ID (consumes 1 credit, case-sensitive exact match):
  - `curl -s -H 'x-api-key: demo-key' "http://localhost:8000/person/54a4f3f67468693b8cd7b470" | jq .`
- CSV download (consumes 1 credit):
  - `curl -s -H 'x-api-key: demo-key' "http://localhost:8000/download?q=Acme&limit=5" > download.csv`
  - Inspect: `head -n 5 download.csv`
- Admin sync (requires admin secret header):
  - `curl -s -X POST http://localhost:8000/admin/sync-credits -H 'x-admin-secret: local-admin' | jq .`

Responses (Examples)
- Health:
  - `{ "ok": true, "postgres": true, "redis": true, "clickhouse": true }`
- Topup:
  - `{ "ok": true, "user_id": 3, "added": 10, "balance": 10 }`
- Search:
  - `{ "results": [{"id": "...", "person_name": "...", "person_title": "...", "person_email": "...", "score": 1}], "count": 1, "total_records": 3421, "page": 1, "limit": 50, "credits_used": 1, "exec_ms": 12 }`
- Person:
  - `{ "record": { "id": "54a4f3f67468693b8cd7b470", "person_name": "Joe Kracmer", "person_title": "Oracle Developer", "person_email": "joe.kracmer@interpublic.com", "score": "1", /* ... */ }, "exec_ms": 72 }`
- Download (first lines):
  - `id,person_name,person_title,person_email,score`\n
  - `<id>,<name>,<title>,<email>,<score>`
- Sync credits:
  - `{ "ok": true, "updated": 2 }`

Errors
- Missing API key: `401 { "detail": "Missing API key" }`
- Invalid API key: `401 { "detail": "Invalid API key" }`
- Insufficient credits: `402 { "detail": "Insufficient credits" }`
- Admin secret missing/invalid: `403 { "detail": "Forbidden" }`
 - Rate limit exceeded: `429 { "detail": "Too many requests" }`
- Bad request (e.g., missing `q`): `400 { "detail": "..." }`
- Server error: `500 { "detail": "Internal server error" }`

Notes
- Admin endpoints are intended for local/demo use; set `ADMIN_SECRET` for safety.
- Credits are enforced via Redis-first; Postgres mirrors are kept in sync via manual or optional background sync.
 - Rate limiting is implemented via Redis fixed-window counters keyed by API key; configure `RATE_LIMIT_RPM`.
 - Maximum items per request are enforced by `MAX_ITEMS` (default 500).