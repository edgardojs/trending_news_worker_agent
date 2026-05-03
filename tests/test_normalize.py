"""Tests for the normalize module."""

import pytest

from src.normalize import normalize_text, normalize_title, extract_domain, compute_hash


def test_normalize_text_lowercase():
    """Test that text is lowercased."""
    assert normalize_text("HELLO WORLD") == "hello world"


def test_normalize_text_trim():
    """Test that whitespace is trimmed."""
    assert normalize_text("  hello  ") == "hello"


def test_normalize_text_urls():
    """Test that URLs are removed."""
    result = normalize_text("Check https://example.com for more")
    assert "https://example.com" not in result
    assert "check" in result


def test_normalize_text_punctuation():
    """Test that excessive punctuation is removed."""
    result = normalize_text("Hello!!! How are you???")
    assert "!!!" not in result
    assert "???" not in result


def test_normalize_text_empty():
    """Test that empty string returns empty."""
    assert normalize_text("") == ""


def test_normalize_title_removes_stopwords():
    """Test that normalize_title removes stopwords."""
    result = normalize_title("The Climate Summit is a Big Deal")
    # "the", "is", "a" should be removed
    assert "the" not in result.lower().split()
    assert "climate" in result.lower()


def test_extract_domain():
    """Test domain extraction from URLs."""
    assert extract_domain("https://www.bbc.co.uk/news") == "bbc.co.uk"
    assert extract_domain("http://example.com/path") == "example.com"
    assert extract_domain("") == ""


def test_compute_hash():
    """Test that hash computation is deterministic."""
    h1 = compute_hash("title", "link")
    h2 = compute_hash("title", "link")
    assert h1 == h2
    assert len(h1) == 16


def test_compute_hash_different():
    """Test that different inputs produce different hashes."""
    h1 = compute_hash("title1", "link1")
    h2 = compute_hash("title2", "link2")
    assert h1 != h2