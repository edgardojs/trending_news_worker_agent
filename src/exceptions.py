"""Custom exceptions for the Trending News Worker Agent."""


class TrendingNewsError(Exception):
    """Base exception for all trending news worker errors."""


class ConfigError(TrendingNewsError):
    """Raised when configuration is missing, invalid, or cannot be loaded."""


class NetworkError(TrendingNewsError):
    """Raised when a network request fails after all retries."""


class CacheError(TrendingNewsError):
    """Raised when a SQLite cache operation fails."""


class OutputError(TrendingNewsError):
    """Raised when writing output files fails."""


class FeedError(TrendingNewsError):
    """Raised when a feed cannot be fetched or parsed."""

    def __init__(self, message: str, feed_url: str = "") -> None:
        self.feed_url = feed_url
        super().__init__(message)
