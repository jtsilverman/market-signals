import logging
import re
from datetime import datetime

import aiohttp

from .config import Settings

logger = logging.getLogger(__name__)


def parse_gdelt_date(date_str: str) -> int:
    """Parse GDELT date format (e.g., '20260326T160000Z') to unix timestamp."""
    try:
        dt = datetime.strptime(date_str[:15], "%Y%m%dT%H%M%S")
        return int(dt.timestamp())
    except (ValueError, IndexError):
        return 0


class GDELTFetcher:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    async def fetch(self, keywords: list[str], hours: int = 2) -> list[dict]:
        if not keywords:
            return []

        query = " ".join(keywords[:5])  # GDELT has query length limits
        url = self.settings.gdelt_base_url
        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": 20,
            "format": "json",
            "sourcelang": "english",
            "timespan": f"{hours}h",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.warning(f"GDELT API returned {resp.status}")
                        return []
                    data = await resp.json(content_type=None)
        except Exception as e:
            logger.warning(f"GDELT fetch error: {e}")
            return []

        articles = []
        seen_urls = set()
        for a in data.get("articles", []):
            article_url = a.get("url", "")
            if not article_url or article_url in seen_urls:
                continue
            seen_urls.add(article_url)

            title = a.get("title", "")
            title_words = re.findall(r'[a-zA-Z]+', title.lower())
            article_keywords = [w for w in title_words if len(w) > 2]

            articles.append({
                "url": article_url,
                "title": title,
                "source": a.get("domain", ""),
                "published_ts": parse_gdelt_date(a.get("seendate", "")),
                "keywords": article_keywords,
            })

        return articles
