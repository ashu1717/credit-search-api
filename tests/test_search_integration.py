import os
import time
import requests
import psycopg2

API_URL = os.getenv("API_URL", "http://localhost:8000")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "local-admin")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:admin@localhost:5432/credits_db")


def wait_for_api(timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(f"{API_URL}/health", timeout=2)
            if r.ok and r.json().get("ok"):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def ensure_demo_user(api_key: str = "demo-key") -> int:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, api_key, is_active) VALUES (%s, %s, true) ON CONFLICT (api_key) DO NOTHING",
                ("demo@example.com", api_key),
            )
            cur.execute("SELECT id FROM users WHERE api_key = %s", (api_key,))
            row = cur.fetchone()
            assert row, "Failed to fetch demo user id"
            return int(row[0])
    finally:
        conn.close()


def topup(user_id: int, amount: int = 5):
    r = requests.post(
        f"{API_URL}/admin/topup",
        headers={"x-admin-secret": ADMIN_SECRET, "Content-Type": "application/json"},
        json={"user_id": user_id, "amount": amount},
        timeout=5,
    )
    assert r.ok, f"topup failed: {r.status_code} {r.text}"
    j = r.json()
    assert j.get("ok"), f"topup not ok: {j}"
    assert j.get("balance") >= amount


def test_search_flow():
    assert wait_for_api(), "API health not ok in time"
    user_id = ensure_demo_user()
    topup(user_id, 5)

    # First call should pass and return JSON with keys
    r = requests.get(
        f"{API_URL}/search",
        params={"q": "Acme", "limit": 3},
        headers={"x-api-key": "demo-key"},
        timeout=10,
    )
    assert r.ok, f"search failed: {r.status_code} {r.text}"
    j = r.json()
    assert "results" in j and isinstance(j["results"], list)
    assert "count" in j and isinstance(j["count"], int)
    assert "exec_ms" in j