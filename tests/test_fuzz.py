"""Fuzz tests using Hypothesis for property-based testing.

These tests generate random/edge-case inputs to find crashes, hangs,
and invariant violations across the core processing pipeline.

Fuzz targets:
- normalize: text normalization with arbitrary unicode/punctuation
- matcher: fuzzy matching with random strings
- deduplicate: similarity detection with near-duplicate variations
- scorer: scoring with edge-case timestamps and values
- ranker: ranking with missing fields and extreme scores
- rss._parse_article_entry: parsing with mock entries having random attributes
- trends._parse_trend_entry: parsing with mock entries having random attributes
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.deduplicate import compute_similarity, deduplicate_articles
from src.matcher import compute_match_score, match_articles_to_trends
from src.normalize import normalize_text, normalize_title
from src.ranker import rank_articles
from src.rss import _extract_domain, _get_authority_score, _parse_article_entry
from src.scorer import compute_authority_score, compute_final_score, compute_recency_score, score_articles
from src.trends import _parse_trend_entry


# ---------------------------------------------------------------------------
# Strategies – reusable input generators
# ---------------------------------------------------------------------------

# Arbitrary text including unicode, emojis, RTL, zero-width chars, etc.
text_strategy = st.text(
    alphabet=st.characters(
        min_codepoint=0,
        max_codepoint=0x10FFFF,
        # Exclude surrogates which are invalid in Python strings
        blacklist_categories=("Cs",),
    ),
    min_size=0,
    max_size=500,
)

# ASCII-only text for performance-sensitive paths
ascii_text = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=0,
    max_size=200,
)

# Realistic article titles – short, mostly printable
title_strategy = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=1,
    max_size=200,
)

# URL-like strings
url_strategy = st.sampled_from([
    "https://www.bbc.co.uk/news/story-123",
    "http://rss.cnn.com/rss/edition.rss",
    "https://example.com/article/12345",
    "ftp://invalid-protocol.net/feed",
    "",
    "not-a-url",
    "https://xn--n3h.com/",  # Punycode domain
    "http://localhost:8080/feed",
])

# Timestamp strings – mix of valid and invalid formats
timestamp_strategy = st.one_of(
    st.none(),
    st.just(""),
    st.just("not-a-date"),
    st.just("Fri, 02 May 2026 08:00:00 GMT"),
    st.just("2026-05-02T08:00:00Z"),
    st.just("2026-05-02T08:00:00+00:00"),
    st.just("2026-05-02"),
    st.just("9999999999"),  # Unix timestamp as string
    st.timedeltas(min_value=timedelta(days=-3650), max_value=timedelta(days=3650))
    .map(lambda td: (datetime.now(timezone.utc) + td).isoformat()),
)

# Authority scores
authority_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Match thresholds
threshold_strategy = st.integers(min_value=0, max_value=100)


# ---------------------------------------------------------------------------
# Fuzz tests: normalize module
# ---------------------------------------------------------------------------

class TestNormalizeFuzz:
    """Fuzz tests for text normalization."""

    @given(text=text_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_text_never_crashes(self, text: str):
        """normalize_text should never raise on arbitrary input."""
        result = normalize_text(text)
        assert isinstance(result, str)

    @given(text=text_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_title_never_crashes(self, text: str):
        """normalize_title should never raise on arbitrary input."""
        result = normalize_title(text)
        assert isinstance(result, str)

    @given(text=text_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_text_idempotent(self, text: str):
        """Normalizing already-normalized text should produce the same result."""
        first = normalize_text(text)
        second = normalize_text(first)
        assert first == second

    @given(text=text_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_text_no_urls_in_output(self, text: str):
        """URLs should be removed from normalized output."""
        result = normalize_text(text)
        assert "http://" not in result
        assert "https://" not in result

    @given(text=ascii_text)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_text_output_is_lowercase(self, text: str):
        """Normalized output should be lowercase."""
        result = normalize_text(text)
        assert result == result.lower()

    @given(text=text_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_title_removes_stopwords(self, text: str):
        """normalize_title should not contain common stopwords."""
        from src.normalize import STOPWORDS
        result = normalize_title(text)
        words = result.split()
        for word in words:
            assert word.lower() not in STOPWORDS

    @given(text=st.text(min_size=0, max_size=10))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_text_empty_string_identity(self, text: str):
        """Empty string input should return empty string."""
        result = normalize_text("")
        assert result == ""


# ---------------------------------------------------------------------------
# Fuzz tests: matcher module
# ---------------------------------------------------------------------------

class TestMatcherFuzz:
    """Fuzz tests for fuzzy matching."""

    @given(title_a=title_strategy, title_b=title_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_compute_match_score_never_crashes(self, title_a: str, title_b: str):
        """compute_match_score should never raise on arbitrary strings."""
        score = compute_match_score(title_a, title_b)
        assert isinstance(score, (int, float))
        assert 0 <= score <= 100

    @given(title=title_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_compute_match_score_self_match_high(self, title: str):
        """Matching a title against itself should yield a high score (or 0 if empty after norm)."""
        score = compute_match_score(title, title)
        norm = normalize_title(title)
        if norm:
            assert score >= 85  # Self-match should be very high
        else:
            assert score == 0

    @given(title_a=title_strategy, title_b=title_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_compute_match_score_symmetric(self, title_a: str, title_b: str):
        """Match score should be symmetric: f(a,b) == f(b,a)."""
        score_ab = compute_match_score(title_a, title_b)
        score_ba = compute_match_score(title_b, title_a)
        assert score_ab == score_ba

    @given(
        articles=st.lists(
            st.builds(
                dict,
                id=st.just("1"),
                title=title_strategy,
                link=st.just("https://example.com"),
            ),
            min_size=0,
            max_size=10,
        ),
        trends=st.lists(
            st.builds(
                dict,
                id=st.just("t1"),
                title=title_strategy,
                geo=st.just("US"),
            ),
            min_size=0,
            max_size=10,
        ),
        threshold=threshold_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_match_articles_to_trends_never_crashes(self, articles, trends, threshold):
        """match_articles_to_trends should never crash with arbitrary inputs."""
        result = match_articles_to_trends(articles, trends, threshold=threshold)
        assert isinstance(result, list)
        # All matched articles should have matched_trends and trend_match_score
        for article in result:
            assert "matched_trends" in article
            assert "trend_match_score" in article
            assert article["trend_match_score"] >= threshold


# ---------------------------------------------------------------------------
# Fuzz tests: deduplicate module
# ---------------------------------------------------------------------------

class TestDeduplicateFuzz:
    """Fuzz tests for near-duplicate detection."""

    @given(title_a=title_strategy, title_b=title_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_compute_similarity_never_crashes(self, title_a: str, title_b: str):
        """compute_similarity should never raise on arbitrary strings."""
        score = compute_similarity(title_a, title_b)
        assert isinstance(score, (int, float))
        assert 0 <= score <= 100

    @given(title=title_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_compute_similarity_self_is_100(self, title: str):
        """Similarity of a title with itself should be 100 (or 0 if empty after norm)."""
        score = compute_similarity(title, title)
        norm = normalize_title(title)
        if norm:
            assert score == 100
        else:
            assert score == 0

    @given(title_a=title_strategy, title_b=title_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_compute_similarity_symmetric(self, title_a: str, title_b: str):
        """Similarity should be symmetric."""
        score_ab = compute_similarity(title_a, title_b)
        score_ba = compute_similarity(title_b, title_a)
        assert score_ab == score_ba

    @given(
        articles=st.lists(
            st.builds(
                dict,
                id=st.text(min_size=1, max_size=10),
                title=title_strategy,
                link=st.just("https://example.com"),
                final_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            ),
            min_size=0,
            max_size=20,
        ),
        threshold=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_deduplicate_articles_never_crashes(self, articles, threshold):
        """deduplicate_articles should never crash with arbitrary inputs."""
        result = deduplicate_articles(articles, threshold=threshold)
        assert isinstance(result, list)
        assert len(result) <= len(articles)

    @given(
        articles=st.lists(
            st.builds(
                dict,
                id=st.text(min_size=1, max_size=10),
                title=title_strategy,
                link=st.just("https://example.com"),
                final_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            ),
            min_size=0,
            max_size=20,
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_deduplicate_preserves_highest_scored(self, articles):
        """Deduplication should never keep a lower-scored article over a higher-scored duplicate."""
        result = deduplicate_articles(articles, threshold=85)
        if len(articles) > 1 and result:
            # The highest-scored article should always be in the result
            max_score = max(a.get("final_score", 0) for a in articles)
            result_scores = [a.get("final_score", 0) for a in result]
            assert max_score in result_scores


# ---------------------------------------------------------------------------
# Fuzz tests: scorer module
# ---------------------------------------------------------------------------

class TestScorerFuzz:
    """Fuzz tests for composite scoring."""

    @given(published=timestamp_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_compute_recency_score_never_crashes(self, published):
        """compute_recency_score should never crash on any timestamp string."""
        score = compute_recency_score(published)
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    @given(published=timestamp_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_compute_recency_score_empty_string_zero(self, published):
        """Empty string should always return 0.0."""
        assert compute_recency_score("") == 0.0

    @given(source=st.builds(dict, authority_score=authority_strategy))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_compute_authority_score_range(self, source):
        """Authority score should be between 0 and 100."""
        score = compute_authority_score(source)
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    @given(source=st.builds(dict))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_compute_authority_score_missing_field(self, source):
        """Missing authority_score should default to 50.0."""
        score = compute_authority_score(source)
        assert score == 50.0

    @given(
        trend_match_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        recency_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        authority_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_compute_final_score_range(self, trend_match_score, recency_score, authority_score):
        """Final score should be between 0 and 100 with default weights."""
        score = compute_final_score(trend_match_score, recency_score, authority_score)
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    @given(
        trend_match_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        recency_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        authority_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_compute_final_score_perfect_inputs(self, trend_match_score, recency_score, authority_score):
        """Final score should be deterministic for same inputs."""
        score1 = compute_final_score(trend_match_score, recency_score, authority_score)
        score2 = compute_final_score(trend_match_score, recency_score, authority_score)
        assert score1 == score2


# ---------------------------------------------------------------------------
# Fuzz tests: ranker module
# ---------------------------------------------------------------------------

class TestRankerFuzz:
    """Fuzz tests for article ranking."""

    def _make_article(self, id_str="1", title="Test", score=50.0, published="", auth=50.0):
        return {
            "id": id_str,
            "title": title,
            "final_score": score,
            "published": published,
            "authority_score": auth,
        }

    @given(
        scores=st.lists(
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            min_size=0,
            max_size=50,
        ),
        max_articles=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_rank_articles_never_crashes(self, scores, max_articles):
        """rank_articles should never crash with arbitrary score lists."""
        articles = [
            self._make_article(id_str=str(i), title=f"Article {i}", score=s)
            for i, s in enumerate(scores)
        ]
        result = rank_articles(articles, max_articles=max_articles)
        assert isinstance(result, list)
        assert len(result) <= len(articles)
        assert len(result) <= max_articles

    @given(max_articles=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_rank_articles_empty_list(self, max_articles):
        """Empty list should return empty list."""
        result = rank_articles([], max_articles=max_articles)
        assert result == []

    @given(
        scores=st.lists(
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_rank_articles_descending_order(self, scores):
        """Ranked articles should be in descending score order."""
        articles = [
            self._make_article(id_str=str(i), title=f"Article {i}", score=s)
            for i, s in enumerate(scores)
        ]
        result = rank_articles(articles, max_articles=100)
        for i in range(len(result) - 1):
            assert result[i]["final_score"] >= result[i + 1]["final_score"]

    @given(
        scores=st.lists(
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_rank_articles_ranks_are_sequential(self, scores):
        """Ranks should be sequential starting from 1."""
        articles = [
            self._make_article(id_str=str(i), title=f"Article {i}", score=s)
            for i, s in enumerate(scores)
        ]
        result = rank_articles(articles, max_articles=100)
        for i, article in enumerate(result):
            assert article["rank"] == i + 1

    @given(
        articles=st.lists(
            st.builds(
                lambda id_s, title, score, pub, auth: {
                    "id": id_s,
                    "title": title,
                    "final_score": score,
                    "published": pub,
                    "authority_score": auth,
                },
                id_s=st.text(min_size=1, max_size=10),
                title=title_strategy,
                score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
                pub=st.one_of(st.just(""), st.just("2026-05-02T08:00:00Z")),
                auth=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            ),
            min_size=0,
            max_size=20,
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_rank_articles_with_missing_fields(self, articles):
        """rank_articles should handle articles with missing optional fields."""
        # Remove some fields randomly to test robustness
        import random
        for article in articles:
            if random.random() < 0.3 and "published" in article:
                del article["published"]
            if random.random() < 0.3 and "authority_score" in article:
                del article["authority_score"]
        result = rank_articles(articles, max_articles=50)
        assert isinstance(result, list)
        assert len(result) <= len(articles)


# ---------------------------------------------------------------------------
# Fuzz tests: RSS parsing
# ---------------------------------------------------------------------------

class TestRSSParseFuzz:
    """Fuzz tests for RSS article parsing."""

    @given(
        title=text_strategy,
        link=url_strategy,
        summary=text_strategy,
        published=st.one_of(st.just(""), st.just("Fri, 02 May 2026 08:00:00 GMT")),
        feed_url=url_strategy,
        feed_name=text_strategy,
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_parse_article_entry_never_crashes(self, title, link, summary, published, feed_url, feed_name):
        """_parse_article_entry should never crash with arbitrary inputs."""
        entry = MagicMock(spec=[])
        entry.title = title
        entry.link = link
        entry.summary = summary
        entry.published = published

        result = _parse_article_entry(entry, feed_url, feed_name)
        assert isinstance(result, dict)
        assert "id" in result
        assert "title" in result
        assert "link" in result
        assert "source" in result

    @given(url=url_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_extract_domain_never_crashes(self, url: str):
        """_extract_domain should never crash on arbitrary URLs."""
        domain = _extract_domain(url)
        assert isinstance(domain, str)

    @given(url=url_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_get_authority_score_range(self, url: str):
        """_get_authority_score should always return a value between 0 and 1."""
        score = _get_authority_score(url)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    @given(
        title=text_strategy,
        link=url_strategy,
        summary=st.one_of(st.just(""), st.just("Short summary")),
        published=st.one_of(
            st.just(""),
            st.just("not-a-date"),
            st.just("Fri, 02 May 2026 08:00:00 GMT"),
            st.just("2026-05-02T08:00:00Z"),
        ),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_parse_article_entry_timestamp_handling(self, title, link, summary, published):
        """_parse_article_entry should handle all timestamp formats gracefully."""
        entry = MagicMock(spec=[])
        entry.title = title
        entry.link = link
        entry.summary = summary
        entry.published = published

        result = _parse_article_entry(entry, "http://example.com/feed.xml", "Test")
        assert "published" in result
        # Should either be empty string or a valid ISO timestamp
        if result["published"]:
            # If not empty, it should be parseable
            assert isinstance(result["published"], str)


# ---------------------------------------------------------------------------
# Fuzz tests: Trends parsing
# ---------------------------------------------------------------------------

class TestTrendsParseFuzz:
    """Fuzz tests for Google Trends parsing."""

    @given(
        title=text_strategy,
        link=url_strategy,
        published=st.one_of(st.just(""), st.just("Fri, 02 May 2026 10:00:00 GMT")),
        geo=st.text(min_size=0, max_size=5),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_parse_trend_entry_never_crashes(self, title, link, published, geo):
        """_parse_trend_entry should never crash with arbitrary inputs."""
        entry = MagicMock(spec=[])
        entry.title = title
        entry.link = link
        entry.published = published

        result = _parse_trend_entry(entry, geo)
        assert isinstance(result, dict)
        assert "id" in result
        assert "title" in result
        assert "geo" in result

    @given(
        title=text_strategy,
        link=url_strategy,
        published=st.one_of(st.just(""), st.just("not-a-date"), st.just("2026-05-02T10:00:00Z")),
        geo=st.text(min_size=0, max_size=5),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_parse_trend_entry_timestamp_handling(self, title, link, published, geo):
        """_parse_trend_entry should handle all timestamp formats gracefully."""
        entry = MagicMock(spec=[])
        entry.title = title
        entry.link = link
        entry.published = published

        result = _parse_trend_entry(entry, geo)
        assert "timestamp" in result
        if result["timestamp"]:
            assert isinstance(result["timestamp"], str)


# ---------------------------------------------------------------------------
# Fuzz tests: End-to-end pipeline
# ---------------------------------------------------------------------------

class TestPipelineFuzz:
    """Fuzz tests for the full processing pipeline (match → score → dedup → rank)."""

    @given(
        article_titles=st.lists(title_strategy, min_size=0, max_size=15),
        trend_titles=st.lists(title_strategy, min_size=0, max_size=10),
        threshold=st.integers(min_value=50, max_value=95),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_match_score_dedup_rank_pipeline(self, article_titles, trend_titles, threshold):
        """Full pipeline should never crash with arbitrary titles."""
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)

        articles = [
            {
                "id": f"a-{i}",
                "title": title,
                "link": f"https://example.com/{i}",
                "published": (now - timedelta(hours=i)).isoformat(),
                "source": {"name": "Test", "url": "http://example.com", "authority_score": 0.7},
            }
            for i, title in enumerate(article_titles)
        ]

        trends = [
            {"id": f"t-{i}", "title": title, "geo": "US"}
            for i, title in enumerate(trend_titles)
        ]

        # Match
        matched = match_articles_to_trends(articles, trends, threshold=threshold)
        assert isinstance(matched, list)

        # Score
        from src.config import ScoringConfig
        scored = score_articles(matched, ScoringConfig())
        assert isinstance(scored, list)

        # Deduplicate
        deduped = deduplicate_articles(scored, threshold=85)
        assert isinstance(deduped, list)
        assert len(deduped) <= len(scored)

        # Rank
        ranked = rank_articles(deduped, max_articles=20)
        assert isinstance(ranked, list)
        assert len(ranked) <= 20

        # Verify ranks are sequential
        for i, article in enumerate(ranked):
            assert article["rank"] == i + 1

        # Verify descending score order
        for i in range(len(ranked) - 1):
            assert ranked[i]["final_score"] >= ranked[i + 1]["final_score"]