"""Tests for SHIELD defensive token injection."""

from nss.guardian.shield import APPEND_TOKENS, PREPEND_TOKENS, enhance_prompt


def test_enhance_prompt_adds_prepend() -> None:
    result = enhance_prompt("Hello world")
    assert PREPEND_TOKENS in result


def test_enhance_prompt_adds_append() -> None:
    result = enhance_prompt("Hello world")
    assert APPEND_TOKENS in result


def test_original_content_preserved() -> None:
    user_prompt = "What is quantum computing?"
    result = enhance_prompt(user_prompt)
    assert user_prompt in result


def test_system_prompt_included() -> None:
    result = enhance_prompt("Hello", system_prompt="You are a helpful assistant.")
    assert "You are a helpful assistant." in result
