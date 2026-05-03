"""Article ranking and top-N selection."""

from __future__ import annotations

from typing import Any


def rank_articles(
    articles: list[dict[str, Any]],
    max_articles: int = 20,
    logger: Any = None,
) -> list[dict[str, Any]]:
    """Rank articles by descending final_score with deterministic tie-breaking.

    Tie-breaking order:
    1. Higher final_score
    2. Newer publication timestamp
    3. Higher source authority
    4. Alphabetical title order

    Args:
        articles: List of scored article dicts.
        max_articles: Maximum number of articles to return.
        logger: Optional logger instance.

    Returns:
        Ranked and trimmed list of article dicts with added 'rank' field.
    """
    if not articles:
        return []

    # Sort with deterministic tie-breaking
    ranked = sorted(
        articles,
        key=lambda a: (
            -a.get("final_score", 0),  # Higher score first
            -_parse_timestamp_for_sort(a.get("published", "")),  # Newer first
            -a.get("authority_score", 0),  # Higher authority first
            a.get("title", "").lower(),  # Alphabetical for determinism
        ),
    )

    # Trim to max_articles
    ranked = ranked[:max_articles]

    # Assign rank numbers
    for i, article in enumerate(ranked):
        article["rank"] = i + 1

    if logger:
        if ranked:
            top_score = ranked[0].get("final_score", 0)
            bottom_score = ranked[-1].get("final_score", 0)
            logger.info(
                "Ranked %d articles (top score: %.1f, bottom score: %.1f)",
                len(ranked),
                top_score,
                bottom_score,
            )
        else:
            logger.info("No articles to rank")

    return ranked


def _parse_timestamp_for_sort(timestamp: str) -> float:
    """Parse a timestamp string into a sortable numeric value.

    Args:
        timestamp: ISO 8601 timestamp string.

    Returns:
        Unix timestamp as float, or 0.0 if parsing fails.
    """
    if not timestamp:
        return 0.0

    try:
        from dateutil import parser as date_parser
        from datetime import timezone

        dt = date_parser.parse(timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0