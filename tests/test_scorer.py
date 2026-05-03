"""Tests for composite trend scoring."""

import pytest

from src.scorer import compute_recency_score, compute_authority_score, compute_final_score, score_articles
from src.config import ScoringConfig


def test_compute_recency_score_recent():
    """Test that recent articles get high recency scores."""
    from datetime import datetime, timezone, timedelta

    # Article published 1 hour ago
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    score = compute_recency_score(recent)
    assert score > 90  # Should be very high


def test_compute_recency_score_old():
    """Test that old articles get low recency scores."""
    from datetime import datetime, timezone, timedelta

    # Article published 72 hours ago
    old = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    score = compute_recency_score(old)
    assert score < 20  # Should be very low


def test_compute_recency_score_empty():
    """Test that empty timestamp returns 0."""
    assert compute_recency_score("") == 0.0


def test_compute_authority_score():
    """Test authority score normalization."""
    assert compute_authority_score({"authority_score": 0.9}) == 90.0
    assert compute_authority_score({"authority_score": 0.5}) == 50.0
    assert compute_authority_score({"authority_score": 1.0}) == 100.0
    assert compute_authority_score({}) == 50.0  # Default


def test_compute_final_score():
    """Test composite score calculation."""
    config = ScoringConfig()
    # With default weights: 0.6, 0.2, 0.2
    score = compute_final_score(
        trend_match_score=100,
        recency_score=100,
        authority_score=100,
        weights=config,
    )
    assert score == 100.0  # Perfect scores = 100


def test_compute_final_score_partial():
    """Test composite score with partial inputs."""
    config = ScoringConfig()
    # trend_match=80, recency=50, authority=90
    # = 80*0.6 + 50*0.2 + 90*0.2 = 48 + 10 + 18 = 76
    score = compute_final_score(
        trend_match_score=80,
        recency_score=50,
        authority_score=90,
        weights=config,
    )
    assert score == 76.0


def test_score_articles():
    """Test scoring a list of matched articles."""
    from datetime import datetime, timezone, timedelta

    recent_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    articles = [
        {
            "id": "1",
            "title": "Test Article",
            "link": "https://example.com/1",
            "published": recent_time,
            "source": {"name": "BBC", "url": "http://feeds.bbci.co.uk/news/rss.xml", "authority_score": 0.9},
            "matched_trends": [{"trend": "Test", "match_score": 90}],
            "trend_match_score": 90,
        },
    ]

    config = ScoringConfig()
    scored = score_articles(articles, config)

    assert len(scored) == 1
    assert "final_score" in scored[0]
    assert "recency_score" in scored[0]
    assert "authority_score" in scored[0]
    assert scored[0]["authority_score"] == 90.0