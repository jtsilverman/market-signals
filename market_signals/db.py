import time
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    keywords TEXT,
    last_price REAL,
    last_updated INTEGER
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    price REAL NOT NULL,
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (market_id) REFERENCES markets(id)
);

CREATE TABLE IF NOT EXISTS news_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE,
    title TEXT NOT NULL,
    source TEXT,
    published INTEGER NOT NULL,
    keywords TEXT,
    fetched INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    news_id INTEGER,
    price_before REAL,
    price_after REAL,
    price_change REAL,
    timestamp INTEGER NOT NULL,
    correlation_score REAL,
    FOREIGN KEY (market_id) REFERENCES markets(id),
    FOREIGN KEY (news_id) REFERENCES news_events(id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_market ON price_snapshots(market_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_time ON signals(timestamp DESC);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def upsert_market(
        self, id: str, platform: str, title: str, category: str, keywords: str, price: float
    ) -> None:
        now = int(time.time())
        await self._db.execute(
            """INSERT INTO markets (id, platform, title, category, keywords, last_price, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET last_price=?, last_updated=?, keywords=?""",
            (id, platform, title, category, keywords, price, now, price, now, keywords),
        )
        await self._db.commit()

    async def insert_snapshot(self, market_id: str, price: float) -> None:
        now = int(time.time())
        await self._db.execute(
            "INSERT INTO price_snapshots (market_id, price, timestamp) VALUES (?, ?, ?)",
            (market_id, price, now),
        )
        await self._db.commit()

    async def insert_news(self, url: str, title: str, source: str, published: int, keywords: str) -> int:
        now = int(time.time())
        try:
            cursor = await self._db.execute(
                "INSERT OR IGNORE INTO news_events (url, title, source, published, keywords, fetched) VALUES (?, ?, ?, ?, ?, ?)",
                (url, title, source, published, keywords, now),
            )
            await self._db.commit()
            return cursor.lastrowid or 0
        except Exception:
            return 0

    async def insert_signal(
        self, market_id: str, news_id: int, price_before: float, price_after: float,
        price_change: float, correlation_score: float
    ) -> None:
        now = int(time.time())
        await self._db.execute(
            """INSERT INTO signals (market_id, news_id, price_before, price_after, price_change, timestamp, correlation_score)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (market_id, news_id, price_before, price_after, price_change, now, correlation_score),
        )
        await self._db.commit()

    async def get_markets(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, platform, title, last_price, last_updated FROM markets ORDER BY last_updated DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_history(self, market_id: str, hours: int = 24) -> dict:
        cutoff = int(time.time()) - hours * 3600
        cursor = await self._db.execute(
            "SELECT price, timestamp FROM price_snapshots WHERE market_id=? AND timestamp>? ORDER BY timestamp",
            (market_id, cutoff),
        )
        prices = [dict(r) for r in await cursor.fetchall()]

        cursor = await self._db.execute(
            """SELECT n.title, n.url, s.price_change as impact, s.timestamp
               FROM signals s JOIN news_events n ON s.news_id=n.id
               WHERE s.market_id=? AND s.timestamp>? ORDER BY s.timestamp""",
            (market_id, cutoff),
        )
        events = [dict(r) for r in await cursor.fetchall()]
        return {"prices": prices, "events": events}

    async def get_signals(self, limit: int = 20, min_change: float = 0) -> list[dict]:
        cursor = await self._db.execute(
            """SELECT s.*, m.title as market_title, n.title as news_title, n.url as news_url
               FROM signals s
               JOIN markets m ON s.market_id=m.id
               LEFT JOIN news_events n ON s.news_id=n.id
               WHERE abs(s.price_change) >= ?
               ORDER BY s.timestamp DESC LIMIT ?""",
            (min_change, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]

    async def get_news(self, limit: int = 20) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT * FROM news_events ORDER BY fetched DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in await cursor.fetchall()]

    async def get_stats(self) -> dict:
        stats = {}
        for table, key in [("markets", "total_markets"), ("price_snapshots", "total_snapshots"),
                           ("signals", "total_signals"), ("news_events", "total_news")]:
            cursor = await self._db.execute(f"SELECT COUNT(*) as c FROM {table}")
            row = await cursor.fetchone()
            stats[key] = row["c"] if row else 0
        return stats

    async def get_price_change(self, market_id: str, hours: float = 1.0) -> tuple[float, float] | None:
        """Return (old_price, new_price) if data exists for the window."""
        cutoff = int(time.time()) - int(hours * 3600)
        cursor = await self._db.execute(
            "SELECT price, timestamp FROM price_snapshots WHERE market_id=? AND timestamp>? ORDER BY timestamp ASC LIMIT 1",
            (market_id, cutoff),
        )
        old = await cursor.fetchone()
        cursor = await self._db.execute(
            "SELECT price, timestamp FROM price_snapshots WHERE market_id=? ORDER BY timestamp DESC LIMIT 1",
            (market_id,),
        )
        new = await cursor.fetchone()
        if old and new and old["price"] != 0:
            return (old["price"], new["price"])
        return None
