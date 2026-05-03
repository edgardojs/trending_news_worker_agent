"""Near-duplicate article detection and removal."""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from src.normalize import normalize_title


def compute_similarity(title_a: str, title_b: str) -> int:
    """Compute similarity score between two article titles.

    Uses token_set_ratio for best fuzzy comparison of titles.

    Args:
        title_a: First article title.
        title_b: Second article title.

    Returns:
        Similarity score (0-100).
    """
    norm_a = normalize_title(title_a)
    norm_b = normalize_title(title_b)

    if not norm_a or not norm_b:
        return 0

    return fuzz.token_set_ratio(norm_a, norm_b)


def deduplicate_articles(
    articles: list[dict[str, Any]],
    threshold: int = 85,
    logger: Any = None,
) -> list[dict[str, Any]]:
    """Remove near-duplicate articles, keeping the highest-scored version.

    For each group of similar articles, keeps the one with the highest
    final_score and preserves references to duplicates in metadata.

    Args:
        articles: List of scored article dicts.
        threshold: Minimum similarity score to consider articles duplicates (0-100).
        logger: Optional logger instance.

    Returns:
        Deduplicated list of article dicts.
    """
    if not articles:
        return []

    # Sort by final_score descending so we process highest-scored first
    sorted_articles = sorted(
        articles, key=lambda a: a.get("final_score", 0), reverse=True
    )

    kept: list[dict[str, Any]] = []
    duplicate_groups: list[list[str]] = []  # Track groups of duplicate IDs

    for article in sorted_articles:
        is_duplicate = False
        duplicate_of: dict[str, Any] | None = None

        for kept_article in kept:
            similarity = compute_similarity(article["title"], kept_article["title"])
            if similarity >= threshold:
                is_duplicate = True
                duplicate_of = kept_article
                break

        if is_duplicate and duplicate_of is not None:
            # Add this article's ID to the kept article's duplicate references
            if "duplicate_ids" not in duplicate_of:
                duplicate_of["duplicate_ids"] = []
            duplicate_of["duplicate_ids"].append(article.get("id", ""))
            if "duplicate_titles" not in duplicate_of:
                duplicate_of["duplicate_titles"] = []
            duplicate_of["duplicate_titles"].append(article.get("title", ""))
        else:
            kept.append(dict(article))

    if logger:
        removed_count = len(articles) - len(kept)
        logger.info(
            "Deduplication: %d articles in, %d duplicates removed, %d kept",
            len(articles),
            removed_count,
            len(kept),
        )

    return kept