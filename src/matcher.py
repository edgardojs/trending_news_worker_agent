"""Fuzzy matching of articles to trending search terms."""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from src.normalize import normalize_title


def compute_match_score(article_title: str, trend_title: str) -> int:
    """Compute the best fuzzy match score between an article title and a trend.

    Uses the maximum of:
    - fuzz.ratio (exact similarity)
    - fuzz.partial_ratio (partial substring match)
    - fuzz.token_set_ratio (token set overlap)

    Args:
        article_title: The article title string.
        trend_title: The trend title string.

    Returns:
        Best match score as integer (0-100).
    """
    norm_article = normalize_title(article_title)
    norm_trend = normalize_title(trend_title)

    if not norm_article or not norm_trend:
        return 0

    ratio = fuzz.ratio(norm_article, norm_trend)
    partial_ratio = fuzz.partial_ratio(norm_article, norm_trend)
    token_set_ratio = fuzz.token_set_ratio(norm_article, norm_trend)

    return int(max(ratio, partial_ratio, token_set_ratio))


def match_articles_to_trends(
    articles: list[dict[str, Any]],
    trends: list[dict[str, Any]],
    threshold: int = 85,
    logger: Any = None,
) -> list[dict[str, Any]]:
    """Match articles against trending search terms.

    For each article, find all trends that match above the threshold.
    Attach matched trends and best match score to each article.

    Args:
        articles: List of normalized article dicts.
        trends: List of normalized trend dicts.
        threshold: Minimum fuzzy match score to consider a match (0-100).
        logger: Optional logger instance.

    Returns:
        List of article dicts with added 'matched_trends' and 'trend_match_score' fields.
    """
    matched_articles: list[dict[str, Any]] = []

    for article in articles:
        matched_trends: list[dict[str, Any]] = []
        best_score = 0

        for trend in trends:
            score = compute_match_score(article["title"], trend["title"])
            if score >= threshold:
                matched_trends.append(
                    {
                        "trend": trend["title"],
                        "trend_id": trend["id"],
                        "match_score": score,
                    }
                )
                best_score = max(best_score, score)

        # Only include articles that have at least one trend match
        if matched_trends:
            article_copy = dict(article)
            article_copy["matched_trends"] = matched_trends
            article_copy["trend_match_score"] = best_score
            matched_articles.append(article_copy)

    if logger:
        logger.info(
            "Matched %d of %d articles to trends (threshold=%d)",
            len(matched_articles),
            len(articles),
            threshold,
        )

    return matched_articles
