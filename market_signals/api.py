import time
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import Database

app = FastAPI(title="Market Signals")

# Database is attached via app.state.db by __main__.py
# For testing, init with in-memory db
_start_time = time.time()

STATIC_DIR = Path(__file__).parent.parent / "static"


@app.on_event("startup")
async def startup():
    if not hasattr(app.state, "db") or app.state.db is None:
        db = Database(":memory:")
        await db.init()
        app.state.db = db


def get_db() -> Database:
    return app.state.db


@app.get("/api/markets")
async def list_markets():
    db = get_db()
    markets = await db.get_markets()
    result = []
    for m in markets:
        change_1h = await db.get_price_change(m["id"], hours=1.0)
        change_24h = await db.get_price_change(m["id"], hours=24.0)
        result.append({
            **m,
            "price_change_1h": round(((change_1h[1] - change_1h[0]) / change_1h[0]) * 100, 2) if change_1h and change_1h[0] != 0 else 0,
            "price_change_24h": round(((change_24h[1] - change_24h[0]) / change_24h[0]) * 100, 2) if change_24h and change_24h[0] != 0 else 0,
        })
    return result


@app.get("/api/markets/{market_id:path}/history")
async def market_history(market_id: str, hours: int = Query(24)):
    db = get_db()
    return await db.get_history(market_id, hours)


@app.get("/api/signals")
async def list_signals(limit: int = Query(20), min_change: float = Query(0)):
    db = get_db()
    return await db.get_signals(limit, min_change)


@app.get("/api/news")
async def list_news(limit: int = Query(20)):
    db = get_db()
    return await db.get_news(limit)


@app.get("/api/stats")
async def stats():
    db = get_db()
    s = await db.get_stats()
    s["uptime_seconds"] = int(time.time() - _start_time)
    return s


# Serve static frontend
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def serve_dashboard():
        return FileResponse(STATIC_DIR / "index.html")
