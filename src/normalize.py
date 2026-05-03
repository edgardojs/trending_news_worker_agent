"""Text normalization utilities for the Trending News Worker Agent."""

from __future__ import annotations

import re
import unicodedata


# Common English stopwords (minimal set for lightweight matching)
STOPWORDS: set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "as", "be", "was", "are",
    "been", "have", "has", "had", "this", "that", "these", "those",
    "not", "no", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "can", "shall",
}


def normalize_text(text: str, remove_stopwords: bool = False) -> str:
    """Normalize text for matching and comparison.

    Normalization steps:
    1. Lowercase
    2. Trim whitespace
    3. Remove excessive punctuation
    4. Retain alphanumeric characters, spaces, and basic punctuation
    5. Optionally remove stopwords

    Args:
        text: Raw text string to normalize.
        remove_stopwords: Whether to remove common stopwords.

    Returns:
        Normalized text string.
    """
    if not text:
        return ""

    # Normalize unicode
    text = unicodedata.normalize("NFKD", text)

    # Lowercase
    text = text.lower()

    # Remove excessive punctuation (keep periods, commas, hyphens within words)
    # Replace multiple punctuation with single
    text = re.sub(r"[!?;:]+", " ", text)

    # Remove URLs
    text = re.sub(r"https?://\S+", " ", text)

    # Keep alphanumeric, spaces, hyphens, and apostrophes
    text = re.sub(r"[^\w\s'\-]", " ", text)

    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)

    # Trim
    text = text.strip()

    # Optionally remove stopwords
    if remove_stopwords:
        words = text.split()
        words = [w for w in words if w not in STOPWORDS]
        text = " ".join(words)

    return text


def normalize_title(title: str) -> str:
    """Normalize an article or trend title for matching.

    Args:
        title: Raw title string.

    Returns:
        Normalized title string with stopwords removed.
    """
    return normalize_text(title, remove_stopwords=True)


def parse_iso8601(timestamp: str) -> str:
    """Parse a timestamp string into ISO 8601 UTC format.

    Args:
        timestamp: A date/time string in various formats.

    Returns:
        ISO 8601 formatted string in UTC.
    """
    if not timestamp:
        return ""

    try:
        from dateutil import parser as date_parser

        dt = date_parser.parse(timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=__import__("datetime").timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        return timestamp


def extract_domain(url: str) -> str:
    """Extract the domain from a URL.

    Args:
        url: Full URL string.

    Returns:
        Lowercase domain string.
    """
    if not url:
        return ""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return parsed.netloc.lower().replace("www.", "")
    except Exception:
        return url.lower()


def compute_hash(*parts: str) -> str:
    """Compute a deterministic hash from string parts.

    Args:
        *parts: String parts to hash.

    Returns:
        Hex hash string (first 16 characters of SHA-256).
    """
    content = "|".join(parts)
    import hashlib

    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]