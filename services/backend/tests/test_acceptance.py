"""
Test suite covering acceptance criteria from the spec.
Run with: pytest tests/ -v

Requires a running stack (docker compose up) or a test database.
Set TEST_DATABASE_URL env var to point at a test DB.
"""
import pytest
import httpx
from datetime import date, datetime, timedelta, timezone

BASE_URL = "http://localhost:8000"


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE_URL, timeout=30)


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_has_db_field(self, client):
        r = client.get("/health")
        data = r.json()
        assert "db" in data
        assert "stream" in data
        assert "status" in data

    def test_health_status_values_valid(self, client):
        r = client.get("/health")
        assert r.json()["status"] in ("healthy", "degraded", "unhealthy")


# ------------------------------------------------------------------
# Tickers / Watchlist
# ------------------------------------------------------------------

class TestTickers:
    TEST_SYMBOL = "TSTR"

    def _cleanup(self, client):
        client.delete(f"/tickers/{self.TEST_SYMBOL}")

    def test_list_tickers_returns_list(self, client):
        r = client.get("/tickers")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_add_ticker(self, client):
        self._cleanup(client)
        r = client.post("/tickers", json={"symbol": self.TEST_SYMBOL, "name": "Test Ticker"})
        assert r.status_code == 201
        data = r.json()
        assert data["symbol"] == self.TEST_SYMBOL
        self._cleanup(client)

    def test_add_duplicate_returns_409(self, client):
        self._cleanup(client)
        client.post("/tickers", json={"symbol": self.TEST_SYMBOL})
        r = client.post("/tickers", json={"symbol": self.TEST_SYMBOL})
        assert r.status_code == 409
        self._cleanup(client)

    def test_patch_ticker(self, client):
        self._cleanup(client)
        client.post("/tickers", json={"symbol": self.TEST_SYMBOL})
        r = client.patch(f"/tickers/{self.TEST_SYMBOL}", json={"notes": "test note"})
        assert r.status_code == 200
        assert r.json()["notes"] == "test note"
        self._cleanup(client)

    def test_delete_ticker(self, client):
        client.post("/tickers", json={"symbol": self.TEST_SYMBOL})
        r = client.delete(f"/tickers/{self.TEST_SYMBOL}")
        assert r.status_code == 204

    def test_delete_nonexistent_returns_404(self, client):
        r = client.delete("/tickers/XXXNONEXISTENT")
        assert r.status_code == 404


# ------------------------------------------------------------------
# Bars — Data Access
# ------------------------------------------------------------------

class TestBars:
    def test_bars_invalid_resolution_returns_422(self, client):
        r = client.get("/bars/AAPL?resolution=invalid")
        assert r.status_code == 422

    def test_bars_returns_list(self, client):
        r = client.get("/bars/AAPL?resolution=1d")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_bars_filtered_by_date_range(self, client):
        start = (date.today() - timedelta(days=7)).isoformat()
        end = date.today().isoformat()
        r = client.get(f"/bars/AAPL?resolution=1d&start={start}&end={end}")
        assert r.status_code == 200

    def test_latest_bar_returns_single_or_none(self, client):
        r = client.get("/bars/AAPL/latest?resolution=1d")
        assert r.status_code == 200
        assert r.json() is None or isinstance(r.json(), dict)

    def test_resolutions_endpoint(self, client):
        r = client.get("/bars/AAPL/resolutions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ------------------------------------------------------------------
# Ingestion Operations
# ------------------------------------------------------------------

class TestIngest:
    def test_status_returns_list(self, client):
        r = client.get("/ingest/status")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_log_returns_paginated(self, client):
        r = client.get("/ingest/log")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "results" in data

    def test_backfill_invalid_resolution(self, client):
        r = client.post("/ingest/backfill", json={
            "symbol": "AAPL",
            "resolution": "bad",
            "start": "2024-01-01",
            "end": "2024-01-05",
        })
        assert r.status_code == 422

    def test_backfill_invalid_date_range(self, client):
        r = client.post("/ingest/backfill", json={
            "symbol": "AAPL",
            "resolution": "1d",
            "start": "2024-01-10",
            "end": "2024-01-01",
        })
        assert r.status_code == 422


# ------------------------------------------------------------------
# Stream
# ------------------------------------------------------------------

class TestStream:
    def test_stream_status_returns_state(self, client):
        r = client.get("/stream/status")
        assert r.status_code == 200
        data = r.json()
        assert "state" in data
        assert data["state"] in ("connected", "disconnected", "reconnecting", "fallback")

    def test_subscribe_returns_200(self, client):
        r = client.post("/stream/subscribe", json={"symbols": ["AAPL"]})
        assert r.status_code == 200

    def test_unsubscribe_returns_200(self, client):
        r = client.post("/stream/unsubscribe", json={"symbols": ["AAPL"]})
        assert r.status_code == 200


# ------------------------------------------------------------------
# Scheduler
# ------------------------------------------------------------------

class TestScheduler:
    def test_jobs_list(self, client):
        r = client.get("/scheduler/jobs")
        assert r.status_code == 200
        data = r.json()
        assert "jobs" in data
        job_ids = [j["id"] for j in data["jobs"]]
        assert "eod_daily_pull" in job_ids
        assert "gap_audit" in job_ids
        assert "retention_cleanup" in job_ids
        assert "monday_gap_pull" in job_ids
