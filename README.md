# Trending News Worker Agent

A lightweight Python CLI worker that fetches Google Trends and RSS news feeds, matches articles to trending topics, scores and ranks them, and produces JSON and Markdown reports.

## Features

- **Google Trends RSS/Atom ingestion** — Fetches trending search terms from configured feeds
- **RSS feed aggregation** — Collects articles from multiple news sources
- **Fuzzy matching** — Matches articles to trends using `rapidfuzz` (ratio, partial_ratio, token_set_ratio)
- **Composite scoring** — Weights trend match, recency, and source authority
- **Near-duplicate detection** — Removes similar articles using fuzzy deduplication
- **Ranked output** — Produces JSON and Markdown reports of top trending articles
- **SQLite cache** — Caches feed data and run history for efficiency
- **Structured logging** — JSON Lines logs for easy parsing and debugging
- **Low resource usage** — Designed to run under 500MB RAM on low-spec hardware

## Quick Start

```bash
# Clone the repository
git clone <repo>
cd trending-news-worker

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and edit configuration (optional)
cp config.yaml config.yaml

# Run the worker
python worker.py --config config.yaml

# Check output
ls output/
ls logs/
```

## Configuration

Configuration is loaded from `config.yaml`. See the file for all available options.

Key sections:
- **general** — Output, log, and cache directories; log level
- **trends** — Google Trends feed URLs, geo, window, max trends
- **rss** — RSS feed URLs, timeout, max articles per feed
- **scoring** — Weights for trend match, recency, authority; fuzzy threshold
- **output** — Formats (json/markdown), max ranked articles, score visibility
- **cache** — SQLite path, TTL, enable/disable
- **deduplication** — Method (fuzzy/exact), threshold

## Architecture

```
config.yaml → worker.py
    ↓
Load config → Fetch Trends → Fetch RSS → Normalize
    ↓
Match → Score → Deduplicate → Rank
    ↓
JSON report + Markdown report + SQLite cache + Structured logs
```

## Project Structure

```
trending-news-worker/
├── worker.py              # Main CLI entry point
├── config.yaml            # Default configuration
├── requirements.txt       # Python dependencies
├── src/
│   ├── __init__.py
│   ├── config.py          # YAML config loading + Pydantic validation
│   ├── trends.py          # Google Trends RSS fetching
│   ├── rss.py             # RSS feed ingestion
│   ├── normalize.py       # Text normalization utilities
│   ├── matcher.py         # Fuzzy matching articles to trends
│   ├── scorer.py          # Composite trend scoring
│   ├── deduplicate.py     # Near-duplicate detection
│   ├── ranker.py           # Article ranking
│   ├── outputs.py         # JSON + Markdown report generation
│   ├── cache_sqlite.py    # SQLite cache and persistence
│   ├── logging_setup.py   # Structured JSON Lines logging
│   └── exceptions.py      # Custom exceptions
├── output/                # Generated reports
├── logs/                  # Structured log files
├── cache/                 # SQLite database
├── tests/                 # Unit tests
└── scripts/
    ├── run.sh             # Simple runner script
    ├── cron_setup.sh      # Cron job setup
    └── health_check.py    # Health check utility
```

## Scoring Formula

```
final_score = (trend_match_score × 0.6) + (recency_score × 0.2) + (authority_score × 0.2)
```

- **Trend match score** — Best fuzzy match score (0-100) from rapidfuzz
- **Recency score** — Exponential decay: `100 × e^(-hours_ago / 24)`
- **Authority score** — Source authority (0-100), based on known news sources

## Cron Setup

```bash
# Run every 30 minutes
*/30 * * * * cd /opt/trending-news-worker && /usr/bin/python3 worker.py --config config.yaml
```

Or use the setup script:
```bash
bash scripts/cron_setup.sh
```

## Health Check

```bash
python scripts/health_check.py --output-dir ./output
```

Checks:
1. Newest JSON output exists
2. Output is less than 2 hours old
3. `ranked_articles` field is present
4. Warns if zero articles ranked

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Configuration error |
| 2 | Network error (no cached data available) |
| 3 | SQLite write error |
| 4 | Output directory unwritable |
| 5 | Unexpected error / OOM |

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## Hardware Requirements

- **CPU:** Intel i3 M330 or equivalent
- **RAM:** < 500MB peak, < 300MB typical
- **Execution:** < 5 minutes per run
- **OS:** Debian 12 Bookworm
- **Python:** 3.11+

## License

See repository for license information.