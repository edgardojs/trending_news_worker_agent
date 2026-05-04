#!/usr/bin/env python3
"""Trending News Worker Agent - Main entry point.

A lightweight Google Trends + RSS trending news worker that:
1. Fetches Google Trends RSS/Atom data
2. Fetches configured RSS news feeds
3. Normalizes both datasets
4. Matches articles against trending search terms
5. Scores article relevance
6. Deduplicates near-duplicates
7. Ranks the results
8. Produces JSON and Markdown reports

Usage:
    python worker.py --config config.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone

from src.cache_sqlite import CacheDB
from src.config import ensure_directories, load_config
from src.deduplicate import deduplicate_articles
from src.exceptions import CacheError, ConfigError, OutputError
from src.logging_setup import get_component_logger, setup_logging
from src.matcher import match_articles_to_trends
from src.outputs import generate_reports
from src.ranker import rank_articles
from src.rss import fetch_rss_feeds
from src.scorer import score_articles
from src.trends import fetch_trends


def generate_run_id() -> str:
    """Generate a unique run ID based on the current timestamp.

    Returns:
        Run ID string in format: trending_news_YYYYMMDD_HHMMSS
    """
    now = datetime.now(timezone.utc)
    return f"trending_news_{now.strftime('%Y%m%d_%H%M%S')}"


def compute_output_hash(report_data: dict) -> str:
    """Compute a deterministic hash of the output for idempotency checks.

    Args:
        report_data: The report data dict.

    Returns:
        SHA-256 hex digest of the serialized report.
    """
    # Sort keys for deterministic serialization
    serialized = json.dumps(report_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:32]


def run_worker(config_path: str) -> int:
    """Main worker execution function.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Exit code: 0 for success, non-zero for various failure modes.
    """
    run_id = generate_run_id()
    logger = None
    cache = None
    warnings: list[str] = []

    try:
        # --- Load Configuration ---
        try:
            config = load_config(config_path)
        except ConfigError as e:
            print(f"Configuration error: {e}", file=sys.stderr)
            return 1

        # --- Setup Directories and Logging ---
        ensure_directories(config)
        logger = setup_logging(
            run_id=run_id,
            log_dir=config.general.log_dir,
            log_level=config.general.log_level,
        )
        log = get_component_logger(logger, "worker")

        log.info("Starting trending news worker (run_id=%s)", run_id)
        start_time = time.time()

        # --- Initialize Cache ---
        try:
            cache = CacheDB(config)
            cache.connect()
            cache.start_run(run_id)
            log.info("Cache initialized at %s", config.cache.sqlite_path)
        except CacheError as e:
            log.warning("Cache initialization failed, continuing without cache: %s", e)
            cache = None

        # --- Fetch Google Trends ---
        log.info("Fetching Google Trends data (geo=%s)", config.trends.geo)
        trends = fetch_trends(config=config, logger=get_component_logger(logger, "trends"), cache=cache)
        log.info("Fetched %d trending topics", len(trends))

        if not trends:
            warnings.append("No trending topics found - results may be limited")

        # --- Fetch RSS Feeds ---
        log.info("Fetching RSS feeds (%d configured)", len(config.rss.feeds))
        articles = fetch_rss_feeds(config=config, logger=get_component_logger(logger, "rss"), cache=cache)
        total_fetched = len(articles)
        log.info("Fetched %d total articles from RSS feeds", total_fetched)

        if not articles:
            warnings.append("No articles fetched from RSS feeds")

        # --- Match Articles to Trends ---
        log.info("Matching articles to trends (threshold=%d)", config.scoring.fuzzy_threshold)
        matched = match_articles_to_trends(
            articles=articles,
            trends=trends,
            threshold=config.scoring.fuzzy_threshold,
            logger=get_component_logger(logger, "matcher"),
        )
        log.info("Matched %d articles to trends", len(matched))

        # --- Score Articles ---
        log.info("Scoring matched articles")
        scored = score_articles(
            articles=matched,
            scoring_config=config.scoring,
            logger=get_component_logger(logger, "scorer"),
        )

        # --- Deduplicate ---
        if config.deduplication.enabled:
            log.info("Deduplicating articles (threshold=%d)", config.deduplication.threshold)
            deduped = deduplicate_articles(
                articles=scored,
                threshold=config.deduplication.threshold,
                logger=get_component_logger(logger, "deduplicate"),
            )
        else:
            log.info("Deduplication disabled, skipping")
            deduped = scored

        # --- Rank ---
        log.info("Ranking articles (max=%d)", config.output.max_ranked_articles)
        ranked = rank_articles(
            articles=deduped,
            max_articles=config.output.max_ranked_articles,
            logger=get_component_logger(logger, "ranker"),
        )

        # --- Generate Reports ---
        log.info("Generating output reports")
        generate_reports(
            config=config,
            trends=trends,
            articles_matched=matched,
            articles_after_dedup=deduped,
            ranked_articles=ranked,
            total_fetched=total_fetched,
            run_id=run_id,
            warnings=warnings,
            logger=get_component_logger(logger, "outputs"),
        )

        # --- Save to Cache ---
        if cache:
            try:
                # Save processed articles
                for article in ranked:
                    article_hash = article.get("id", "")
                    if article_hash:
                        cache.save_processed_article(
                            article_hash=article_hash,
                            title=article.get("title", ""),
                            link=article.get("link", ""),
                            source=article.get("source", {}).get("name", ""),
                            trend_score=article.get("final_score", 0),
                            run_id=run_id,
                        )

                # Compute output hash for idempotency
                output_hash = compute_output_hash(
                    {"run_id": run_id, "ranked_count": len(ranked)}
                )
                cache.complete_run(run_id, status="completed", output_hash=output_hash)
                log.info("Run completed and saved to cache")
            except CacheError as e:
                log.warning("Failed to save run to cache: %s", e)

        elapsed = time.time() - start_time
        log.info(
            "Worker completed successfully in %.1f seconds "
            "(%d trends, %d articles, %d matched, %d ranked)",
            elapsed,
            len(trends),
            total_fetched,
            len(matched),
            len(ranked),
        )

        return 0

    except OutputError as e:
        if logger:
            logger.critical("Output error: %s", e)
        else:
            print(f"Output error: {e}", file=sys.stderr)
        return 4

    except Exception as e:
        if logger:
            logger.critical("Unexpected error: %s", e, exc_info=True)
        else:
            print(f"Unexpected error: {e}", file=sys.stderr)
        return 5

    finally:
        if cache:
            try:
                cache.close()
            except Exception:
                pass


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Trending News Worker Agent - Fetch, match, score, and rank trending news."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the YAML configuration file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    args = parser.parse_args()

    exit_code = run_worker(args.config)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
