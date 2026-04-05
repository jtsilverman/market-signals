import time

import pytest
import pytest_asyncio

from market_signals.db import Database


@pytest_asyncio.fixture
async def db():
    database = Database(":memory:")
    await database.init()
    yield database
    await database.close()


class TestDatabaseSchema:
    @pytest.mark.asyncio
    async def test_schema_creates_tables(self, db):
        """All expected tables exist after init."""
        cursor = await db._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cursor.fetchall()
        table_names = sorted([r["name"] for r in rows])
        assert "markets" in table_names
        assert "news_events" in table_names
        assert "price_snapshots" in table_names
        assert "signals" in table_names

    @pytest.mark.asyncio
    async def test_double_init_is_safe(self, db):
        """Calling init again does not raise (CREATE IF NOT EXISTS)."""
        await db.init()
        stats = await db.get_stats()
        assert stats["total_markets"] == 0


class TestInsertAndRetrieve:
    @pytest.mark.asyncio
    async def test_upsert_and_get_markets(self, db):
        await db.upsert_market("test:1", "test", "Will BTC hit 100k?", "crypto", "btc,bitcoin", 0.65)
        markets = await db.get_markets()
        assert len(markets) == 1
        assert markets[0]["id"] == "test:1"
        assert markets[0]["title"] == "Will BTC hit 100k?"
        assert markets[0]["last_price"] == 0.65

    @pytest.mark.asyncio
    async def test_upsert_updates_price(self, db):
        await db.upsert_market("test:1", "test", "Will BTC hit 100k?", "crypto", "btc", 0.50)
        await db.upsert_market("test:1", "test", "Will BTC hit 100k?", "crypto", "btc", 0.75)
        markets = await db.get_markets()
        assert len(markets) == 1
        assert markets[0]["last_price"] == 0.75

    @pytest.mark.asyncio
    async def test_insert_snapshot(self, db):
        await db.upsert_market("test:1", "test", "Title", "cat", "kw", 0.5)
        await db.insert_snapshot("test:1", 0.55)
        history = await db.get_history("test:1", hours=1)
        assert len(history["prices"]) == 1
        assert history["prices"][0]["price"] == 0.55

    @pytest.mark.asyncio
    async def test_insert_news_returns_id(self, db):
        news_id = await db.insert_news(
            url="https://example.com/article",
            title="BTC Crashes",
            source="example.com",
            published=int(time.time()),
            keywords="btc,crash",
        )
        assert news_id > 0

    @pytest.mark.asyncio
    async def test_insert_news_duplicate_url_ignored(self, db):
        ts = int(time.time())
        id1 = await db.insert_news("https://example.com/a", "Title", "src", ts, "kw")
        id2 = await db.insert_news("https://example.com/a", "Title2", "src2", ts, "kw2")
        assert id1 > 0
        # Second insert is ignored (INSERT OR IGNORE), no new row created
        news = await db.get_news(limit=10)
        assert len(news) == 1
        assert news[0]["title"] == "Title"  # original title preserved

    @pytest.mark.asyncio
    async def test_insert_and_get_signals(self, db):
        await db.upsert_market("test:1", "test", "BTC Price", "crypto", "btc", 0.5)
        news_id = await db.insert_news("https://ex.com/1", "News", "src", int(time.time()), "kw")
        await db.insert_signal("test:1", news_id, 0.45, 0.55, 10.0, 0.8)
        signals = await db.get_signals(limit=10)
        assert len(signals) == 1
        assert signals[0]["market_title"] == "BTC Price"
        assert signals[0]["correlation_score"] == 0.8


class TestGetPriceChange:
    @pytest.mark.asyncio
    async def test_no_snapshots_returns_none(self, db):
        result = await db.get_price_change("nonexistent", hours=1.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_old_and_new_price(self, db):
        await db.upsert_market("test:1", "test", "Title", "cat", "kw", 0.5)
        # Insert snapshots with explicit timestamps via raw SQL
        now = int(time.time())
        await db._db.execute(
            "INSERT INTO price_snapshots (market_id, price, timestamp) VALUES (?, ?, ?)",
            ("test:1", 0.40, now - 1800),  # 30 min ago
        )
        await db._db.execute(
            "INSERT INTO price_snapshots (market_id, price, timestamp) VALUES (?, ?, ?)",
            ("test:1", 0.60, now),
        )
        await db._db.commit()

        result = await db.get_price_change("test:1", hours=1.0)
        assert result is not None
        old, new = result
        assert old == 0.40
        assert new == 0.60

    @pytest.mark.asyncio
    async def test_old_price_zero_returns_none(self, db):
        """If oldest price in window is 0, returns None."""
        now = int(time.time())
        await db._db.execute(
            "INSERT INTO price_snapshots (market_id, price, timestamp) VALUES (?, ?, ?)",
            ("test:1", 0.0, now - 1800),
        )
        await db._db.execute(
            "INSERT INTO price_snapshots (market_id, price, timestamp) VALUES (?, ?, ?)",
            ("test:1", 0.5, now),
        )
        await db._db.commit()

        result = await db.get_price_change("test:1", hours=1.0)
        assert result is None


class TestGetRecentSignals:
    @pytest.mark.asyncio
    async def test_empty_signals(self, db):
        signals = await db.get_signals(limit=10)
        assert signals == []

    @pytest.mark.asyncio
    async def test_min_change_filter(self, db):
        await db.upsert_market("t:1", "test", "Title", "cat", "kw", 0.5)
        nid = await db.insert_news("https://ex.com/1", "N", "s", int(time.time()), "k")
        await db.insert_signal("t:1", nid, 0.5, 0.51, 2.0, 0.5)  # 2% change
        await db.insert_signal("t:1", nid, 0.5, 0.60, 20.0, 0.9)  # 20% change

        # Filter for >= 10% change
        signals = await db.get_signals(limit=10, min_change=10.0)
        assert len(signals) == 1
        assert signals[0]["price_change"] == 20.0

    @pytest.mark.asyncio
    async def test_stats(self, db):
        stats = await db.get_stats()
        assert stats["total_markets"] == 0
        assert stats["total_snapshots"] == 0
        assert stats["total_signals"] == 0
        assert stats["total_news"] == 0

        await db.upsert_market("t:1", "test", "Title", "cat", "kw", 0.5)
        stats = await db.get_stats()
        assert stats["total_markets"] == 1
