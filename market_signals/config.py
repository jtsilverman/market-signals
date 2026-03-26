from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    poll_interval: int = 60
    price_change_threshold: float = 5.0
    correlation_threshold: float = 0.3
    news_lookback_hours: int = 2
    db_path: str = str(Path.home() / ".market-signals" / "data.db")
    host: str = "0.0.0.0"
    port: int = 8080

    kalshi_base_url: str = "https://api.elections.kalshi.com/trade-api/v2"
    kalshi_market_limit: int = 100
    polymarket_base_url: str = "https://gamma-api.polymarket.com"
    polymarket_market_limit: int = 100
    gdelt_base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc"

    stopwords: set = field(default_factory=lambda: {
        "will", "the", "a", "an", "in", "on", "at", "to", "of", "is", "be",
        "by", "or", "and", "for", "with", "from", "this", "that", "it",
        "not", "are", "was", "were", "has", "have", "had", "do", "does",
        "did", "but", "if", "than", "then", "so", "no", "yes", "any",
        "before", "after", "above", "below", "between", "during", "about",
    })
