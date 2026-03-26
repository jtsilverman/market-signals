import logging
import re

import aiohttp

from .config import Settings

logger = logging.getLogger(__name__)


def extract_keywords(title: str, stopwords: set[str]) -> list[str]:
    words = re.findall(r'[a-zA-Z]+', title.lower())
    return [w for w in words if len(w) > 2 and w not in stopwords]


class KalshiPoller:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    async def fetch(self) -> list[dict]:
        url = f"{self.settings.kalshi_base_url}/markets"
        params = {"limit": self.settings.kalshi_market_limit, "status": "open"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Kalshi API returned {resp.status}")
                        return []
                    data = await resp.json()
        except Exception as e:
            logger.warning(f"Kalshi fetch error: {e}")
            return []

        markets = []
        for m in data.get("markets", []):
            # Kalshi returns price fields as strings like "0.0300"
            # Try last_price, then yes_ask, then yes_bid as fallbacks
            price = 0.0
            for field in ("last_price_dollars", "yes_ask_dollars", "yes_bid_dollars", "previous_price_dollars"):
                val = m.get(field)
                if val is not None:
                    try:
                        p = float(val)
                        if p > 0:
                            price = p
                            break
                    except (TypeError, ValueError):
                        pass

            title = m.get("title", "")
            keywords = extract_keywords(title, self.settings.stopwords)
            markets.append({
                "id": f"kalshi:{m['ticker']}",
                "platform": "kalshi",
                "title": title,
                "price": price,
                "keywords": keywords,
            })
        return markets


class PolymarketPoller:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    async def fetch(self) -> list[dict]:
        url = f"{self.settings.polymarket_base_url}/markets"
        params = {"limit": self.settings.polymarket_market_limit, "active": "true", "closed": "false"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Polymarket API returned {resp.status}")
                        return []
                    data = await resp.json()
        except Exception as e:
            logger.warning(f"Polymarket fetch error: {e}")
            return []

        raw_markets = data if isinstance(data, list) else data.get("data", [])
        markets = []
        for m in raw_markets:
            # outcomePrices can be a JSON string '["0.096", "0.904"]' or a list
            outcome_prices = m.get("outcomePrices")
            price = 0.0
            if outcome_prices:
                import json as _json
                if isinstance(outcome_prices, str):
                    try:
                        outcome_prices = _json.loads(outcome_prices)
                    except (ValueError, TypeError):
                        outcome_prices = []
                if isinstance(outcome_prices, list) and len(outcome_prices) > 0:
                    try:
                        price = float(str(outcome_prices[0]).strip('"'))
                    except (TypeError, ValueError):
                        price = 0.0

            title = m.get("question", "")
            condition_id = m.get("conditionId", m.get("id", ""))
            keywords = extract_keywords(title, self.settings.stopwords)
            markets.append({
                "id": f"polymarket:{condition_id}",
                "platform": "polymarket",
                "title": title,
                "price": price,
                "keywords": keywords,
            })
        return markets
