import logging
import time

from .config import Settings
from .db import Database
from .news import GDELTFetcher

logger = logging.getLogger(__name__)


def compute_correlation_score(
    market_keywords: list[str],
    article_keywords: list[str],
    time_diff_seconds: float,
    max_time_window: float = 7200,
) -> float:
    """Score how well a news article correlates with a market.

    Returns 0-1 based on keyword overlap * time proximity.
    """
    if not market_keywords or not article_keywords:
        return 0.0

    market_set = set(market_keywords)
    article_set = set(article_keywords)
    overlap = market_set & article_set

    if not overlap:
        return 0.0

    keyword_ratio = len(overlap) / len(market_set)
    time_factor = max(0.0, 1.0 - abs(time_diff_seconds) / max_time_window)

    return round(keyword_ratio * time_factor, 3)


class Correlator:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.news_fetcher = GDELTFetcher(self.settings)

    async def detect_changes(self, db: Database) -> list[dict]:
        """Find markets with price changes above threshold in the last hour."""
        markets = await db.get_markets()
        changed = []

        for m in markets:
            result = await db.get_price_change(m["id"], hours=1.0)
            if result is None:
                continue
            old_price, new_price = result
            if old_price == 0:
                continue
            pct_change = ((new_price - old_price) / old_price) * 100
            if abs(pct_change) >= self.settings.price_change_threshold:
                changed.append({
                    "id": m["id"],
                    "title": m["title"],
                    "old_price": old_price,
                    "new_price": new_price,
                    "pct_change": pct_change,
                })

        return changed

    async def run_cycle(self, db: Database) -> int:
        """Run one correlation cycle. Returns number of signals found."""
        changes = await self.detect_changes(db)
        if not changes:
            return 0

        logger.info(f"Detected {len(changes)} price changes above threshold")
        signal_count = 0

        for change in changes:
            # Extract keywords from market title
            market_keywords = change["title"].lower().split()
            market_keywords = [w for w in market_keywords if len(w) > 2 and w not in self.settings.stopwords]

            if not market_keywords:
                continue

            # Fetch relevant news
            articles = await self.news_fetcher.fetch(
                market_keywords[:5],
                hours=self.settings.news_lookback_hours,
            )

            now = int(time.time())
            for article in articles:
                time_diff = abs(now - article["published_ts"]) if article["published_ts"] > 0 else 7200
                score = compute_correlation_score(
                    market_keywords,
                    article["keywords"],
                    time_diff,
                )

                if score >= self.settings.correlation_threshold:
                    news_id = await db.insert_news(
                        url=article["url"],
                        title=article["title"],
                        source=article["source"],
                        published=article["published_ts"],
                        keywords=",".join(article["keywords"][:10]),
                    )
                    if news_id:
                        await db.insert_signal(
                            market_id=change["id"],
                            news_id=news_id,
                            price_before=change["old_price"],
                            price_after=change["new_price"],
                            price_change=change["pct_change"],
                            correlation_score=score,
                        )
                        signal_count += 1

        return signal_count
