Postgres Schema (credits_db)

Tables
- `users`
  - `id SERIAL PRIMARY KEY`
  - `email TEXT`
  - `api_key TEXT UNIQUE`
  - `is_active BOOLEAN`
- `credits`
  - `user_id INT PRIMARY KEY REFERENCES users(id)`
  - `credits_remaining INT`
  - `updated_at TIMESTAMP`
- `api_logs`
  - `id SERIAL PRIMARY KEY`
  - `user_id INT REFERENCES users(id)`
  - `endpoint TEXT`
  - `credits_used INT`
  - `query_params JSONB`
  - `execution_time_ms INT`
  - `client_ip TEXT`

Redis Keys
- Credit counters: `credits:<user_id>` → integer balance
- Lua script ensures atomic decrement when sufficient credits are present

ClickHouse
- Main table: `analytics.persons_ingested`
  - Columns: `id`, `person_name`, `person_title`, `person_email`, `score`, etc.
- Queries: `/search` and `/download` use case-insensitive matching on name/title

Notes
- Redis is the primary enforcement layer; Postgres is the durable mirror.
- Manual and optional background sync maintain consistency.