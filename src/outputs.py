"""JSON and Markdown report generation for the Trending News Worker Agent."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import AppConfig
from src.exceptions import OutputError


def _generate_run_id() -> str:
    """Generate a unique run ID based on the current timestamp.

    Returns:
        Run ID string in format: trending_news_YYYYMMDD_HHMMSS
    """
    now = datetime.now(timezone.utc)
    return f"trending_news_{now.strftime('%Y%m%d_%H%M%S')}"


def _build_json_report(
    run_id: str,
    config: AppConfig,
    trends: list[dict[str, Any]],
    articles_matched: list[dict[str, Any]],
    articles_after_dedup: list[dict[str, Any]],
    ranked_articles: list[dict[str, Any]],
    total_fetched: int,
) -> dict[str, Any]:
    """Build the JSON report data structure.

    Args:
        run_id: Unique run identifier.
        config: Application configuration.
        trends: List of trend dicts.
        articles_matched: Articles matched to trends.
        articles_after_dedup: Articles after deduplication.
        ranked_articles: Final ranked articles.
        total_fetched: Total number of articles fetched.

    Returns:
        Report dict ready for JSON serialization.
    """
    # Build ranked articles output
    ranked_output: list[dict[str, Any]] = []
    for article in ranked_articles:
        # Safely extract source name — source may be a dict, str, or missing
        raw_source = article.get("source", {})
        if isinstance(raw_source, dict):
            source_name = raw_source.get("name", "")
        elif isinstance(raw_source, str):
            source_name = raw_source
        else:
            source_name = ""

        entry: dict[str, Any] = {
            "rank": article.get("rank", 0),
            "title": article.get("title", ""),
            "link": article.get("link", ""),
            "source": source_name,
            "published": article.get("published", ""),
            "trend_score": article.get("final_score") or 0,
        }

        if config.output.include_trend_matches:
            entry["matched_trends"] = article.get("matched_trends", [])

        if config.output.include_scores:
            entry["scores"] = {
                "trend_match": article.get("trend_match_score") or 0,
                "recency": article.get("recency_score") or 0,
                "authority": article.get("authority_score") or 0,
                "final": article.get("final_score") or 0,
            }

        ranked_output.append(entry)

    # Build top trends output
    top_trends: list[dict[str, Any]] = [
        {"trend": t.get("title", ""), "volume": t.get("search_volume", "")}
        for t in trends[:10]  # Top 10 trends
    ]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "config": {
            "geo": config.trends.geo,
            "window_hours": config.trends.window_hours,
        },
        "summary": {
            "total_articles_fetched": total_fetched,
            "articles_matched": len(articles_matched),
            "articles_after_dedup": len(articles_after_dedup),
        },
        "ranked_articles": ranked_output,
        "top_trends": top_trends,
    }

    return report


def write_json_report(
    report: dict[str, Any],
    output_dir: str,
    run_id: str,
) -> Path:
    """Write the JSON report to a file.

    Args:
        report: Report data dict.
        output_dir: Directory to write the report file.
        run_id: Unique run identifier for the filename.

    Returns:
        Path to the written JSON file.

    Raises:
        OutputError: If the file cannot be written.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Extract timestamp from run_id for filename
    # run_id format: trending_news_YYYYMMDD_HHMMSS
    timestamp = run_id.replace("trending_news_", "")
    filename = f"trending_news_{timestamp}.json"
    filepath = output_path / filename

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return filepath
    except (OSError, TypeError, ValueError) as e:
        raise OutputError(f"Failed to write JSON report: {e}") from e


def write_markdown_report(
    report: dict[str, Any],
    output_dir: str,
    run_id: str,
) -> Path:
    """Write the Markdown report to a file.

    Args:
        report: Report data dict.
        output_dir: Directory to write the report file.
        run_id: Unique run identifier for the filename.

    Returns:
        Path to the written Markdown file.

    Raises:
        OutputError: If the file cannot be written.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = run_id.replace("trending_news_", "")
    filename = f"trending_news_{timestamp}.md"
    filepath = output_path / filename

    try:
        lines: list[str] = []

        # Title
        lines.append("# Trending News Report")
        lines.append("")

        # Metadata
        lines.append(f"**Generated:** {report['generated_at']}  ")
        lines.append(f"**Run ID:** {report['run_id']}  ")
        lines.append(f"**Region:** {report['config']['geo']}  ")
        lines.append(f"**Window:** {report['config']['window_hours']} hours  ")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        summary = report["summary"]
        lines.append(f"- **Total articles fetched:** {summary['total_articles_fetched']}")
        lines.append(f"- **Articles matched to trends:** {summary['articles_matched']}")
        lines.append(f"- **Articles after deduplication:** {summary['articles_after_dedup']}")
        lines.append("")

        # Top Trends
        lines.append("## Top Trends")
        lines.append("")
        for i, trend in enumerate(report.get("top_trends", [])):
            volume = trend.get("volume", "")
            volume_str = f" ({volume})" if volume else ""
            lines.append(f"{i + 1}. **{trend['trend']}**{volume_str}")
        lines.append("")

        # Ranked Articles
        lines.append("## Ranked Articles")
        lines.append("")
        for article in report.get("ranked_articles", []):
            rank = article.get("rank", 0)
            title = article.get("title", "Untitled")
            link = article.get("link", "")
            source = article.get("source", "Unknown")
            published = article.get("published", "")
            score = article.get("trend_score") or 0

            lines.append(f"### {rank}. {title}")
            lines.append("")
            lines.append(f"- **Source:** {source}")
            lines.append(f"- **Published:** {published}")
            lines.append(f"- **Trend Score:** {score:.1f}")
            lines.append(f"- **Link:** {link}")

            # Show matched trends
            matched = article.get("matched_trends", [])
            if matched:
                lines.append("- **Matched Trends:**")
                for m in matched:
                    lines.append(f"  - {m['trend']} (match: {m['match_score']})")

            # Show score breakdown
            scores = article.get("scores", {})
            if scores:
                trend_match = scores.get("trend_match") or 0
                recency = scores.get("recency") or 0
                authority = scores.get("authority") or 0
                lines.append("- **Score Breakdown:**")
                lines.append(
                    f"  - Trend Match: {trend_match:.1f} | "
                    f"Recency: {recency:.1f} | "
                    f"Authority: {authority:.1f}"
                )

            lines.append("")

        # Warnings
        warnings = report.get("warnings", [])
        if warnings:
            lines.append("## Warnings")
            lines.append("")
            for warning in warnings:
                lines.append(f"- ⚠️ {warning}")
            lines.append("")

        content = "\n".join(lines)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath

    except (OSError, TypeError, ValueError) as e:
        raise OutputError(f"Failed to write Markdown report: {e}") from e


def generate_reports(
    config: AppConfig,
    trends: list[dict[str, Any]],
    articles_matched: list[dict[str, Any]],
    articles_after_dedup: list[dict[str, Any]],
    ranked_articles: list[dict[str, Any]],
    total_fetched: int,
    run_id: str | None = None,
    warnings: list[str] | None = None,
    logger: Any = None,
) -> tuple[Path | None, Path | None]:
    """Generate all configured output reports.

    Args:
        config: Application configuration.
        trends: List of trend dicts.
        articles_matched: Articles matched to trends.
        articles_after_dedup: Articles after deduplication.
        ranked_articles: Final ranked articles.
        total_fetched: Total number of articles fetched.
        run_id: Optional run ID (auto-generated if not provided).
        warnings: Optional list of warning messages.
        logger: Optional logger instance.

    Returns:
        Tuple of (json_path, markdown_path) - either may be None if format not configured.
    """
    if run_id is None:
        run_id = _generate_run_id()

    report = _build_json_report(
        run_id=run_id,
        config=config,
        trends=trends,
        articles_matched=articles_matched,
        articles_after_dedup=articles_after_dedup,
        ranked_articles=ranked_articles,
        total_fetched=total_fetched,
    )

    if warnings:
        report["warnings"] = warnings

    json_path = None
    markdown_path = None

    if "json" in config.output.formats:
        json_path = write_json_report(report, config.general.output_dir, run_id)
        if logger:
            logger.info("JSON report written to %s", json_path)

    if "markdown" in config.output.formats:
        markdown_path = write_markdown_report(
            report, config.general.output_dir, run_id
        )
        if logger:
            logger.info("Markdown report written to %s", markdown_path)

    return json_path, markdown_path
