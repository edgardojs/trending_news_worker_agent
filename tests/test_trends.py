"""Tests for Google Trends fetching."""

from unittest.mock import MagicMock, patch

import pytest

from src.trends import _parse_trend_entry, fetch_trends
from src.config import AppConfig


@pytest.fixture
def mock_config():
    """Return a test configuration."""
    return AppConfig(
        trends={
            "feeds": ["https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"],
            "geo": "US",
            "window_hours": 24,
            "max_trends": 50,
        },
        rss={"timeout_seconds": 10, "user_agent": "TestAgent/1.0"},
    )


def test_parse_trend_entry():
    """Test parsing a Google Trends RSS entry."""
    entry = MagicMock(spec=[])
    entry.title = "Climate Summit"
    entry.link = "https://trends.google.com/foo"
    entry.published = "Fri, 02 May 2026 10:00:00 GMT"
    entry.ht_approx_traffic = "500K+"

    result = _parse_trend_entry(entry, "US")
    assert result["title"] == "Climate Summit"
    assert result["geo"] == "US"
    assert result["search_volume"] == "500K+"
    assert result["id"]  # Should have a hash ID


def test_parse_trend_entry_no_traffic():
    """Test parsing an entry without traffic data."""
    entry = MagicMock(spec=[])
    entry.title = "Test Trend"
    entry.link = "https://example.com"
    entry.published = ""
    entry.updated = "2026-05-02T10:00:00Z"

    result = _parse_trend_entry(entry, "US")
    assert result["title"] == "Test Trend"
    assert result["search_volume"] == ""


def test_fetch_trends_empty_feed(mock_config):
    """Test fetching trends when feed returns no entries."""
    mock_feed_data = MagicMock(spec=[])
    mock_feed_data.entries = []
    mock_feed_data.bozo = 0

    with patch("src.trends.feedparser.parse", return_value=mock_feed_data), \
         patch("src.trends._fetch_feed_content", return_value="<rss></rss>"):
        trends = fetch_trends(config=mock_config)
        assert isinstance(trends, list)


def test_fetch_trends_with_entries(mock_config):
    """Test fetching trends with valid entries."""
    entry = MagicMock(spec=[])
    entry.title = "Test Trend"
    entry.link = "https://trends.google.com/test"
    entry.published = "Fri, 02 May 2026 10:00:00 GMT"
    entry.ht_approx_traffic = "100K+"

    mock_feed_data = MagicMock(spec=[])
    mock_feed_data.entries = [entry]
    mock_feed_data.bozo = 0

    with patch("src.trends.feedparser.parse", return_value=mock_feed_data), \
         patch("src.trends._fetch_feed_content", return_value="<rss></rss>"):
        trends = fetch_trends(config=mock_config)
        assert len(trends) == 1
        assert trends[0]["title"] == "Test Trend"