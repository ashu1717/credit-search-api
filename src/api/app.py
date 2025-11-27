from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
import csv
from io import StringIO
import os
import time
import json
from typing import Optional

# Config from env (defaults target docker-compose services)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:admin@postgres:5432/credits_db")
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", 9000))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "local-admin")
RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "60"))
# Maximum rows returned per request for JSON/CSV endpoints
MAX_ITEMS = int(os.getenv("MAX_ITEMS", "500"))

# Postgres connection pool
import psycopg2
import psycopg2.pool

pg_pool: Optional[psycopg2.pool.SimpleConnectionPool] = None
try:
    pg_pool = psycopg2.pool.SimpleConnectionPool(1, 10, dsn=DATABASE_URL)
except Exception as e:
    print("Warning: Postgres pool init failed:", e)

# Redis client
import redis
redis_client = redis.Redis.from_url(REDIS_URL)

# ClickHouse client
from clickhouse_driver import Client as CHClient
from pydantic import BaseModel
# ClickHouse client with startup retries (waits for CH to become ready)
import time
import threading
from fastapi.responses import JSONResponse

ch_client = None
for i in range(12):  # try for ~24 seconds (12 * 2s)
    try:
        ch_client = CHClient(host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT)
        ch_client.execute("SELECT 1")
        print("Connected to ClickHouse")
        break
    except Exception as e:
        print(f"ClickHouse not ready (attempt {i+1}/12): {e}")
        time.sleep(2)
else:
    raise RuntimeError("ClickHouse unavailable after retries")

# Optional background worker to periodically sync Redis credits back to Postgres
ENABLE_SYNC_WORKER = os.environ.get("ENABLE_SYNC_WORKER", "false").lower() == "true"
SYNC_INTERVAL_SECONDS = int(os.environ.get("SYNC_INTERVAL_SECONDS", "60"))

def require_admin_secret(request: Request):
    secret = request.headers.get("x-admin-secret")
    if secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

def sync_redis_to_postgres():
    conn = pg_pool.getconn()
    try:
        updated = 0
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM credits")
                for (uid,) in cur.fetchall():
                    v = redis_client.get(f"credits:{uid}")
                    if v is not None:
                        cur.execute(
                            "UPDATE credits SET credits_remaining = %s, updated_at = now() WHERE user_id = %s",
                            (int(v), uid),
                        )
                        updated += 1
        return updated
    finally:
        pg_pool.putconn(conn)

def start_sync_worker():
    def worker():
        while True:
            try:
                count = sync_redis_to_postgres()
                if count:
                    print(f"Sync worker flushed {count} Redis credits to Postgres")
            except Exception as e:
                print(f"Sync worker error: {e}")
            time.sleep(SYNC_INTERVAL_SECONDS)

    t = threading.Thread(target=worker, daemon=True)
    t.start()

# Startup worker registration will be attached via decorator below app creation

def _sync_credits_endpoint_impl():
    try:
        updated = sync_redis_to_postgres()
        return {"ok": True, "updated": updated}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

app = FastAPI(title="Credit-based ClickHouse API", version="0.1")

@app.on_event("startup")
async def _start_sync_worker_if_enabled():
    if ENABLE_SYNC_WORKER:
        start_sync_worker()

@app.post("/admin/sync-credits")
async def sync_credits_endpoint(request: Request):
    require_admin_secret(request)
    return _sync_credits_endpoint_impl()


class TopUpRequest(BaseModel):
    user_id: int
    amount: int


@app.post("/admin/topup")
async def admin_topup(request: Request, req: TopUpRequest):
    require_admin_secret(request)
    if req.amount <= 0:
        return JSONResponse(status_code=400, content={"ok": False, "error": "amount must be > 0"})
    try:
        key = f"credits:{req.user_id}"
        cur_val = redis_client.get(key)
        if cur_val is None:
            # Fallback to Postgres when Redis key is missing
            conn = None
            base_val = 0
            try:
                conn = get_pg_conn()
                cur = conn.cursor()
                cur.execute("SELECT credits_remaining FROM credits WHERE user_id = %s", (req.user_id,))
                row = cur.fetchone()
                base_val = int(row[0]) if row else 0
                cur.close()
            except Exception as e:
                print("topup: read postgres error", e)
            finally:
                if conn:
                    release_pg_conn(conn)
        else:
            base_val = int(cur_val)

        new_val = base_val + req.amount

        # Update Redis first (primary for enforcement)
        redis_client.set(key, new_val)

        # Upsert Postgres for visibility and consistency
        conn = None
        try:
            conn = get_pg_conn()
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM credits WHERE user_id = %s", (req.user_id,))
            exists = cur.fetchone() is not None
            if exists:
                cur.execute(
                    "UPDATE credits SET credits_remaining = %s, updated_at = now() WHERE user_id = %s",
                    (new_val, req.user_id),
                )
            else:
                cur.execute(
                    "INSERT INTO credits (user_id, credits_remaining, updated_at) VALUES (%s, %s, now())",
                    (req.user_id, new_val),
                )
            conn.commit()
            cur.close()
        except Exception as e:
            print("topup: write postgres error", e)
        finally:
            if conn:
                release_pg_conn(conn)

        return {"ok": True, "user_id": req.user_id, "added": req.amount, "balance": new_val}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

# Lua for atomic credit deduction
DEDUCT_LUA = """
local v = redis.call('GET', KEYS[1])
if not v then
  return -1
end
local n = tonumber(v)
local amount = tonumber(ARGV[1])
if n >= amount then
  redis.call('DECRBY', KEYS[1], amount)
  return 1
else
  return 0
end
"""

def get_pg_conn():
    if not pg_pool:
        raise RuntimeError("Postgres pool not initialized")
    return pg_pool.getconn()

def release_pg_conn(conn):
    if pg_pool and conn:
        pg_pool.putconn(conn)

def validate_api_key(api_key: str) -> Optional[int]:
    conn = None
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE api_key = %s AND is_active = true", (api_key,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    except Exception as e:
        print("validate_api_key error", e)
        return None
    finally:
        if conn:
            release_pg_conn(conn)

def try_consume_credits(user_id: int, amount: int = 1) -> bool:
    key = f"credits:{user_id}"
    try:
        res = redis_client.eval(DEDUCT_LUA, 1, key, amount)
        if res == 1:
            # Mirror successful Redis deduction to Postgres for immediate visibility
            try:
                new_val_raw = redis_client.get(key)
                new_val = int(new_val_raw) if new_val_raw is not None else None
            except Exception:
                new_val = None

            if new_val is not None:
                conn = None
                try:
                    conn = get_pg_conn()
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE credits SET credits_remaining = %s, updated_at = now() WHERE user_id = %s",
                        (new_val, user_id),
                    )
                    conn.commit()
                    cur.close()
                except Exception as e:
                    # If Postgres mirror fails, continue; Redis remains the source of truth
                    print("postgres mirror after redis deduct error", e)
                    if conn:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                finally:
                    if conn:
                        release_pg_conn(conn)
            return True
        if res == 0:
            return False
    except Exception as e:
        print("Redis deduct error:", e)

    conn = None
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute('BEGIN;')
        cur.execute('SELECT credits_remaining FROM credits WHERE user_id = %s FOR UPDATE', (user_id,))
        row = cur.fetchone()
        if not row:
            cur.execute('ROLLBACK;')
            cur.close()
            return False
        available = row[0]
        if available >= amount:
            cur.execute('UPDATE credits SET credits_remaining = credits_remaining - %s, updated_at = now() WHERE user_id = %s', (amount, user_id))
            conn.commit()
            cur.close()
            try:
                redis_client.set(key, available - amount)
            except Exception:
                pass
            return True
        else:
            conn.rollback()
            cur.close()
            return False
    except Exception as e:
        print("Postgres deduct error", e)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_pg_conn(conn)

def log_api_call(user_id: int, endpoint: str, credits_used: int, query_params: dict, exec_ms: int, client_ip: Optional[str] = None):
    conn = None
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO api_logs (user_id, endpoint, credits_used, query_params, execution_time_ms, client_ip) VALUES (%s,%s,%s,%s,%s,%s)",
            (user_id, endpoint, credits_used, json.dumps(query_params), exec_ms, client_ip),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        print("log_api_call error", e)
        if conn:
            conn.rollback()
    finally:
        if conn:
            release_pg_conn(conn)

@app.get("/health")
def health():
    status = {"postgres": False, "redis": False, "clickhouse": False}
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        _ = cur.fetchone()
        cur.close()
        release_pg_conn(conn)
        status["postgres"] = True
    except Exception:
        status["postgres"] = False
    try:
        redis_client.ping()
        status["redis"] = True
    except Exception:
        status["redis"] = False
    try:
        ch_client.execute("SELECT 1")
        status["clickhouse"] = True
    except Exception:
        status["clickhouse"] = False
    ok = all(status.values())
    return JSONResponse({"ok": ok, **status})

def auth_and_consume(request: Request) -> int:
    api_key = request.headers.get("x-api-key")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    user_id = validate_api_key(api_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API key")
    # Rate limiting: fixed window per minute per API key
    try:
        if RATE_LIMIT_RPM > 0:
            now_min = int(time.time() // 60)
            key = f"rate:{api_key}:{now_min}"
            count = redis_client.incr(key)
            if count == 1:
                # Set TTL slightly over 1 minute to cover window
                redis_client.expire(key, 120)
            if count > RATE_LIMIT_RPM:
                raise HTTPException(status_code=429, detail="Too many requests")
    except HTTPException:
        raise
    except Exception as e:
        # Fail-open on rate limit backend errors to avoid unnecessary downtime
        print("rate_limit error:", e)
    if not try_consume_credits(user_id, 1):
        raise HTTPException(status_code=402, detail="Insufficient credits")
    return user_id

@app.get("/search")
def search(
    request: Request,
    q: Optional[str] = None,
    limit: int = 50,
    page: int = 1,
    title: Optional[str] = None,
    country: Optional[str] = None,
    email_domain: Optional[str] = None,
    score_min: Optional[int] = None,
    score_max: Optional[int] = None,
):
    user_id = auth_and_consume(request)
    t0 = time.time()
    try:
        # Sanitize and clamp pagination
        if page < 1:
            page = 1
        if limit < 1:
            limit = 1
        if limit > MAX_ITEMS:
            limit = MAX_ITEMS
        offset = (page - 1) * limit

        # Build dynamic filters
        where_clauses = []
        params = {"limit": limit, "offset": offset}

        term = (q or "").strip()
        if term:
            where_clauses.append(
                "(positionCaseInsensitive(person_name, %(term)s) > 0 OR positionCaseInsensitive(person_title, %(term)s) > 0)"
            )
            params["term"] = term

        if title:
            params["title"] = title
            where_clauses.append("positionCaseInsensitive(person_title, %(title)s) > 0")

        if country:
            params["country"] = country
            where_clauses.append("person_location_country = %(country)s")

        if email_domain:
            # Match emails ending with the given domain
            # Build a LIKE pattern server-side to avoid CH concat quirks
            params["email_pat"] = "%@" + email_domain
            where_clauses.append("person_email LIKE %(email_pat)s")

        if score_min is not None:
            params["score_min"] = int(score_min)
            where_clauses.append("toInt64OrNull(score) >= %(score_min)s")

        if score_max is not None:
            params["score_max"] = int(score_max)
            where_clauses.append("toInt64OrNull(score) <= %(score_max)s")

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # Query with pagination
        sql = (
            "SELECT id, person_name, person_title, person_email, score "
            "FROM analytics.persons_ingested"
            + where_sql +
            " ORDER BY score DESC NULLS LAST, person_name ASC"
            " LIMIT %(limit)s OFFSET %(offset)s"
        )
        rows = ch_client.execute(sql, params=params)

        # Total matching rows for metadata
        count_sql = "SELECT count() FROM analytics.persons_ingested" + where_sql
        total_records = ch_client.execute(count_sql, params=params)[0][0]
        columns = ["id", "person_name", "person_title", "person_email", "score"]
        data = [dict(zip(columns, r)) for r in rows]
        exec_ms = int((time.time() - t0) * 1000)
        try:
            log_api_call(
                user_id,
                "/search",
                1,
                {
                    "q": q,
                    "limit": limit,
                    "page": page,
                    "title": title,
                    "country": country,
                    "email_domain": email_domain,
                    "score_min": score_min,
                    "score_max": score_max,
                },
                exec_ms,
                request.client.host if request.client else None,
            )
        except Exception:
            pass
        return JSONResponse({
            "results": data,
            "count": len(data),
            "total_records": int(total_records),
            "page": page,
            "limit": limit,
            "credits_used": 1,
            "exec_ms": exec_ms,
        })
    except HTTPException:
        raise
    except Exception as e:
        print("/search error:", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/download")
def download(
    request: Request,
    q: Optional[str] = None,
    limit: int = 10000,
    title: Optional[str] = None,
    country: Optional[str] = None,
    email_domain: Optional[str] = None,
    score_min: Optional[int] = None,
    score_max: Optional[int] = None,
):
    user_id = auth_and_consume(request)
    t0 = time.time()
    try:
        # Enforce maximum items
        if limit < 1:
            limit = 1
        if limit > MAX_ITEMS:
            limit = MAX_ITEMS

        where_clauses = []
        params = {"limit": limit}
        term = (q or "").strip()
        if term:
            where_clauses.append(
                "(positionCaseInsensitive(person_name, %(term)s) > 0 OR positionCaseInsensitive(person_title, %(term)s) > 0)"
            )
            params["term"] = term
        if title:
            params["title"] = title
            where_clauses.append("positionCaseInsensitive(person_title, %(title)s) > 0")
        if country:
            params["country"] = country
            where_clauses.append("person_location_country = %(country)s")
        if email_domain:
            params["email_pat"] = "%@" + email_domain
            where_clauses.append("person_email LIKE %(email_pat)s")
        if score_min is not None:
            params["score_min"] = int(score_min)
            where_clauses.append("toInt64OrNull(score) >= %(score_min)s")
        if score_max is not None:
            params["score_max"] = int(score_max)
            where_clauses.append("toInt64OrNull(score) <= %(score_max)s")

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        sql = (
            "SELECT id, person_name, person_title, person_email, score "
            "FROM analytics.persons_ingested"
            + where_sql +
            " ORDER BY score DESC NULLS LAST, person_name ASC"
            " LIMIT %(limit)s"
        )
        rows = ch_client.execute(sql, params=params)
        columns = ["id", "person_name", "person_title", "person_email", "score"]

        def generate():
            buf = StringIO()
            writer = csv.writer(buf)
            writer.writerow(columns)
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)
            for r in rows:
                writer.writerow(r)
                yield buf.getvalue()
                buf.seek(0); buf.truncate(0)

        headers = {"Content-Disposition": 'attachment; filename="download.csv"'}
        exec_ms = int((time.time() - t0) * 1000)
        try:
            log_api_call(
                user_id,
                "/download",
                1,
                {
                    "q": q,
                    "limit": limit,
                    "title": title,
                    "country": country,
                    "email_domain": email_domain,
                    "score_min": score_min,
                    "score_max": score_max,
                },
                exec_ms,
                request.client.host if request.client else None,
            )
        except Exception:
            pass
        return StreamingResponse(generate(), media_type="text/csv", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        print("/download error:", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/person/{person_id}")
def get_person(person_id: str, request: Request):
    user_id = auth_and_consume(request)
    t0 = time.time()
    try:
        if not person_id:
            raise HTTPException(status_code=400, detail="Path param 'person_id' is required")

        sql = "SELECT * FROM analytics.persons_ingested WHERE id = %(id)s LIMIT 1"
        rows = ch_client.execute(sql, {"id": person_id})
        if not rows:
            raise HTTPException(status_code=404, detail="Not Found")

        # Fetch column names to build a dict record
        cols_rows = ch_client.execute(
            "SELECT name FROM system.columns WHERE table = 'persons_ingested' AND database = 'analytics'"
        )
        columns = [c[0] for c in cols_rows]
        record = dict(zip(columns, rows[0]))

        exec_ms = int((time.time() - t0) * 1000)
        try:
            log_api_call(user_id, "/person", 1, {"person_id": person_id}, exec_ms, request.client.host if request.client else None)
        except Exception:
            pass
        return JSONResponse({"record": record, "exec_ms": exec_ms})
    except HTTPException:
        raise
    except Exception as e:
        print("/person error:", e)
        raise HTTPException(status_code=500, detail="Internal server error")