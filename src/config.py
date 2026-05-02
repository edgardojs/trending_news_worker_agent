"""Configuration loading and validation for the Trending News Worker Agent."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class GeneralConfig(BaseModel):
    """General configuration settings."""

    output_dir: str = "./output"
    log_dir: str = "./logs"
    cache_dir: str = "./cache"
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got {v!r}")
        return v_upper


class TrendsConfig(BaseModel):
    """Google Trends configuration."""

    feeds: list[str] = Field(
        default_factory=lambda: [
            "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
        ]
    )
    geo: str = "US"
    window_hours: int = 24
    max_trends: int = 50

    @field_validator("window_hours")
    @classmethod
    def validate_window_hours(cls, v: int) -> int:
        if v < 1 or v > 168:
            raise ValueError("window_hours must be between 1 and 168")
        return v

    @field_validator("max_trends")
    @classmethod
    def validate_max_trends(cls, v: int) -> int:
        if v < 1 or v > 200:
            raise ValueError("max_trends must be between 1 and 200")
        return v


class RssConfig(BaseModel):
    """RSS feed configuration."""

    feeds: list[str] = Field(
        default_factory=lambda: [
            "http://feeds.bbci.co.uk/news/rss.xml",
            "http://rss.cnn.com/rss/edition.rss",
        ]
    )
    timeout_seconds: int = 30
    max_articles_per_feed: int = 100
    user_agent: str = "TrendingNewsWorker/1.0"

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v < 5 or v > 120:
            raise ValueError("timeout_seconds must be between 5 and 120")
        return v

    @field_validator("max_articles_per_feed")
    @classmethod
    def validate_max_articles(cls, v: int) -> int:
        if v < 1 or v > 500:
            raise ValueError("max_articles_per_feed must be between 1 and 500")
        return v


class ScoringConfig(BaseModel):
    """Scoring configuration."""

    trend_match_weight: float = 0.6
    recency_weight: float = 0.2
    source_authority_weight: float = 0.2
    fuzzy_threshold: int = 85

    @field_validator("trend_match_weight", "recency_weight", "source_authority_weight")
    @classmethod
    def validate_weights(cls, v: float) -> float:
        if v < 0 or v > 1:
            raise ValueError("weights must be between 0.0 and 1.0")
        return v

    @field_validator("fuzzy_threshold")
    @classmethod
    def validate_threshold(cls, v: int) -> int:
        if v < 0 or v > 100:
            raise ValueError("fuzzy_threshold must be between 0 and 100")
        return v


class OutputConfig(BaseModel):
    """Output configuration."""

    formats: list[str] = Field(default_factory=lambda: ["json", "markdown"])
    max_ranked_articles: int = 20
    include_scores: bool = True
    include_trend_matches: bool = True

    @field_validator("formats")
    @classmethod
    def validate_formats(cls, v: list[str]) -> list[str]:
        allowed = {"json", "markdown"}
        for fmt in v:
            if fmt not in allowed:
                raise ValueError(f"format must be one of {allowed}, got {fmt!r}")
        return v

    @field_validator("max_ranked_articles")
    @classmethod
    def validate_max_ranked(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError("max_ranked_articles must be between 1 and 100")
        return v


class CacheConfig(BaseModel):
    """Cache configuration."""

    backend: str = "sqlite"
    enabled: bool = True
    ttl_seconds: int = 3600
    sqlite_path: str = "./cache/trending_news.db"
    redis_enabled: bool = False

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        allowed = {"sqlite", "redis"}
        if v not in allowed:
            raise ValueError(f"backend must be one of {allowed}, got {v!r}")
        return v

    @field_validator("ttl_seconds")
    @classmethod
    def validate_ttl(cls, v: int) -> int:
        if v < 60:
            raise ValueError("ttl_seconds must be at least 60")
        return v


class DeduplicationConfig(BaseModel):
    """Deduplication configuration."""

    enabled: bool = True
    method: str = "fuzzy"
    threshold: int = 85

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        allowed = {"fuzzy", "exact"}
        if v not in allowed:
            raise ValueError(f"method must be one of {allowed}, got {v!r}")
        return v

    @field_validator("threshold")
    @classmethod
    def validate_threshold(cls, v: int) -> int:
        if v < 0 or v > 100:
            raise ValueError("threshold must be between 0 and 100")
        return v


class AppConfig(BaseModel):
    """Top-level application configuration."""

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    trends: TrendsConfig = Field(default_factory=TrendsConfig)
    rss: RssConfig = Field(default_factory=RssConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    deduplication: DeduplicationConfig = Field(default_factory=DeduplicationConfig)


def load_config(config_path: str) -> AppConfig:
    """Load and validate configuration from a YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Validated AppConfig instance.

    Raises:
        ConfigError: If the config file cannot be loaded or is invalid.
    """
    from src.exceptions import ConfigError

    path = Path(config_path)

    if not path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in configuration file: {e}") from e
    except OSError as e:
        raise ConfigError(f"Cannot read configuration file: {e}") from e

    try:
        config = AppConfig(**raw)
    except Exception as e:
        raise ConfigError(f"Configuration validation error: {e}") from e

    return config


def ensure_directories(config: AppConfig) -> None:
    """Create output, log, and cache directories if they don't exist.

    Args:
        config: Validated AppConfig instance.
    """
    for dir_path in [
        config.general.output_dir,
        config.general.log_dir,
        config.general.cache_dir,
    ]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)