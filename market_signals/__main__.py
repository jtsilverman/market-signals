import asyncio
import logging
import signal
import sys
import time

import uvicorn

from .config import Settings
from .db import Database
from .poller import KalshiPoller, PolymarketPoller
from .correlator import Correlator
from .api import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def poll_loop(settings: Settings, db: Database):
    """Main polling loop: fetch markets, store snapshots, run correlation."""
    kalshi = KalshiPoller(settings)
    polymarket = PolymarketPoller(settings)
    correlator = Correlator(settings)
    cycle = 0

    while True:
        cycle += 1
        logger.info(f"Poll cycle {cycle} starting...")

        try:
            # Fetch from both platforms concurrently
            k_markets, p_markets = await asyncio.gather(
                kalshi.fetch(),
                polymarket.fetch(),
                return_exceptions=True,
            )

            if isinstance(k_markets, Exception):
                logger.warning(f"Kalshi fetch failed: {k_markets}")
                k_markets = []
            if isinstance(p_markets, Exception):
                logger.warning(f"Polymarket fetch failed: {p_markets}")
                p_markets = []

            all_markets = list(k_markets) + list(p_markets)
            stored = 0

            for m in all_markets:
                await db.upsert_market(
                    id=m["id"],
                    platform=m["platform"],
                    title=m["title"],
                    category="",
                    keywords=",".join(m["keywords"]),
                    price=m["price"],
                )
                if m["price"] > 0:
                    await db.insert_snapshot(m["id"], m["price"])
                    stored += 1

            logger.info(
                f"Cycle {cycle}: {len(k_markets)} Kalshi + {len(p_markets)} Polymarket = {len(all_markets)} markets, {stored} snapshots stored"
            )

            # Run correlation
            signals = await correlator.run_cycle(db)
            if signals > 0:
                logger.info(f"Cycle {cycle}: {signals} new signals detected!")

        except Exception as e:
            logger.error(f"Poll cycle {cycle} error: {e}")

        await asyncio.sleep(settings.poll_interval)


async def run_server(settings: Settings):
    """Run FastAPI server."""
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def async_main():
    settings = Settings()
    db = Database(settings.db_path)
    await db.init()

    # Attach db to FastAPI app
    app.state.db = db

    logger.info(f"Market Signals starting on http://{settings.host}:{settings.port}")
    logger.info(f"Polling every {settings.poll_interval}s, threshold: {settings.price_change_threshold}%")
    logger.info(f"Database: {settings.db_path}")

    # Run poller and server concurrently
    try:
        await asyncio.gather(
            poll_loop(settings, db),
            run_server(settings),
        )
    except asyncio.CancelledError:
        pass
    finally:
        stats = await db.get_stats()
        logger.info(f"Shutting down. Stats: {stats}")
        await db.close()


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python -m market_signals")
        print()
        print("Starts the Market Signals dashboard.")
        print(f"Dashboard: http://0.0.0.0:8080")
        print(f"Polls Kalshi + Polymarket every 60s.")
        sys.exit(0)

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    main()
