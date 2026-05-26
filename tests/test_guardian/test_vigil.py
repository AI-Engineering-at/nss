"""Tests for VIGIL tool call safety."""

from nss.guardian.vigil import check_tool_call


def test_allowed_tool_passes() -> None:
    result = check_tool_call("search", {"query": "test"}, "user-1")
    assert result["verdict"] == "ALLOW"


def test_unknown_tool_blocked() -> None:
    result = check_tool_call("dangerous_tool", {}, "user-1")
    assert result["verdict"] == "DENY"
    assert result["checks"]["confidentiality"] is False


def test_suspicious_chars_blocked() -> None:
    result = check_tool_call(
        "search",
        {"query": "test; rm -rf /"},
        "user-1",
    )
    assert result["verdict"] == "DENY"
    assert result["checks"]["integrity"] is False
