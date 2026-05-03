"""Google Trends RSS/Atom feed fetching for the Trending News Worker Agent."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import AppConfig
from src.exceptions import FeedError


def _hash_id(*parts: str) -> str:
    """Generate a deterministic hash ID from string parts."""
    content = "|".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _parse_trend_entry(entry: Any, geo: str) -> dict[str, Any]:
    """Parse a single Google Trends RSS entry into normalized structure.

    Args:
        entry: A feedparser entry dict.
        geo: Geographic region code.

    Returns:
        Normalized trend dict.
    """
    title = getattr(entry, "title", "").strip()
    link = getattr(entry, "link", "").strip()
    published = getattr(entry, "published", "") or getattr(entry, "updated", "")

    # Parse the timestamp
    timestamp = ""
    if published:
        try:
            from dateutil import parser as date_parser

            dt = date_parser.parse(published)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            timestamp = dt.isoformat()
        except (ValueError, TypeError):
            timestamp = published

    # Extract approximate search volume from ht:approx_traffic if available
    search_volume = ""
    if hasattr(entry, "ht_approx_traffic"):
        search_volume = entry.ht_approx_traffic
    elif hasattr(entry, "approx_traffic"):
        search_volume = entry.approx_traffic

    trend_id = _hash_id(title, timestamp or "no-timestamp")

    return {
        "id": trend_id,
        "title": title,
        "link": link,
        "timestamp": timestamp,
        "search_volume": search_volume,
        "geo": geo,
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_feed_content(url: str, timeout: int = 30, user_agent: str = "TrendingNewsWorker/1.0") -> str:
    """Fetch raw feed content with retry logic.

    Args:
        url: Feed URL to fetch.
        timeout: Request timeout in seconds.
        user_agent: User-Agent header value.

    Returns:
        Raw feed content as string.

    Raises:
        FeedError: If the feed cannot be fetched.
    """
    headers = {"User-Agent": user_agent}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
    except httpx.HTTPError as e:
        raise FeedError(f"Failed to fetch feed {url}: {e}", feed_url=url) from e


def fetch_trends(
    config: AppConfig,
    logger: Any = None,
    cache: Any = None,
) -> list[dict[str, Any]]:
    """Fetch Google Trends data from configured feeds.

    Args:
        config: Application configuration.
        logger: Optional logger instance.
        cache: Optional CacheDB instance for caching.

    Returns:
        List of normalized trend dicts.
    """
    trends: list[dict[str, Any]] = []
    errors: list[str] = []

    # Try cache first
    if cache and config.cache.enabled:
        cached = cache.get_trends_cache(config.trends.geo, config.trends.window_hours)
        if cached:
            if logger:
                logger.info("Using cached trends data (geo=%s)", config.trends.geo)
            return cached[: config.trends.max_trends]

    for feed_url in config.trends.feeds:
        try:
            if logger:
                logger.info("Fetching trends feed: %s", feed_url)

            content = _fetch_feed_content(
                url=feed_url,
                timeout=config.rss.timeout_seconds,
                user_agent=config.rss.user_agent,
            )
            parsed = feedparser.parse(content)

            if parsed.bozo and not parsed.entries:
                raise FeedError(
                    f"Failed to parse trends feed {feed_url}: {parsed.bozo_exception}",
                    feed_url=feed_url,
                )

            for entry in parsed.entries:
                trend = _parse_trend_entry(entry, config.trends.geo)
                if trend["title"]:
                    trends.append(trend)

            if logger:
                logger.info(
                    "Fetched %d trends from %s",
                    len(parsed.entries),
                    feed_url,
                    extra={"feed_url": feed_url},
                )

        except FeedError as e:
            errors.append(str(e))
            if logger:
                logger.warning("Failed to fetch trends feed %s: %s", feed_url, e)
        except Exception as e:
            errors.append(str(e))
            if logger:
                logger.warning("Unexpected error fetching trends feed %s: %s", feed_url, e)

    # Limit to max_trends
    trends = trends[: config.trends.max_trends]

    # Save to cache
    if cache and config.cache.enabled and trends:
        try:
            cache.save_trends_cache(config.trends.geo, config.trends.window_hours, trends)
        except Exception as e:
            if logger:
                logger.warning("Failed to save trends to cache: %s", e)

    if not trends and errors:
        if logger:
            logger.warning(
                "All trends feeds failed. Errors: %s", "; ".join(errors)
            )

    return trends