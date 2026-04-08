import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from market_signals.api import app
from market_signals.db import Database


def _run(coro):
    """Run an async coroutine synchronously using the existing event loop."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


@pytest.fixture
def client():
    """Create a TestClient with a fresh in-memory db for each test."""
    # Force a fresh db every test by replacing app.state.db before startup
    fresh_db = Database(":memory:")
    _run(fresh_db.init())
    app.state.db = fresh_db
    with TestClient(app) as c:
        yield c
    _run(fresh_db.close())


def _seed_market(market_id: str = "test:1", price: float = 0.65) -> None:
    """Insert a market directly via the db on app.state."""
    db = app.state.db
    _run(db.upsert_market(market_id, "test", "Will BTC hit 100k?", "crypto", "btc", price))


def _seed_snapshot(market_id: str, price: float, ts: int) -> None:
    """Insert a price snapshot with explicit timestamp."""
    db = app.state.db
    _run(db._db.execute(
        "INSERT INTO price_snapshots (market_id, price, timestamp) VALUES (?, ?, ?)",
        (market_id, price, ts),
    ))
    _run(db._db.commit())


def _seed_news(url: str = "https://example.com/a", title: str = "BTC Crashes") -> int:
    """Insert a news event and return its id."""
    db = app.state.db
    return _run(db.insert_news(url, title, "example.com", int(time.time()), "btc"))


def _seed_signal(
    market_id: str = "test:1",
    news_id: int = 1,
    price_change: float = 10.0,
) -> None:
    """Insert a signal."""
    db = app.state.db
    _run(db.insert_signal(market_id, news_id, 0.50, 0.60, price_change, 0.8))


# ---------------------------------------------------------------------------
# GET /api/markets
# ---------------------------------------------------------------------------

class TestListMarkets:
    def test_empty_db_returns_empty_list(self, client):
        resp = client.get("/api/markets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_with_data_returns_price_change_fields(self, client):
        now = int(time.time())
        _seed_market("test:1", 0.65)
        _seed_snapshot("test:1", 0.50, now - 1800)
        _seed_snapshot("test:1", 0.65, now)

        resp = client.get("/api/markets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "price_change_1h" in data[0]
        assert "price_change_24h" in data[0]
        assert data[0]["id"] == "test:1"
        # 1h change: (0.65 - 0.50) / 0.50 * 100 = 30.0
        assert data[0]["price_change_1h"] == 30.0

    def test_price_change_zero_when_old_price_is_zero(self, client):
        """Division-by-zero guard: old_price=0 should yield price_change=0."""
        now = int(time.time())
        _seed_market("zero:1", 0.50)
        _seed_snapshot("zero:1", 0.0, now - 1800)
        _seed_snapshot("zero:1", 0.50, now)

        resp = client.get("/api/markets")
        data = resp.json()
        assert len(data) == 1
        # get_price_change returns None when old price is 0, so api returns 0
        assert data[0]["price_change_1h"] == 0
        assert data[0]["price_change_24h"] == 0


# ---------------------------------------------------------------------------
# GET /api/markets/{id}/history
# ---------------------------------------------------------------------------

class TestMarketHistory:
    def test_returns_history_dict(self, client):
        now = int(time.time())
        _seed_market("test:1")
        _seed_snapshot("test:1", 0.55, now - 600)

        resp = client.get("/api/markets/test:1/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "prices" in data
        assert "events" in data
        assert len(data["prices"]) == 1
        assert data["prices"][0]["price"] == 0.55

    def test_respects_hours_param(self, client):
        now = int(time.time())
        _seed_market("test:1")
        _seed_snapshot("test:1", 0.40, now - 7200)  # 2 hours ago
        _seed_snapshot("test:1", 0.60, now - 600)    # 10 min ago

        # Only 1 hour window should exclude the 2h-old snapshot
        resp = client.get("/api/markets/test:1/history?hours=1")
        data = resp.json()
        assert len(data["prices"]) == 1
        assert data["prices"][0]["price"] == 0.60

    def test_nonexistent_market_returns_empty(self, client):
        resp = client.get("/api/markets/nonexistent:99/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["prices"] == []
        assert data["events"] == []


# ---------------------------------------------------------------------------
# GET /api/signals
# ---------------------------------------------------------------------------

class TestListSignals:
    def test_empty_returns_list(self, client):
        resp = client.get("/api/signals")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_respects_limit_param(self, client):
        _seed_market("test:1")
        nid = _seed_news("https://ex.com/1", "News 1")
        _seed_signal("test:1", nid, 5.0)
        nid2 = _seed_news("https://ex.com/2", "News 2")
        _seed_signal("test:1", nid2, 15.0)

        resp = client.get("/api/signals?limit=1")
        data = resp.json()
        assert len(data) == 1

    def test_respects_min_change_param(self, client):
        _seed_market("test:1")
        nid = _seed_news("https://ex.com/1", "News 1")
        _seed_signal("test:1", nid, 2.0)   # small change
        nid2 = _seed_news("https://ex.com/2", "News 2")
        _seed_signal("test:1", nid2, 20.0)  # big change

        resp = client.get("/api/signals?min_change=10")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["price_change"] == 20.0


# ---------------------------------------------------------------------------
# GET /api/news
# ---------------------------------------------------------------------------

class TestListNews:
    def test_empty_returns_list(self, client):
        resp = client.get("/api/news")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_respects_limit_param(self, client):
        _seed_news("https://ex.com/1", "News 1")
        _seed_news("https://ex.com/2", "News 2")
        _seed_news("https://ex.com/3", "News 3")

        resp = client.get("/api/news?limit=2")
        data = resp.json()
        assert len(data) == 2


# ---------------------------------------------------------------------------
# GET /api/stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_returns_dict_with_uptime(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "uptime_seconds" in data
        assert "total_markets" in data
        assert "total_snapshots" in data
        assert "total_signals" in data
        assert "total_news" in data

    def test_uptime_is_non_negative_int(self, client):
        resp = client.get("/api/stats")
        data = resp.json()
        assert isinstance(data["uptime_seconds"], int)
        assert data["uptime_seconds"] >= 0

    def test_stats_reflect_seeded_data(self, client):
        _seed_market("test:1")
        _seed_news("https://ex.com/1", "News")

        resp = client.get("/api/stats")
        data = resp.json()
        assert data["total_markets"] == 1
        assert data["total_news"] == 1
        assert data["total_signals"] == 0


# ---------------------------------------------------------------------------
# Negative / edge-case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_invalid_endpoint_returns_404(self, client):
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404

    def test_markets_history_bad_hours_param(self, client):
        """Non-integer hours param should return 422 validation error."""
        resp = client.get("/api/markets/test:1/history?hours=abc")
        assert resp.status_code == 422

    def test_signals_bad_limit_param(self, client):
        """Non-integer limit should return 422 validation error."""
        resp = client.get("/api/signals?limit=xyz")
        assert resp.status_code == 422

    def test_news_bad_limit_param(self, client):
        """Non-integer limit should return 422 validation error."""
        resp = client.get("/api/news?limit=xyz")
        assert resp.status_code == 422
