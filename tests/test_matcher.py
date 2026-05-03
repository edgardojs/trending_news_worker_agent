"""Tests for fuzzy matching of articles to trends."""

import pytest

from src.matcher import compute_match_score, match_articles_to_trends


def test_compute_match_score_exact():
    """Test exact match returns high score."""
    score = compute_match_score("Climate Summit 2026", "Climate Summit 2026")
    assert score == 100


def test_compute_match_score_partial():
    """Test partial match returns reasonable score."""
    score = compute_match_score("Climate Summit discusses global policy", "Climate Summit")
    assert score >= 85  # partial_ratio should catch this


def test_compute_match_score_different():
    """Test unrelated titles return low score."""
    score = compute_match_score("Weather forecast for tomorrow", "Stock market update")
    assert score < 50


def test_compute_match_score_empty():
    """Test empty strings return 0."""
    assert compute_match_score("", "test") == 0
    assert compute_match_score("test", "") == 0
    assert compute_match_score("", "") == 0


def test_match_articles_to_trends_basic():
    """Test basic matching of articles to trends."""
    articles = [
        {"id": "1", "title": "Climate Summit reaches agreement", "link": "https://example.com/1"},
        {"id": "2", "title": "Sports results from yesterday", "link": "https://example.com/2"},
    ]
    trends = [
        {"id": "t1", "title": "Climate Summit", "geo": "US"},
        {"id": "t2", "title": "Stock Market", "geo": "US"},
    ]

    matched = match_articles_to_trends(articles, trends, threshold=85)
    assert len(matched) >= 1
    # Climate article should match Climate Summit trend
    climate_matches = [a for a in matched if "Climate" in a["title"]]
    assert len(climate_matches) >= 1
    assert any(m["trend"] == "Climate Summit" for m in climate_matches[0]["matched_trends"])


def test_match_articles_to_trends_no_matches():
    """Test that no matches returns empty list."""
    articles = [
        {"id": "1", "title": "Local weather forecast", "link": "https://example.com/1"},
    ]
    trends = [
        {"id": "t1", "title": "Quantum Computing Breakthrough", "geo": "US"},
    ]

    matched = match_articles_to_trends(articles, trends, threshold=85)
    assert len(matched) == 0


def test_match_articles_to_trends_threshold():
    """Test that threshold controls matching strictness."""
    articles = [
        {"id": "1", "title": "Climate change policy update", "link": "https://example.com/1"},
    ]
    trends = [
        {"id": "t1", "title": "Climate", "geo": "US"},
    ]

    # With high threshold, may not match
    matched_high = match_articles_to_trends(articles, trends, threshold=95)
    # With low threshold, should match
    matched_low = match_articles_to_trends(articles, trends, threshold=50)
    assert len(matched_low) >= len(matched_high)