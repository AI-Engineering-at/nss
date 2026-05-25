"""Tests for STEER transformation pipeline."""

from nss.gateway.steer import detect_language, normalize_prompt, steer_transform


def test_detect_language_german() -> None:
    assert detect_language("Das ist ein Test und die Antwort ist klar") == "de"


def test_detect_language_english() -> None:
    assert detect_language("This is a test and the answer is clear") == "en"


def test_normalize_prompt_whitespace() -> None:
    result = normalize_prompt("  Hello   world  \n\n  test  ")
    assert result == "Hello world test"


def test_normalize_prompt_smart_quotes() -> None:
    result = normalize_prompt("\u201cHello\u201d and \u2018world\u2019")
    assert result == '"Hello" and \'world\''


def test_steer_transform_privacy_tier_0() -> None:
    msg, meta = steer_transform("Hello world", privacy_tier=0)
    assert "[SYSTEM CONTEXT]" in msg
    assert "Privacy Level: 0" in msg
    assert "Hello world" in msg
    assert meta["privacy_tier"] == 0


def test_steer_transform_privacy_tier_3() -> None:
    msg, meta = steer_transform("Sensitive query", privacy_tier=3)
    assert "Governance-level restrictions" in msg
    assert meta["privacy_tier"] == 3


def test_steer_transform_metadata() -> None:
    msg, meta = steer_transform("Test message", privacy_tier=1)
    assert "language_detected" in meta
    assert "original_length" in meta
    assert "transformed_length" in meta
    assert meta["transformed_length"] > meta["original_length"]
