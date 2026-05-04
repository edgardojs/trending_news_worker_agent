"""SQLite cache and persistence layer for the Trending News Worker Agent."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import AppConfig
from src.exceptions import CacheError


SCHEMA_SQL = """
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
"""


class CacheDB:
    """SQLite cache manager for the trending news worker."""

    def __init__(self, config: AppConfig) -> None:
        self.db_path = Path(config.cache.sqlite_path)
        self.ttl_seconds = config.cache.ttl_seconds
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Open a connection to the SQLite database and initialize schema."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(SCHEMA_SQL)
            self._conn.commit()
        except sqlite3.Error as e:
            raise CacheError(f"Failed to initialize database: {e}") from e

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> CacheDB:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # --- RSS Cache ---

    def get_rss_cache(
        self, feed_url: str
    ) -> dict[str, Any] | None:
        """Get cached RSS data for a feed URL if still fresh.

        Args:
            feed_url: The RSS feed URL to look up.

        Returns:
            Cached data dict or None if not found or stale.
        """
        if not self._conn:
            raise CacheError("Database not connected")

        row = self._conn.execute(
            "SELECT * FROM rss_cache WHERE feed_url = ?", (feed_url,)
        ).fetchone()

        if row is None:
            return None

        fetched_at = datetime.fromisoformat(row["fetched_at"])
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()

        if age > self.ttl_seconds:
            return None

        return {
            "feed_url": row["feed_url"],
            "response_blob": row["response_blob"],
            "fetched_at": row["fetched_at"],
            "etag": row["etag"],
            "last_modified": row["last_modified"],
        }

    def save_rss_cache(
        self,
        feed_url: str,
        response_blob: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> None:
        """Save RSS feed data to cache.

        Args:
            feed_url: The RSS feed URL.
            response_blob: The raw response content.
            etag: Optional ETag header value.
            last_modified: Optional Last-Modified header value.
        """
        if not self._conn:
            raise CacheError("Database not connected")

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO rss_cache
            (feed_url, response_blob, fetched_at, etag, last_modified)
            VALUES (?, ?, ?, ?, ?)
            """,
            (feed_url, response_blob, now, etag, last_modified),
        )
        self._conn.commit()

    # --- Trends Cache ---

    def get_trends_cache(
        self, geo: str, window_hours: int
    ) -> list[dict[str, Any]] | None:
        """Get cached trends data if still fresh.

        Args:
            geo: Geographic region code (e.g., "US").
            window_hours: Time window in hours.

        Returns:
            List of trend dicts or None if not found or stale.
        """
        if not self._conn:
            raise CacheError("Database not connected")

        cache_key = f"trends_{geo}_{window_hours}"

        row = self._conn.execute(
            "SELECT * FROM trends_cache WHERE cache_key = ?", (cache_key,)
        ).fetchone()

        if row is None:
            return None

        fetched_at = datetime.fromisoformat(row["fetched_at"])
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()

        if age > self.ttl_seconds:
            return None

        return json.loads(row["trends_json"])

    def save_trends_cache(
        self, geo: str, window_hours: int, trends: list[dict[str, Any]]
    ) -> None:
        """Save trends data to cache.

        Args:
            geo: Geographic region code.
            window_hours: Time window in hours.
            trends: List of trend data dicts.
        """
        if not self._conn:
            raise CacheError("Database not connected")

        cache_key = f"trends_{geo}_{window_hours}"
        now = datetime.now(timezone.utc).isoformat()
        trends_json = json.dumps(trends, ensure_ascii=False)

        self._conn.execute(
            """
            INSERT OR REPLACE INTO trends_cache
            (cache_key, trends_json, fetched_at, geo, window_hours)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cache_key, trends_json, now, geo, window_hours),
        )
        self._conn.commit()

    # --- Runs ---

    def start_run(self, run_id: str) -> None:
        """Record the start of a worker run.

        Args:
            run_id: Unique run identifier.
        """
        if not self._conn:
            raise CacheError("Database not connected")

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO runs (run_id, started_at, status) VALUES (?, ?, ?)",
            (run_id, now, "running"),
        )
        self._conn.commit()

    def complete_run(
        self, run_id: str, status: str = "completed", output_hash: str | None = None
    ) -> None:
        """Record the completion of a worker run.

        Args:
            run_id: Unique run identifier.
            status: Final status (completed, failed, partial).
            output_hash: Optional hash of the output for idempotency.
        """
        if not self._conn:
            raise CacheError("Database not connected")

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE runs SET completed_at = ?, status = ?, output_hash = ?
            WHERE run_id = ?
            """,
            (now, status, output_hash, run_id),
        )
        self._conn.commit()

    # --- Processed Articles ---

    def save_processed_article(
        self,
        article_hash: str,
        title: str,
        link: str,
        source: str,
        trend_score: float,
        run_id: str,
    ) -> None:
        """Save a processed article record.

        Args:
            article_hash: Unique hash of the article.
            title: Article title.
            link: Article URL.
            source: Source name.
            trend_score: Computed trend score.
            run_id: Associated run ID.
        """
        if not self._conn:
            raise CacheError("Database not connected")

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO processed_articles
            (article_hash, title, link, source, trend_score, run_id, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (article_hash, title, link, source, trend_score, run_id, now),
        )
        self._conn.commit()

    def article_exists(self, article_hash: str) -> bool:
        """Check if an article has already been processed.

        Args:
            article_hash: Unique hash of the article.

        Returns:
            True if the article exists in the database.
        """
        if not self._conn:
            raise CacheError("Database not connected")

        row = self._conn.execute(
            "SELECT 1 FROM processed_articles WHERE article_hash = ?",
            (article_hash,),
        ).fetchone()
        return row is not None
