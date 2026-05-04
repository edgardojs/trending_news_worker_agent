"""Structured JSON Lines logging setup for the Trending News Worker Agent."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON Lines."""

    def __init__(self, run_id: str = "", component: str = "") -> None:
        super().__init__()
        self.run_id = run_id
        self.component = component

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "run_id": self.run_id,
            "component": getattr(record, "component", self.component),
            "message": record.getMessage(),
        }

        # Add optional fields from the log record
        for key in ("duration_ms", "feed_url", "article_count", "error_detail"):
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(
    run_id: str,
    log_dir: str = "./logs",
    log_level: str = "INFO",
    component: str = "worker",
) -> logging.Logger:
    """Configure structured JSON Lines logging.

    Args:
        run_id: Unique identifier for this worker run.
        log_dir: Directory to write log files.
        log_level: Minimum log level to capture.
        component: Default component name for log entries.

    Returns:
        Configured logger instance.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_file = log_path / f"worker_{date_str}.log"

    logger = logging.getLogger("trending_news_worker")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates on re-configuration
    logger.handlers.clear()

    # File handler with JSON formatting
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter(run_id=run_id, component=component))
    logger.addHandler(file_handler)

    # Console handler with simpler format for readability
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger


def get_component_logger(
    logger: logging.Logger, component: str
) -> logging.LoggerAdapter:
    """Get a logger adapter that adds a component field to all log entries.

    Args:
        logger: Base logger instance.
        component: Component name to tag log entries with.

    Returns:
        LoggerAdapter that injects the component field.
    """

    class ComponentAdapter(logging.LoggerAdapter):
        def process(
            self, msg: str, kwargs: Any
        ) -> tuple[str, dict[str, Any]]:
            kwargs.setdefault("extra", {})["component"] = component
            return msg, kwargs["extra"]

    return ComponentAdapter(logger, extra={"component": component})
