"""Tests for PNC compression."""

from nss.gateway.pnc_compression import _deduplicate_phrases, _remove_fillers, compress


def test_deduplicate_removes_repeated_sentences() -> None:
    text = "Hello world. Hello world. Another sentence."
    result = _deduplicate_phrases(text)
    assert result.count("Hello world") == 1
    assert "Another sentence" in result


def test_remove_fillers() -> None:
    text = "I basically want to um find the answer honestly"
    result = _remove_fillers(text)
    assert "basically" not in result
    assert "um" not in result
    assert "honestly" not in result
    assert "find" in result
    assert "answer" in result


def test_compress_verbose_input() -> None:
    text = "I basically want to um find the answer. I basically want to um find the answer. Please help."
    compressed, ratio, meta = compress(text)
    assert ratio > 0
    assert meta["compressed_length"] < meta["original_length"]
    assert len(meta["steps"]) > 0


def test_compress_short_input_unchanged() -> None:
    text = "What is 2+2?"
    compressed, ratio, meta = compress(text)
    assert compressed == text
    assert ratio == 0.0


def test_compress_empty_input() -> None:
    compressed, ratio, meta = compress("")
    assert compressed == ""
    assert ratio == 0.0


def test_compress_truncation() -> None:
    # Create very long text
    text = "word " * 5000
    compressed, ratio, meta = compress(text, max_tokens=100)
    assert "[TRUNCATED]" in compressed
    assert "truncation" in meta["steps"]
