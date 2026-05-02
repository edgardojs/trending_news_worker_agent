# Software Requirements Specification (SRS)

# Trending News Worker Agent Build Specification

**Version:** 1.0  
**Date:** 2026-05-02  
**Target Platform:** Debian GNU/Linux 12 Bookworm  
**Target Hardware:** Intel i3 M330, 8GB RAM  
**Primary Constraint:** Lightweight standalone worker under 500MB RAM  
**Implementation Decision:** Standalone Python worker with SQLite-first cache, optional async fetching, optional Redis/Docker later

---

## 1. Purpose

This SRS defines the requirements for an agent to build a lightweight Google Trends + RSS Trending News Worker.

The worker shall fetch Google Trends RSS/Atom data, fetch configured RSS news feeds, normalize both datasets, match articles against trending search terms, score article relevance, deduplicate near-duplicates, rank the results, and produce JSON and Markdown reports.

The recommended implementation is a **standalone Python CLI worker using SQLite as the default cache and persistence layer**. Redis, Docker, Caddy, OpenClaw integration, and ML/NLP features are explicitly deferred to later phases unless requested separately.

---

## 2. Recommended Decision

The agent shall implement the project using this design:

```text
Standalone Python worker
+ async or concurrent feed fetching
+ SQLite-first cache
+ Redis optional later
+ Docker optional later
+ OpenClaw integration later
```

The worker shall be runnable as:

```bash
python worker.py --config config.yaml
```

The first build must prioritize:

1. Reliability on low-spec hardware.
2. Deterministic output.
3. Low memory usage.
4. Easy debugging from terminal logs and local files.
5. No hard dependency on Redis, Docker, OpenClaw, or heavy ML.

---

## 3. Scope

## 3.1 In Scope for Version 1

The agent shall build:

- A standalone Python command-line worker.
- YAML-based configuration loading.
- Google Trends RSS/Atom ingestion.
- RSS news feed ingestion.
- Data normalization.
- Fuzzy matching using `rapidfuzz`.
- Composite trend scoring.
- Near-duplicate article detection.
- Ranked output generation.
- JSON report output.
- Markdown report output.
- SQLite cache and run history.
- Structured JSON Lines logging.
- Basic retry and failure handling.
- Cron-compatible execution.
- Health check script.
- Basic unit tests for core modules.

## 3.2 Out of Scope for Version 1

The agent shall not implement these in v1:

- LLM summarization.
- Embeddings.
- Transformers.
- PyTorch.
- TensorFlow.
- Heavy NLP pipelines.
- Web dashboard.
- OpenClaw gateway integration.
- Email delivery.
- Real-time WebSocket streaming.
- Multi-worker Celery architecture.
- Mandatory Redis.
- Mandatory Docker Compose.

These may be added in later phases after the standalone worker passes acceptance criteria.

---

## 4. System Architecture

## 4.1 Version 1 Architecture

```text
config.yaml
    ↓
worker.py
    ↓
Load config
    ↓
Fetch Google Trends RSS/Atom
    ↓
Fetch configured RSS feeds
    ↓
Normalize trends and articles
    ↓
Match articles to trends
    ↓
Score articles
    ↓
Deduplicate articles
    ↓
Rank top articles
    ↓
Write JSON report
Write Markdown report
Write structured logs
Persist cache/run data to SQLite
```

## 4.2 Version 1 Runtime Model

The worker shall run as a single process.

No background daemon is required.

The worker shall be compatible with:

```bash
python worker.py --config config.yaml
```

and with cron:

```cron
*/30 * * * * cd /opt/trending-news-worker && /usr/bin/python3 worker.py --config config.yaml
```

---

## 5. Constraints

## 5.1 Hardware Constraints

The worker shall operate within these target constraints:

| Constraint | Requirement |
|---|---|
| CPU | Intel i3 M330 or equivalent low-spec CPU |
| RAM | 8GB system RAM |
| Worker memory | Less than 500MB peak |
| Preferred memory | Less than 300MB typical |
| Execution window | Less than 5 minutes |
| OS | Debian 12 Bookworm |
| Python | Python 3.11+ |

## 5.2 Dependency Constraints

The worker shall avoid heavy dependencies.

Allowed core packages:

```text
httpx
feedparser
pyyaml
pydantic or dataclasses
rapidfuzz
aiosqlite or sqlite3
python-dateutil
tenacity
python-json-logger
```

The agent shall not add heavy ML/NLP packages unless explicitly requested in a future phase.

Forbidden for v1:

```text
transformers
torch
tensorflow
sentence-transformers
spacy large models
local LLM runtime requirements
```

---

## 6. Functional Requirements

## FR-01: Configuration Loading

The worker shall load configuration from `config.yaml` at startup.

The agent may use either Pydantic or dataclasses for validation.

Required configuration sections:

```yaml
general:
  output_dir: "./output"
  log_dir: "./logs"
  cache_dir: "./cache"
  log_level: "INFO"

trends:
  feeds:
    - "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
  geo: "US"
  window_hours: 24
  max_trends: 50

rss:
  feeds:
    - "http://feeds.bbci.co.uk/news/rss.xml"
    - "http://rss.cnn.com/rss/edition.rss"
  timeout_seconds: 30
  max_articles_per_feed: 100
  user_agent: "TrendingNewsWorker/1.0"

scoring:
  trend_match_weight: 0.6
  recency_weight: 0.2
  source_authority_weight: 0.2
  fuzzy_threshold: 85

output:
  formats:
    - "json"
    - "markdown"
  max_ranked_articles: 20
  include_scores: true
  include_trend_matches: true

cache:
  backend: "sqlite"
  enabled: true
  ttl_seconds: 3600
  sqlite_path: "./cache/trending_news.db"
  redis_enabled: false

deduplication:
  enabled: true
  method: "fuzzy"
  threshold: 85
```

If the configuration is missing or invalid, the worker shall log the error and exit with code `1`.

---

## FR-02: Google Trends Fetching

The worker shall fetch Google Trends RSS/Atom feeds from the configured `trends.feeds` list.

Each trend item shall be normalized into this internal structure:

```json
{
  "id": "hash(title+timestamp)",
  "title": "trending search term",
  "link": "https://trends.google.com/...",
  "timestamp": "2026-05-02T10:00:00Z",
  "search_volume": "100K+",
  "geo": "US"
}
```

If all trend fetches fail, the worker shall:

1. Attempt to use cached trends if available and fresh enough.
2. Log a warning if using stale cache.
3. Continue with an empty trends list only if no cache exists.
4. Never crash solely because one trends feed failed.

---

## FR-03: RSS Feed Ingestion

The worker shall fetch configured RSS feeds.

Each article shall be normalized into this internal structure:

```json
{
  "id": "hash(title+link)",
  "title": "Article headline",
  "link": "https://example.com/article",
  "summary": "Brief description",
  "published": "2026-05-02T08:00:00Z",
  "source": {
    "name": "BBC News",
    "url": "http://feeds.bbci.co.uk/news/rss.xml",
    "authority_score": 0.9
  }
}
```

If a single RSS feed fails, the worker shall:

1. Log the failure.
2. Skip that feed.
3. Continue with remaining feeds.
4. Exit successfully if at least one feed was processed.

---

## FR-04: Normalization

The worker shall normalize trend titles and article fields.

Normalization shall include:

1. Lowercasing text.
2. Trimming whitespace.
3. Removing excessive punctuation.
4. Retaining alphanumeric characters, spaces, and basic punctuation.
5. Parsing dates into ISO 8601 UTC.
6. Extracting source domains from URLs.
7. Optionally removing stopwords if implemented without heavy NLP dependencies.

---

## FR-05: Matching

The worker shall match articles to trends using `rapidfuzz`.

The matching algorithm shall calculate:

```text
fuzz.ratio
fuzz.partial_ratio
fuzz.token_set_ratio
```

The best match score shall be:

```text
best_score = max(ratio, partial_ratio, token_set_ratio)
```

An article shall be considered matched to a trend if:

```text
best_score >= scoring.fuzzy_threshold
```

Default threshold:

```text
85
```

---

## FR-06: Scoring

The worker shall calculate a composite trend score for each article.

Formula:

```text
final_score =
  (trend_match_score * trend_match_weight)
+ (recency_score * recency_weight)
+ (authority_score * source_authority_weight)
```

Default weights:

```text
trend_match_weight = 0.6
recency_weight = 0.2
source_authority_weight = 0.2
```

Recency score shall use exponential decay:

```text
recency_score = 100 * e^(-hours_ago / 24)
```

Authority score shall be normalized from `0.0-1.0` into `0-100`.

If no authority score is configured for a source, the worker shall use a default authority score of `0.5`.

---

## FR-07: Deduplication

The worker shall remove or group near-duplicate articles.

Default behavior:

1. Compare normalized titles using fuzzy matching.
2. Treat articles as duplicates if similarity is greater than or equal to `deduplication.threshold`.
3. Keep the article with the highest final trend score.
4. Preserve duplicate references in metadata if practical.

Default threshold:

```text
85
```

---

## FR-08: Ranking

The worker shall rank articles by descending `final_score`.

The worker shall limit output to:

```yaml
output:
  max_ranked_articles: 20
```

Tie-breaking order:

1. Higher trend score.
2. Newer publication timestamp.
3. Higher source authority.
4. Alphabetical title order for deterministic output.

---

## FR-09: JSON Output

The worker shall write a JSON report to the configured output directory.

Required JSON structure:

```json
{
  "generated_at": "2026-05-02T10:30:00Z",
  "run_id": "trending_news_20260502_103000",
  "config": {
    "geo": "US",
    "window_hours": 24
  },
  "summary": {
    "total_articles_fetched": 487,
    "articles_matched": 42,
    "articles_after_dedup": 28
  },
  "ranked_articles": [
    {
      "rank": 1,
      "title": "Example trending news",
      "link": "https://example.com/article",
      "source": "BBC News",
      "published": "2026-05-02T08:00:00Z",
      "trend_score": 94.2,
      "matched_trends": [
        {
          "trend": "climate summit",
          "match_score": 96
        }
      ]
    }
  ],
  "top_trends": [
    {
      "trend": "climate summit",
      "volume": "500K+"
    }
  ]
}
```

The output filename shall use this format:

```text
trending_news_YYYYMMDD_HHMMSS.json
```

---

## FR-10: Markdown Output

The worker shall write a Markdown report to the configured output directory.

The Markdown report shall include:

1. Title.
2. Generated timestamp.
3. Run ID.
4. Summary statistics.
5. Top trends.
6. Ranked article list.
7. Score details if enabled.
8. Source links.
9. Warnings if any feeds failed.

The output filename shall use this format:

```text
trending_news_YYYYMMDD_HHMMSS.md
```

---

## FR-11: SQLite Cache and Persistence

The worker shall use SQLite as the default cache and persistence backend.

Required database path:

```text
./cache/trending_news.db
```

Required tables:

```sql
CREATE TABLE IF NOT EXISTS rss_cache (
    feed_url TEXT PRIMARY KEY,
    response_blob TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    etag TEXT,
    last_modified TEXT
);

CREATE TABLE IF NOT EXISTS trends_cache (
    cache_key TEXT PRIMARY KEY,
    trends_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    geo TEXT NOT NULL,
    window_hours INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT,
    output_hash TEXT
);

CREATE TABLE IF NOT EXISTS processed_articles (
    article_hash TEXT PRIMARY KEY,
    title TEXT,
    link TEXT,
    source TEXT,
    trend_score REAL,
    run_id TEXT,
    processed_at TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_trends_cache_geo_window
ON trends_cache(geo, window_hours);

CREATE INDEX IF NOT EXISTS idx_runs_completed_at
ON runs(completed_at);

CREATE INDEX IF NOT EXISTS idx_articles_trend_score
ON processed_articles(trend_score);
```

---

## FR-12: Logging

The worker shall write structured JSON Lines logs.

Required log fields:

```json
{
  "timestamp": "2026-05-02T10:30:00Z",
  "level": "INFO",
  "run_id": "trending_news_20260502_103000",
  "component": "rss",
  "message": "Fetched feed successfully",
  "duration_ms": 1200
}
```

Logs shall be written to:

```text
./logs/worker_YYYYMMDD.log
```

---

## FR-13: Failure Handling

The worker shall handle failures gracefully.

| Failure Scenario | Required Behavior | Exit Code |
|---|---|---:|
| Missing config | Log error and exit | 1 |
| Invalid config | Log validation error and exit | 1 |
| Network unreachable | Retry, then fail if no cached data available | 2 |
| Single RSS feed timeout | Log warning, skip feed, continue | 0 |
| All RSS feeds fail | Log error, exit unless cached data is available | 2 |
| All trends feeds fail | Use cache if available; otherwise continue with warning | 0 |
| SQLite write error | Log error and attempt fallback output-only mode | 3 |
| Output directory unwritable | Log error and exit | 4 |
| Memory pressure/OOM risk | Log critical, flush partial output if possible | 5 |

---

## 7. Non-Functional Requirements

## NFR-01: Performance

The worker shall complete a full run in less than 5 minutes.

Target execution time:

```text
30-90 seconds typical
under 300 seconds worst acceptable case
```

## NFR-02: Memory Efficiency

The worker shall use less than 500MB RAM peak.

The agent shall avoid storing unnecessary large objects in memory.

Recommended strategies:

- Limit articles per feed.
- Use streaming or bounded lists where practical.
- Avoid storing raw feed blobs in memory after parsing.
- Run garbage collection after large fetch/parse steps if necessary.
- Avoid full-text article scraping in v1.

## NFR-03: Idempotency

Given the same input data and same timestamp/run seed, the worker shall produce deterministic output.

The worker shall compute and store an output hash in SQLite.

## NFR-04: Debuggability

The worker shall be easy to inspect using only terminal tools.

Required artifacts:

```text
output/*.json
output/*.md
logs/*.log
cache/trending_news.db
```

## NFR-05: Portability

The v1 worker shall run directly on Debian 12 without Docker.

Docker support may be added later, but the native Python run path must remain supported.

---

## 8. File Layout

The agent shall create this project structure:

```text
trending-news-worker/
├── worker.py
├── config.yaml
├── requirements.txt
├── README.md
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── trends.py
│   ├── rss.py
│   ├── normalize.py
│   ├── matcher.py
│   ├── scorer.py
│   ├── deduplicate.py
│   ├── ranker.py
│   ├── outputs.py
│   ├── cache_sqlite.py
│   ├── logging_setup.py
│   └── exceptions.py
├── output/
├── logs/
├── cache/
├── tests/
│   ├── test_config.py
│   ├── test_trends.py
│   ├── test_rss.py
│   ├── test_matcher.py
│   ├── test_scorer.py
│   └── test_deduplicate.py
└── scripts/
    ├── run.sh
    ├── cron_setup.sh
    └── health_check.py
```

---

## 9. Implementation Phases

## Phase 1: Minimal Reliable Worker

The agent shall implement:

```text
config.py
trends.py
rss.py
normalize.py
matcher.py
scorer.py
deduplicate.py
ranker.py
outputs.py
cache_sqlite.py
logging_setup.py
worker.py
```

Phase 1 completion means:

- Worker runs from CLI.
- Fetches trends.
- Fetches RSS feeds.
- Scores and ranks articles.
- Writes JSON and Markdown.
- Logs structured events.
- Uses SQLite cache.

---

## Phase 2: Hardening

The agent shall add:

```text
retry/backoff
cache expiration
ETag support if available
Last-Modified support if available
output hashing
idempotency checks
health_check.py
cron runner
unit tests
```

Phase 2 completion means:

- The worker survives partial feed failures.
- Cache improves repeated run performance.
- Health check reports useful status.
- Unit tests validate scoring, matching, and deduplication.

---

## Phase 3: Optional Service Mode

Only after Phase 1 and Phase 2 pass, the agent may add:

```text
Dockerfile
docker-compose.yml
optional Redis backend
optional Caddy static output viewer
```

Docker and Redis shall remain optional.

The native Python worker must remain the primary supported path.

---

## Phase 4: Optional OpenClaw Integration

Only after the worker is stable, the agent may expose the worker as an OpenClaw skill.

Possible commands:

```text
trending-news run
trending-news latest
trending-news health
trending-news summarize-latest
trending-news email-report
```

OpenClaw integration shall call the worker as a deterministic subprocess or library function.

The ranking engine must remain usable without OpenClaw.

---

## 10. Acceptance Criteria

| ID | Criteria | Verification |
|---|---|---|
| AC-01 | Loads valid `config.yaml` | Run worker with sample config |
| AC-02 | Fails cleanly on invalid config | Run with malformed config |
| AC-03 | Fetches at least one Google Trends feed | Check logs and output JSON |
| AC-04 | Fetches at least three RSS feeds | Check summary counts |
| AC-05 | Single RSS failure does not crash worker | Use one invalid feed URL |
| AC-06 | Produces valid JSON output | Validate with `jq` |
| AC-07 | Produces readable Markdown output | Open generated `.md` file |
| AC-08 | Scores articles using configured weights | Unit test scorer |
| AC-09 | Deduplicates near-identical titles | Unit test deduplication |
| AC-10 | Ranks articles by descending score | Inspect output order |
| AC-11 | Completes under 5 minutes | Run with `time` |
| AC-12 | Uses less than 500MB RAM | Monitor with `ps`, `top`, or `/usr/bin/time -v` |
| AC-13 | Writes structured logs | Inspect `logs/*.log` |
| AC-14 | Writes and reuses SQLite cache | Inspect `cache/trending_news.db` |
| AC-15 | Can run from cron | Run via `scripts/run.sh` |
| AC-16 | Health check returns OK after successful run | Run `scripts/health_check.py` |

---

## 11. Minimal `requirements.txt`

The agent shall begin with this dependency set:

```text
httpx==0.27.0
feedparser==6.0.11
pyyaml==6.0.1
pydantic==2.7.0
rapidfuzz==3.9.0
aiosqlite==0.20.0
python-dateutil==2.9.0
tenacity==8.2.3
python-json-logger==2.0.7
```

Redis shall not be included in the default v1 requirements unless the optional Redis backend is implemented.

---

## 12. Minimal `run.sh`

The agent shall create a simple runner script:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python3 worker.py --config config.yaml
```

---

## 13. Minimal Health Check

The agent shall create `scripts/health_check.py`.

Health check behavior:

1. Find the newest JSON output file.
2. Fail if no output exists.
3. Warn if newest output is older than two hours.
4. Validate that `ranked_articles` exists.
5. Warn if zero articles were ranked.
6. Print a human-readable status line.

---

## 14. Agent Build Instructions

The implementation agent shall follow these priorities:

1. Build the standalone Python worker first.
2. Keep all modules small and testable.
3. Avoid heavy dependencies.
4. Use SQLite as the default cache.
5. Make Redis optional, not required.
6. Make Docker optional, not required.
7. Do not implement OpenClaw integration until the standalone worker is stable.
8. Do not implement ML, LLM, embeddings, or article scraping in v1.
9. Preserve deterministic output ordering.
10. Fail gracefully and continue when individual feeds fail.

---

## 15. Final Implementation Target

The successful v1 build shall allow this workflow:

```bash
git clone <repo>
cd trending-news-worker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
python worker.py --config config.yaml
ls output/
ls logs/
```

Expected result:

```text
output/trending_news_YYYYMMDD_HHMMSS.json
output/trending_news_YYYYMMDD_HHMMSS.md
logs/worker_YYYYMMDD.log
cache/trending_news.db
```

The worker is considered complete when it can run repeatedly on the target Debian 12 machine without exceeding the memory limit, without requiring Docker, and without crashing when individual feeds fail.

---

## 16. Summary Decision

The agent shall build a **SQLite-first standalone Python worker**.

This is the best implementation path because it matches the hardware limits, avoids unnecessary service overhead, keeps the system debuggable, and still leaves a clean path for later Docker, Redis, OpenClaw, email, dashboard, or self-learning extensions.

