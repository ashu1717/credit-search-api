# Credit Management System

This document describes how authentication, rate limiting, credit assignment, credit consumption, and usage logging are implemented in the API.

## Overview

- Identity: Users are stored in Postgres (`users` table) with fields: `id`, `email`, `api_key`, `is_active`.
- Credits: Each user has a balance in Postgres (`credits` table) and a mirrored balance in Redis (`credits:{user_id}`) for fast enforcement.
- Logging: Every API call is recorded in Postgres (`api_logs`) with `endpoint`, `credits_used`, `query_params`, `execution_time_ms`, `client_ip`, and timestamps.
- Enforcement: Requests are authenticated by `x-api-key`, rate limited per minute (`RATE_LIMIT_RPM`), and deduct 1 credit per request. If credits are exhausted, the API returns `402 Insufficient credits`.

## Authentication

- Header: `x-api-key: <user-api-key>`.
- Validation: API key is looked up in Postgres, requiring `is_active = true`.
- Admin endpoints use `x-admin-secret: <secret>`; the secret is configured via `ADMIN_SECRET`.

## Rate Limiting

- Fixed-window per minute per API key using Redis (`rate:<api_key>:<minute>`).
- Configure with `RATE_LIMIT_RPM` (default: 60). Exceeding returns `429 Too many requests`.
- Fail-open behavior if rate limit backend errors occur (to reduce user-facing downtime during Redis outages).

## Credit Assignment (Admin)

- Endpoint: `POST /admin/topup { user_id, amount }`.
- Process:
  1. Read existing balance from Redis if present; otherwise fallback to Postgres.
  2. Update Redis to new balance.
  3. Upsert Postgres (`credits`) with the same balance for visibility.
- Authentication: `x-admin-secret` header.

## Credit Consumption (Per Request)

- All paid endpoints call `auth_and_consume()`; on success 1 credit is deducted.
- Redis-first deduction via Lua script (atomic `DECRBY` if sufficient balance).
- Immediate Postgres mirror after successful Redis deduction for consistency and observability.
- Fallback: If Redis is unavailable or key is missing, a Postgres transaction performs `SELECT ... FOR UPDATE` and decrements the balance, then attempts to backfill Redis.
- Exhausted credits: Returns `402 Insufficient credits`.

## Usage Logging

- Each request logs a record in `api_logs`:
  - `user_id`, `endpoint`, `credits_used`, `query_params` (JSON), `execution_time_ms`, `client_ip`, `created_at`.
- An index (`idx_api_logs_user_created_at`) supports querying by `user_id` and time.

## Data Model

```sql
-- users
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  api_key VARCHAR(64) UNIQUE NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- credits
CREATE TABLE IF NOT EXISTS credits (
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  credits_remaining INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  PRIMARY KEY(user_id)
);

-- api_logs
CREATE TABLE IF NOT EXISTS api_logs (
  id BIGSERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id),
  endpoint TEXT,
  credits_used INT,
  query_params JSONB,
  execution_time_ms INT,
  client_ip INET,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
```

## Configuration

- `ADMIN_SECRET`: Admin header for topups and sync.
- `RATE_LIMIT_RPM`: Requests per minute per API key.
- `MAX_ITEMS`: Maximum rows per request for `/search` and `/download`.
- `ENABLE_SYNC_WORKER`: Optional background sync from Redis to Postgres.
- `SYNC_INTERVAL_SECONDS`: Interval for the background sync worker.

## Operational Examples

- Top up 10 credits:
```
curl -s -X POST http://localhost:8000/admin/topup \
  -H 'x-admin-secret: local-admin' -H 'Content-Type: application/json' \
  -d '{"user_id": 3, "amount": 10}' | jq .
```

- Check credits in Postgres:
```
docker compose exec postgres psql -U admin -d credits_db \
  -c "SELECT u.email, c.credits_remaining, c.updated_at FROM users u JOIN credits c ON c.user_id = u.id WHERE u.api_key = 'demo-key';"
```

- Check credits in Redis:
```
docker compose exec redis redis-cli GET credits:3
```

- Export API logs (JSON Lines):
```
docker compose exec postgres psql -U admin -d credits_db -At -c \
  "COPY (SELECT row_to_json(l) FROM api_logs l ORDER BY id DESC LIMIT 500) TO STDOUT" \
  > sample-output/api-log.json
```

## Error Codes

- `401` Missing/Invalid API key.
- `402` Insufficient credits.
- `403` Forbidden (admin endpoints).
- `429` Too many requests.
- `400` Bad request (e.g., missing required parameters).
- `500` Internal server error.