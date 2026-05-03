"""RSS feed ingestion for the Trending News Worker Agent."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import AppConfig
from src.exceptions import FeedError


# Default authority scores for known news sources
SOURCE_AUTHORITY: dict[str, float] = {
    "bbc.co.uk": 0.9,
    "bbc.com": 0.9,
    "cnn.com": 0.85,
    "reuters.com": 0.95,
    "apnews.com": 0.9,
    "nytimes.com": 0.85,
    "theguardian.com": 0.85,
    "washingtonpost.com": 0.85,
    "aljazeera.com": 0.8,
    "news.google.com": 0.7,
}


def _hash_id(*parts: str) -> str:
    """Generate a deterministic hash ID from string parts."""
    content = "|".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL.

    Args:
        url: Full URL string.

    Returns:
        Domain string (e.g., 'bbc.co.uk').
    """
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return parsed.netloc.lower().replace("www.", "")
    except Exception:
        return url.lower()


def _get_authority_score(url: str) -> float:
    """Get the authority score for a source URL.

    Args:
        url: Source feed URL.

    Returns:
        Authority score between 0.0 and 1.0.
    """
    domain = _extract_domain(url)
    for known_domain, score in SOURCE_AUTHORITY.items():
        if known_domain in domain:
            return score
    return 0.5  # Default authority for unknown sources


def _parse_article_entry(
    entry: Any, feed_url: str, feed_name: str = ""
) -> dict[str, Any]:
    """Parse a single RSS entry into normalized article structure.

    Args:
        entry: A feedparser entry dict.
        feed_url: The source feed URL.
        feed_name: Human-readable feed name.

    Returns:
        Normalized article dict.
    """
    title = getattr(entry, "title", "").strip()
    link = getattr(entry, "link", "").strip()
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
    if isinstance(summary, str):
        summary = summary.strip()
    else:
        summary = str(summary).strip()

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

    # Determine source name
    source_name = feed_name
    if not source_name:
        if hasattr(entry, "source") and hasattr(entry.source, "title"):
            source_name = entry.source.title
        elif hasattr(entry, "feed_title"):
            source_name = entry.feed_title
        else:
            source_name = _extract_domain(feed_url)

    article_id = _hash_id(title, link)
    authority_score = _get_authority_score(feed_url)

    return {
        "id": article_id,
        "title": title,
        "link": link,
        "summary": summary,
        "published": timestamp,
        "source": {
            "name": source_name,
            "url": feed_url,
            "authority_score": authority_score,
        },
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
        raise FeedError(f"Failed to fetch RSS feed {url}: {e}", feed_url=url) from e


def fetch_rss_feeds(
    config: AppConfig,
    logger: Any = None,
    cache: Any = None,
) -> list[dict[str, Any]]:
    """Fetch and parse all configured RSS feeds.

    Args:
        config: Application configuration.
        logger: Optional logger instance.
        cache: Optional CacheDB instance for caching.

    Returns:
        List of normalized article dicts.
    """
    articles: list[dict[str, Any]] = []
    feeds_succeeded = 0
    feeds_failed = 0

    for feed_url in config.rss.feeds:
        try:
            # Try cache first
            if cache and config.cache.enabled:
                cached = cache.get_rss_cache(feed_url)
                if cached:
                    content = cached["response_blob"]
                    if logger:
                        logger.info("Using cached RSS data for %s", feed_url)
                else:
                    content = _fetch_feed_content(
                        url=feed_url,
                        timeout=config.rss.timeout_seconds,
                        user_agent=config.rss.user_agent,
                    )
                    # Save to cache
                    try:
                        cache.save_rss_cache(feed_url, content)
                    except Exception as e:
                        if logger:
                            logger.warning("Failed to cache RSS feed %s: %s", feed_url, e)
            else:
                content = _fetch_feed_content(
                    url=feed_url,
                    timeout=config.rss.timeout_seconds,
                    user_agent=config.rss.user_agent,
                )

            parsed = feedparser.parse(content)

            if parsed.bozo and not parsed.entries:
                raise FeedError(
                    f"Failed to parse RSS feed {feed_url}: {parsed.bozo_exception}",
                    feed_url=feed_url,
                )

            feed_name = getattr(parsed.feed, "title", _extract_domain(feed_url))

            entry_count = 0
            for entry in parsed.entries:
                if entry_count >= config.rss.max_articles_per_feed:
                    break
                article = _parse_article_entry(entry, feed_url, feed_name)
                if article["title"]:
                    articles.append(article)
                    entry_count += 1

            feeds_succeeded += 1
            if logger:
                logger.info(
                    "Fetched %d articles from %s",
                    entry_count,
                    feed_url,
                    extra={"feed_url": feed_url, "article_count": entry_count},
                )

        except FeedError as e:
            feeds_failed += 1
            if logger:
                logger.warning("Failed to fetch RSS feed %s: %s", feed_url, e)
        except Exception as e:
            feeds_failed += 1
            if logger:
                logger.warning("Unexpected error fetching RSS feed %s: %s", feed_url, e)

    if logger:
        logger.info(
            "RSS feed fetching complete: %d succeeded, %d failed, %d total articles",
            feeds_succeeded,
            feeds_failed,
            len(articles),
        )

    # If all feeds failed, raise an error
    if feeds_failed > 0 and feeds_succeeded == 0:
        if logger:
            logger.error("All RSS feeds failed")
        # Don't raise - we continue with empty articles and let the worker handle it

    return articles