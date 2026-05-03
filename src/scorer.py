"""Composite trend scoring for articles."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from src.config import ScoringConfig


def compute_recency_score(published: str, reference_time: str | None = None) -> float:
    """Compute recency score using exponential decay.

    Formula: recency_score = 100 * e^(-hours_ago / 24)

    Args:
        published: ISO 8601 timestamp of article publication.
        reference_time: Optional reference time (defaults to now).

    Returns:
        Recency score between 0 and 100.
    """
    if not published:
        return 0.0

    try:
        from dateutil import parser as date_parser

        pub_dt = date_parser.parse(published)
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)

        if reference_time:
            ref_dt = date_parser.parse(reference_time)
            if ref_dt.tzinfo is None:
                ref_dt = ref_dt.replace(tzinfo=timezone.utc)
        else:
            ref_dt = datetime.now(timezone.utc)

        hours_ago = (ref_dt - pub_dt).total_seconds() / 3600

        # Exponential decay: 100 * e^(-hours_ago / 24)
        recency_score = 100 * math.exp(-hours_ago / 24)

        return max(0.0, min(100.0, recency_score))

    except (ValueError, TypeError):
        return 0.0


def compute_authority_score(source: dict[str, Any]) -> float:
    """Normalize authority score from 0.0-1.0 to 0-100.

    Args:
        source: Source dict with 'authority_score' field (0.0-1.0).

    Returns:
        Authority score between 0 and 100.
    """
    authority = source.get("authority_score", 0.5)
    return authority * 100


def compute_final_score(
    trend_match_score: float,
    recency_score: float,
    authority_score: float,
    weights: ScoringConfig | None = None,
) -> float:
    """Compute the composite final trend score for an article.

    Formula:
        final_score = (trend_match_score * trend_match_weight)
                    + (recency_score * recency_weight)
                    + (authority_score * source_authority_weight)

    Args:
        trend_match_score: Best fuzzy match score (0-100).
        recency_score: Recency score (0-100).
        authority_score: Source authority score (0-100).
        weights: Scoring configuration with weights.

    Returns:
        Final composite score (0-100).
    """
    if weights is None:
        weights = ScoringConfig()

    final = (
        (trend_match_score * weights.trend_match_weight)
        + (recency_score * weights.recency_weight)
        + (authority_score * weights.source_authority_weight)
    )

    return round(final, 2)


def score_articles(
    articles: list[dict[str, Any]],
    scoring_config: ScoringConfig,
    logger: Any = None,
) -> list[dict[str, Any]]:
    """Score all matched articles with composite trend scores.

    Adds 'recency_score', 'authority_score', and 'final_score' to each article.

    Args:
        articles: List of article dicts with 'matched_trends' and 'trend_match_score'.
        scoring_config: Scoring configuration.
        logger: Optional logger instance.

    Returns:
        List of article dicts with added score fields.
    """
    scored_articles: list[dict[str, Any]] = []

    for article in articles:
        article_copy = dict(article)

        # Recency score
        recency = compute_recency_score(article.get("published", ""))
        article_copy["recency_score"] = round(recency, 2)

        # Authority score
        source = article.get("source", {})
        authority = compute_authority_score(source)
        article_copy["authority_score"] = round(authority, 2)

        # Final composite score
        trend_match = article.get("trend_match_score", 0)
        final = compute_final_score(trend_match, recency, authority, scoring_config)
        article_copy["final_score"] = final

        scored_articles.append(article_copy)

    if logger:
        if scored_articles:
            avg_score = sum(a["final_score"] for a in scored_articles) / len(
                scored_articles
            )
            logger.info(
                "Scored %d articles (avg score: %.1f)", len(scored_articles), avg_score
            )
        else:
            logger.info("No articles to score")

    return scored_articles