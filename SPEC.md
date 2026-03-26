# Market Signals

## Overview

A real-time dashboard that polls prediction market contracts from Kalshi and Polymarket, correlates price movements with timestamped news events from GDELT, and highlights which news actually moved markets vs. noise. Shows a live feed of market/news pairs ranked by price impact. No existing tool does this cross-platform correlation.

## Scope

- **Timebox:** 2 days
- **Building:**
  - Poller that fetches Kalshi and Polymarket market data every 60 seconds
  - GDELT news fetcher that pulls recent articles by keyword
  - Price change detector (flags moves > 5% in a window)
  - News-to-market correlator: matches news articles to relevant markets by keyword overlap + timestamp proximity
  - SQLite storage for price snapshots and news events
  - Web dashboard (Chart.js) showing: price time series with news event markers, ranked signal feed, market browser
  - CLI mode: `python -m market_signals` runs poller + serves dashboard
- **Not building:**
  - Real-time WebSocket streaming (polling is fine for MVP)
  - Causal inference or statistical significance testing
  - Trading signals or recommendations
  - User accounts, alerts, or notifications
  - Polymarket price history (API returns empty; we build our own via polling)
- **Ship target:** GitHub + PyPI (`pip install market-signals`) + optional Railway deploy

## Project Type

**Pure code** (Python backend + static web frontend, no AI/agent)

## Stack

- **Backend:** Python 3.12, aiohttp (async polling), SQLite (via aiosqlite), FastAPI (serves API + dashboard)
- **Frontend:** Static HTML + Chart.js + vanilla JS (no build step, served by FastAPI)
- **Why:** Python is natural for data pipelines and time series. aiohttp for concurrent API polling. SQLite for zero-config persistence. Static frontend with Chart.js avoids another heavy framework while producing clean interactive charts. Different pattern from ARC (React+Vite) and mcpprof (pure Node CLI).

## Architecture

### Directory Structure

```
market-signals/
  market_signals/
    __init__.py
    __main__.py        # CLI entry point
    config.py          # Settings, poll intervals
    db.py              # SQLite schema + queries
    poller.py          # Async market data fetcher
    news.py            # GDELT news fetcher
    correlator.py      # Price change detection + news matching
    api.py             # FastAPI routes
  static/
    index.html         # Dashboard UI
    app.js             # Chart.js rendering + API calls
    style.css
  pyproject.toml
  README.md
```

### Data Models (SQLite)

```sql
CREATE TABLE markets (
  id TEXT PRIMARY KEY,          -- "kalshi:TICKER" or "polymarket:conditionId"
  platform TEXT NOT NULL,       -- "kalshi" or "polymarket"
  title TEXT NOT NULL,
  category TEXT,
  keywords TEXT,                -- extracted from title, comma-separated
  last_price REAL,
  last_updated INTEGER          -- unix timestamp
);

CREATE TABLE price_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  market_id TEXT NOT NULL,
  price REAL NOT NULL,
  timestamp INTEGER NOT NULL,
  FOREIGN KEY (market_id) REFERENCES markets(id)
);

CREATE TABLE news_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT UNIQUE,
  title TEXT NOT NULL,
  source TEXT,
  published INTEGER NOT NULL,   -- unix timestamp
  keywords TEXT,                 -- extracted, comma-separated
  fetched INTEGER NOT NULL
);

CREATE TABLE signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  market_id TEXT NOT NULL,
  news_id INTEGER,
  price_before REAL,
  price_after REAL,
  price_change REAL,            -- percentage
  timestamp INTEGER NOT NULL,
  correlation_score REAL,       -- keyword overlap + time proximity score
  FOREIGN KEY (market_id) REFERENCES markets(id),
  FOREIGN KEY (news_id) REFERENCES news_events(id)
);
```

### API Contract

```
GET  /api/markets
  Response: [{ id, platform, title, last_price, price_change_1h, price_change_24h }]

GET  /api/markets/{id}/history
  Query: ?hours=24
  Response: { prices: [{ timestamp, price }], events: [{ timestamp, title, url, impact }] }

GET  /api/signals
  Query: ?limit=20&min_change=5
  Response: [{ market_title, news_title, price_change, correlation_score, timestamp }]

GET  /api/news
  Query: ?limit=20
  Response: [{ title, url, source, published, matched_markets }]

GET  /api/stats
  Response: { total_markets, total_snapshots, total_signals, uptime_seconds }
```

### Polling Flow

```
Every 60s:
  1. Fetch Kalshi markets (GET /trade-api/v2/markets?limit=100&status=open)
  2. Fetch Polymarket markets (GET gamma-api/markets?active=true&limit=100)
  3. Store price snapshots in SQLite
  4. Detect price changes > 5% in last hour
  5. Fetch GDELT news for keywords from changed markets
  6. Score news-market correlations (keyword overlap * time proximity)
  7. Store signals
```

### Correlation Algorithm

For each price change > threshold:
1. Extract keywords from market title (split on spaces, remove stopwords)
2. Fetch GDELT articles matching those keywords from the last 2 hours
3. For each article, compute score = keyword_overlap_ratio * time_proximity_factor
   - keyword_overlap_ratio = matched_keywords / total_market_keywords
   - time_proximity_factor = max(0, 1 - abs(news_time - price_change_time) / 7200)
4. If score > 0.3, create a signal

## Task List

### Phase 1: Project Setup

#### Task 1.1: Scaffold Python Project
**Files:** `pyproject.toml` (create), `market_signals/__init__.py` (create), `market_signals/config.py` (create)
**Do:** Create pyproject.toml with project metadata, dependencies (aiohttp, aiosqlite, fastapi, uvicorn), and console script entry point. Create config.py with settings: POLL_INTERVAL=60, PRICE_CHANGE_THRESHOLD=5.0, DB_PATH, KALSHI_BASE_URL, POLYMARKET_BASE_URL, GDELT_BASE_URL.
**Validate:** `pip install -e . && python -c "from market_signals.config import Settings; print(Settings())"`

### Phase 2: Data Layer

#### Task 2.1: Database Setup
**Files:** `market_signals/db.py` (create)
**Do:** Create async SQLite manager. init_db() creates tables if not exist. Functions: upsert_market(), insert_snapshot(), insert_news(), insert_signal(), get_markets(), get_history(market_id, hours), get_signals(limit, min_change), get_news(limit), get_stats(). All async using aiosqlite.
**Validate:** `python -c "import asyncio; from market_signals.db import Database; db = Database(':memory:'); asyncio.run(db.init()); asyncio.run(db.upsert_market('test:1','kalshi','Test Market','test','test',0.5)); markets = asyncio.run(db.get_markets()); assert len(markets)==1; print('PASS')"`

#### Task 2.2: Market Pollers
**Files:** `market_signals/poller.py` (create)
**Do:** Create KalshiPoller and PolymarketPoller classes, both with async fetch() method returning list of normalized market dicts {id, platform, title, price, keywords}. KalshiPoller hits /trade-api/v2/markets. PolymarketPoller hits gamma-api/markets. Both use aiohttp session. Extract keywords from title (lowercase, split, remove common stopwords). Handle API errors gracefully (log and skip).
**Validate:** `python -c "import asyncio; from market_signals.poller import KalshiPoller, PolymarketPoller; kp=KalshiPoller(); pp=PolymarketPoller(); k=asyncio.run(kp.fetch()); p=asyncio.run(pp.fetch()); print(f'Kalshi: {len(k)}, Polymarket: {len(p)}'); assert len(k)>0; assert len(p)>0; print('PASS')"`

#### Task 2.3: News Fetcher
**Files:** `market_signals/news.py` (create)
**Do:** Create GDELTFetcher with async fetch(keywords, hours=2) method. Hits GDELT doc API with keywords query, returns list of {url, title, source, published_ts, keywords}. Parse GDELT date format. Deduplicate by URL. Handle empty results and API errors.
**Validate:** `python -c "import asyncio; from market_signals.news import GDELTFetcher; f=GDELTFetcher(); articles=asyncio.run(f.fetch(['trump','tariff'])); print(f'Articles: {len(articles)}'); print('PASS')"`

### Phase 3: Correlation Engine

#### Task 3.1: Price Change Detection and Correlation
**Files:** `market_signals/correlator.py` (create)
**Do:** Create Correlator class. detect_changes(db, threshold_pct) queries price_snapshots for markets with >threshold% change in last hour. correlate(market, news_articles) computes keyword overlap and time proximity scores. run_cycle(db, news_fetcher) orchestrates: detect changes, fetch news for changed markets, score correlations, store signals. All async.
**Validate:** `python -c "from market_signals.correlator import compute_correlation_score; score = compute_correlation_score(['trump','tariff','trade'], ['trump','tariff','china'], 0); assert 0 < score <= 1; print(f'Score: {score:.2f}'); print('PASS')"`

### Phase 4: API and Dashboard

#### Task 4.1: FastAPI Routes
**Files:** `market_signals/api.py` (create)
**Do:** Create FastAPI app. Mount /static for the dashboard. Routes: GET /api/markets (list with 1h and 24h price changes computed from snapshots), GET /api/markets/{id}/history (price series + news events), GET /api/signals (ranked by correlation score), GET /api/news (recent), GET /api/stats. All read from SQLite.
**Validate:** `python -c "from market_signals.api import app; from fastapi.testclient import TestClient; c=TestClient(app); assert c.get('/api/stats').status_code==200; print('PASS')"`

#### Task 4.2: Web Dashboard
**Files:** `static/index.html` (create), `static/app.js` (create), `static/style.css` (create)
**Do:** Single-page dashboard. Top: stats bar (markets tracked, signals found, uptime). Middle: two panels. Left: signal feed (cards showing market title, news title, price change %, correlation score, sorted by recency). Right: market chart (select a market, shows Chart.js line chart of price over time with vertical markers for correlated news events). Bottom: market browser table (sortable by price change). Dark theme. Fetch data from /api/* endpoints. Auto-refresh every 30 seconds.
**Validate:** `ls static/index.html static/app.js static/style.css && python -c "from market_signals.api import app; from fastapi.testclient import TestClient; c=TestClient(app); r=c.get('/'); assert r.status_code==200; assert 'Market Signals' in r.text; print('PASS')"`

### Phase 5: CLI and Main Loop

#### Task 5.1: Main Loop and CLI
**Files:** `market_signals/__main__.py` (create), `market_signals/api.py` (modify)
**Do:** Create __main__.py as CLI entry point. Initializes database, creates pollers and correlator, starts async main loop: every POLL_INTERVAL seconds, fetch markets from both platforms, store snapshots, run correlation cycle. Concurrently starts FastAPI server on port 8080. Handles SIGINT gracefully (print stats, close db). Wire the database instance into the API app via app.state.
**Validate:** Start the app, wait 5 seconds, check endpoints: `python -m market_signals & sleep 8 && curl -sf http://localhost:8080/api/stats | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['total_markets']>0; print(f'PASS: {d[\"total_markets\"]} markets tracked')" && kill %1`

### Phase 6: End-to-End Integration Test

#### Task 6.1: Integration Test
**Files:** `tests/integration.py` (create)
**Do:** Start the full app, wait for 2 poll cycles (~130 seconds). Verify: /api/markets returns > 0 markets from both platforms. /api/markets/{id}/history returns price points. /api/stats shows total_snapshots > 0. /api/news or /api/signals responds (may be empty if no price changes). Dashboard HTML loads with correct title. Kill app cleanly.
**Validate:** `python tests/integration.py`

### Phase 7: Ship

#### Task 7.1: README and Package Config
**Files:** `README.md` (create), `.gitignore` (create)
**Do:** Portfolio-ready README (problem, demo screenshot placeholder, how it works, install, usage, API docs, tech stack, the hard part, license). .gitignore for __pycache__, *.db, .env, dist.
**Validate:** `pip install -e . && python -m market_signals --help`

## The One Hard Thing

**Meaningful news-to-market correlation without false positives.**

Why it's hard: Markets move for many reasons (organic trading, whale activity, market maker adjustments) and news articles are noisy (duplicate stories, irrelevant matches, delayed reporting). Naive keyword matching produces too many false signals.

Proposed approach: Two-factor scoring: keyword overlap ratio (how many market keywords appear in the article) times time proximity factor (exponential decay from the price change timestamp). Only surface signals above a 0.3 threshold. This is simple but surprisingly effective because prediction markets are topical (their titles contain the exact keywords that news articles use).

Fallback: If keyword matching is too noisy, switch to using Perplexity or Gemini for semantic similarity between market question and news headline. More expensive but more accurate. Both approaches are independently viable.

## Risks

- **API rate limits (medium):** Kalshi and Polymarket are public but may rate-limit aggressive polling. Mitigation: 60-second intervals, respect rate limit headers, cache results.
- **GDELT data quality (medium):** GDELT articles are scraped broadly, may include irrelevant sources. Mitigation: filter by English language, exclude known spam domains.
- **Polymarket price history (low):** Their history endpoint returns empty for most markets. Mitigation: we build our own history via polling (this is the plan anyway).
- **Correlation noise (medium):** Many false positives possible. Mitigation: threshold tuning, time proximity weighting, expose raw scores so users can judge.
- **Scope (low):** Well-scoped. Polling + storage + correlation + dashboard, each is straightforward. The correlation quality is the variable.
