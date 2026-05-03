"""Tests for article ranking."""

import pytest

from src.ranker import rank_articles


def test_rank_articles_basic():
    """Test basic ranking by descending score."""
    articles = [
        {"id": "1", "title": "Alpha", "final_score": 70.0, "published": "2026-05-02T08:00:00Z", "authority_score": 80.0},
        {"id": "2", "title": "Beta", "final_score": 90.0, "published": "2026-05-02T09:00:00Z", "authority_score": 85.0},
        {"id": "3", "title": "Gamma", "final_score": 80.0, "published": "2026-05-02T07:00:00Z", "authority_score": 75.0},
    ]

    ranked = rank_articles(articles, max_articles=10)
    assert len(ranked) == 3
    assert ranked[0]["rank"] == 1
    assert ranked[0]["final_score"] == 90.0
    assert ranked[1]["rank"] == 2
    assert ranked[1]["final_score"] == 80.0
    assert ranked[2]["rank"] == 3
    assert ranked[2]["final_score"] == 70.0


def test_rank_articles_max_limit():
    """Test that max_articles limits the output."""
    articles = [
        {"id": str(i), "title": f"Article {i}", "final_score": float(100 - i), "published": "2026-05-02T08:00:00Z", "authority_score": 80.0}
        for i in range(30)
    ]

    ranked = rank_articles(articles, max_articles=20)
    assert len(ranked) == 20


def test_rank_articles_tiebreaking():
    """Test deterministic tie-breaking."""
    articles = [
        {"id": "1", "title": "B Article", "final_score": 80.0, "published": "2026-05-02T08:00:00Z", "authority_score": 80.0},
        {"id": "2", "title": "A Article", "final_score": 80.0, "published": "2026-05-02T09:00:00Z", "authority_score": 80.0},
    ]

    ranked = rank_articles(articles, max_articles=10)
    # Same score, but article 2 is newer, so it should rank first
    assert ranked[0]["id"] == "2"


def test_rank_articles_empty():
    """Test that empty list returns empty."""
    ranked = rank_articles([], max_articles=10)
    assert ranked == []


def test_rank_articles_assigns_ranks():
    """Test that rank numbers are assigned correctly."""
    articles = [
        {"id": "1", "title": "First", "final_score": 95.0, "published": "2026-05-02T08:00:00Z", "authority_score": 90.0},
        {"id": "2", "title": "Second", "final_score": 85.0, "published": "2026-05-02T07:00:00Z", "authority_score": 80.0},
    ]

    ranked = rank_articles(articles, max_articles=10)
    assert ranked[0]["rank"] == 1
    assert ranked[1]["rank"] == 2