"""Tests for RSS feed ingestion."""

from unittest.mock import MagicMock, patch

import pytest

from src.rss import _parse_article_entry, _extract_domain, _get_authority_score, fetch_rss_feeds
from src.config import AppConfig


@pytest.fixture
def mock_config():
    """Return a test configuration."""
    return AppConfig(
        rss={
            "feeds": ["http://feeds.bbci.co.uk/news/rss.xml"],
            "timeout_seconds": 10,
            "max_articles_per_feed": 100,
            "user_agent": "TestAgent/1.0",
        }
    )


def test_extract_domain():
    """Test domain extraction from URLs."""
    assert _extract_domain("https://www.bbc.co.uk/news") == "bbc.co.uk"
    assert _extract_domain("http://rss.cnn.com/rss/edition.rss") == "rss.cnn.com"
    assert _extract_domain("https://example.com") == "example.com"


def test_get_authority_score():
    """Test authority score lookup."""
    assert _get_authority_score("http://feeds.bbci.co.uk/news/rss.xml") == 0.9
    assert _get_authority_score("http://rss.cnn.com/rss/edition.rss") == 0.85
    assert _get_authority_score("http://unknown-source.com/feed.xml") == 0.5


def test_parse_article_entry():
    """Test parsing an RSS entry into normalized article."""
    entry = MagicMock(spec=[])
    entry.title = "Breaking News Story"
    entry.link = "https://www.bbc.co.uk/news/story-123"
    entry.summary = "A brief description of the story."
    entry.published = "Fri, 02 May 2026 08:00:00 GMT"

    result = _parse_article_entry(entry, "http://feeds.bbci.co.uk/news/rss.xml", "BBC News")
    assert result["title"] == "Breaking News Story"
    assert result["link"] == "https://www.bbc.co.uk/news/story-123"
    assert result["source"]["name"] == "BBC News"
    assert result["source"]["authority_score"] == 0.9
    assert result["id"]  # Should have a hash ID


def test_parse_article_entry_empty_title():
    """Test that entries with empty titles are handled."""
    entry = MagicMock(spec=[])
    entry.title = ""
    entry.link = "https://example.com/article"
    entry.summary = ""
    entry.published = ""

    result = _parse_article_entry(entry, "http://example.com/feed.xml", "Test")
    assert result["title"] == ""


def test_fetch_rss_feeds_with_entries(mock_config):
    """Test fetching RSS feeds with valid entries."""
    entry = MagicMock(spec=[])
    entry.title = "Test Article"
    entry.link = "https://www.bbc.co.uk/news/test"
    entry.summary = "Test summary"
    entry.published = "Fri, 02 May 2026 08:00:00 GMT"

    mock_feed = MagicMock()
    mock_feed.title = "BBC News"

    mock_feed_data = MagicMock()
    mock_feed_data.entries = [entry]
    mock_feed_data.bozo = 0
    mock_feed_data.feed = mock_feed

    with patch("src.rss.feedparser.parse", return_value=mock_feed_data), \
         patch("src.rss._fetch_feed_content", return_value="<rss></rss>"):
        articles = fetch_rss_feeds(config=mock_config)
        assert len(articles) == 1
        assert articles[0]["title"] == "Test Article"