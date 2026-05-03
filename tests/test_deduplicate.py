"""Tests for near-duplicate article detection."""

import pytest

from src.deduplicate import compute_similarity, deduplicate_articles


def test_compute_similarity_identical():
    """Test that identical titles get 100 similarity."""
    score = compute_similarity("Climate Summit 2026", "Climate Summit 2026")
    assert score == 100


def test_compute_similarity_similar():
    """Test that similar titles get high similarity."""
    score = compute_similarity(
        "Climate Summit reaches historic agreement",
        "Climate Summit reaches a historic agreement"
    )
    assert score >= 85


def test_compute_similarity_different():
    """Test that different titles get low similarity."""
    score = compute_similarity("Climate Summit", "Stock Market Update")
    assert score < 50


def test_compute_similarity_empty():
    """Test that empty strings return 0."""
    assert compute_similarity("", "test") == 0
    assert compute_similarity("test", "") == 0


def test_deduplicate_articles_keeps_highest_score():
    """Test that deduplication keeps the article with the highest score."""
    articles = [
        {
            "id": "1",
            "title": "Climate Summit reaches agreement",
            "link": "https://example.com/1",
            "final_score": 85.0,
        },
        {
            "id": "2",
            "title": "Climate Summit reaches an agreement",
            "link": "https://example.com/2",
            "final_score": 75.0,
        },
    ]

    result = deduplicate_articles(articles, threshold=85)
    assert len(result) == 1
    assert result[0]["id"] == "1"  # Higher score kept
    assert result[0]["final_score"] == 85.0


def test_deduplicate_articles_preserves_unique():
    """Test that unique articles are preserved."""
    articles = [
        {
            "id": "1",
            "title": "Climate Summit reaches agreement",
            "link": "https://example.com/1",
            "final_score": 85.0,
        },
        {
            "id": "2",
            "title": "Stock Market hits record high",
            "link": "https://example.com/2",
            "final_score": 70.0,
        },
    ]

    result = deduplicate_articles(articles, threshold=85)
    assert len(result) == 2


def test_deduplicate_articles_empty():
    """Test that empty list returns empty list."""
    result = deduplicate_articles([], threshold=85)
    assert result == []


def test_deduplicate_articles_tracks_duplicates():
    """Test that duplicate references are preserved in metadata."""
    articles = [
        {
            "id": "1",
            "title": "Climate Summit reaches agreement",
            "link": "https://example.com/1",
            "final_score": 90.0,
        },
        {
            "id": "2",
            "title": "Climate Summit reaches an agreement",
            "link": "https://example.com/2",
            "final_score": 80.0,
        },
    ]

    result = deduplicate_articles(articles, threshold=80)
    assert len(result) == 1
    assert "duplicate_ids" in result[0]
    assert "2" in result[0]["duplicate_ids"]