"""Tests for configuration loading and validation."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from src.config import AppConfig, load_config, ensure_directories
from src.exceptions import ConfigError


@pytest.fixture
def valid_config_data():
    """Return a valid configuration dict."""
    return {
        "general": {
            "output_dir": "./output",
            "log_dir": "./logs",
            "cache_dir": "./cache",
            "log_level": "INFO",
        },
        "trends": {
            "feeds": ["https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"],
            "geo": "US",
            "window_hours": 24,
            "max_trends": 50,
        },
        "rss": {
            "feeds": ["http://feeds.bbci.co.uk/news/rss.xml"],
            "timeout_seconds": 30,
            "max_articles_per_feed": 100,
            "user_agent": "TrendingNewsWorker/1.0",
        },
        "scoring": {
            "trend_match_weight": 0.6,
            "recency_weight": 0.2,
            "source_authority_weight": 0.2,
            "fuzzy_threshold": 85,
        },
        "output": {
            "formats": ["json", "markdown"],
            "max_ranked_articles": 20,
            "include_scores": True,
            "include_trend_matches": True,
        },
        "cache": {
            "backend": "sqlite",
            "enabled": True,
            "ttl_seconds": 3600,
            "sqlite_path": "./cache/trending_news.db",
            "redis_enabled": False,
        },
        "deduplication": {
            "enabled": True,
            "method": "fuzzy",
            "threshold": 85,
        },
    }


@pytest.fixture
def config_file(valid_config_data, tmp_path):
    """Create a temporary config file."""
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(valid_config_data, f)
    return str(config_path)


def test_load_valid_config(config_file):
    """Test loading a valid configuration file."""
    config = load_config(config_file)
    assert isinstance(config, AppConfig)
    assert config.general.log_level == "INFO"
    assert config.trends.geo == "US"
    assert config.scoring.fuzzy_threshold == 85


def test_load_missing_config():
    """Test that loading a missing config file raises ConfigError."""
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/path/config.yaml")


def test_load_invalid_yaml(tmp_path):
    """Test that invalid YAML raises ConfigError."""
    config_path = tmp_path / "bad_config.yaml"
    with open(config_path, "w") as f:
        f.write("invalid: yaml: content: [")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(str(config_path))


def test_default_config():
    """Test that AppConfig has sensible defaults."""
    config = AppConfig()
    assert config.general.output_dir == "./output"
    assert config.trends.geo == "US"
    assert config.scoring.trend_match_weight == 0.6
    assert config.cache.backend == "sqlite"


def test_invalid_log_level():
    """Test that invalid log level raises validation error."""
    with pytest.raises(Exception):
        AppConfig(**{"general": {"log_level": "INVALID"}})


def test_invalid_weights():
    """Test that weights outside 0-1 range raise validation error."""
    with pytest.raises(Exception):
        AppConfig(**{"scoring": {"trend_match_weight": 1.5}})


def test_ensure_directories(tmp_path):
    """Test that ensure_directories creates directories."""
    config = AppConfig(
        general={
            "output_dir": str(tmp_path / "output"),
            "log_dir": str(tmp_path / "logs"),
            "cache_dir": str(tmp_path / "cache"),
        }
    )
    ensure_directories(config)
    assert Path(config.general.output_dir).exists()
    assert Path(config.general.log_dir).exists()
    assert Path(config.general.cache_dir).exists()