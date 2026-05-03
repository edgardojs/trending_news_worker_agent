#!/usr/bin/env python3
"""Health check script for the Trending News Worker Agent.

Checks:
1. Find the newest JSON output file.
2. Fail if no output exists.
3. Warn if newest output is older than two hours.
4. Validate that ranked_articles exists.
5. Warn if zero articles were ranked.
6. Print a human-readable status line.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "output"
DEFAULT_CACHE_DIR = Path(__file__).parent.parent / "cache"
MAX_AGE_HOURS = 2


def find_newest_json(output_dir: Path) -> Path | None:
    """Find the most recent JSON output file.

    Args:
        output_dir: Directory containing output files.

    Returns:
        Path to the newest JSON file, or None if no files found.
    """
    json_files = sorted(output_dir.glob("trending_news_*.json"), reverse=True)
    return json_files[0] if json_files else None


def check_health(output_dir: Path) -> tuple[int, list[str]]:
    """Run health checks and return status.

    Args:
        output_dir: Directory containing output files.

    Returns:
        Tuple of (exit_code, list of status messages).
    """
    messages: list[str] = []
    exit_code = 0

    # Check 1: Find newest JSON output
    newest = find_newest_json(output_dir)
    if newest is None:
        messages.append("CRITICAL: No JSON output files found")
        return 1, messages

    messages.append(f"Newest output: {newest.name}")

    # Check 2: Check age of newest output
    try:
        stat = newest.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - modified).total_seconds() / 3600

        if age_hours > MAX_AGE_HOURS:
            messages.append(
                f"WARNING: Newest output is {age_hours:.1f} hours old "
                f"(threshold: {MAX_AGE_HOURS} hours)"
            )
            exit_code = 0  # Warning, not failure
        else:
            messages.append(f"Output age: {age_hours:.1f} hours (OK)")
    except OSError as e:
        messages.append(f"ERROR: Cannot stat output file: {e}")
        return 1, messages

    # Check 3: Validate JSON content
    try:
        with open(newest, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        messages.append(f"ERROR: Cannot parse JSON output: {e}")
        return 1, messages

    # Check 4: Validate ranked_articles exists
    if "ranked_articles" not in data:
        messages.append("ERROR: ranked_articles field missing from output")
        return 1, messages

    ranked = data.get("ranked_articles", [])
    summary = data.get("summary", {})

    # Check 5: Warn if zero articles ranked
    if len(ranked) == 0:
        messages.append("WARNING: Zero articles ranked in output")
    else:
        messages.append(f"Ranked articles: {len(ranked)} (OK)")

    # Print summary
    total_fetched = summary.get("total_articles_fetched", 0)
    matched = summary.get("articles_matched", 0)
    after_dedup = summary.get("articles_after_dedup", 0)

    messages.append(
        f"Summary: {total_fetched} fetched, {matched} matched, "
        f"{after_dedup} after dedup, {len(ranked)} ranked"
    )

    return exit_code, messages


def main() -> None:
    """CLI entry point for health check."""
    import argparse

    parser = argparse.ArgumentParser(description="Trending News Worker Health Check")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Path to output directory",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    exit_code, messages = check_health(output_dir)

    print("=" * 50)
    print("Trending News Worker - Health Check")
    print("=" * 50)
    for msg in messages:
        print(f"  {msg}")
    print("=" * 50)

    status = "OK" if exit_code == 0 else "FAILED"
    print(f"Status: {status}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()