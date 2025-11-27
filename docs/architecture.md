Architecture Diagram

Mermaid
```
flowchart LR
    Client[Client] -- x-api-key --> API[FastAPI]
    Admin[Admin] -- x-admin-secret --> API
    API -- SQL --> Postgres[(credits_db)]
    API -- Redis ops --> Redis[(Redis)]
    API -- CH driver --> ClickHouse[(ClickHouse)]

    subgraph Credits Enforcement
      API --> Redis
      Redis --> API
      API --> Postgres
    end

    subgraph Analytics Data
      Ingest[ingest.py] --> ClickHouse
      Schema[export_schema.py] --> Docs
    end
```

Data Flow
- Requests arrive at FastAPI; per-request credits are authenticated via `x-api-key`.
- Credits are decremented atomically via Redis Lua; Postgres mirrors for durability.
- Search and download query ClickHouse for results; `/download` streams CSV.
- Admin helpers (`/admin/topup`, `/admin/sync-credits`) require `x-admin-secret`.
- Optional background worker periodically reconciles Redis → Postgres.

Why Redis-first?
- Atomic credit decrements via Redis Lua scripts avoid race conditions under concurrent requests.
- Low-latency counter operations keep the hot path fast and reduce database round trips.
- Strong single-key concurrency guarantees align with per-user counters; scales for bursty traffic.
- Postgres provides durable mirrors for audit/reporting; manual or periodic sync reconciles state.
- Fallback to Postgres paths maintains service continuity if Redis is temporarily unavailable.