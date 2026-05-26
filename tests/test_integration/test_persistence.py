"""Tests for Redis persistence in AuditLogger and PrivacyBudgetTracker.

These tests verify the persistence layer works correctly:
- With Redis unavailable (graceful degradation)
- Constructor accepts redis_url parameter
- In-memory behaviour is unchanged
"""

from __future__ import annotations

from nss.audit import AuditLogger
from nss.governance.privacy_budget import PrivacyBudgetTracker

# ---------------------------------------------------------------------------
# AuditLogger persistence tests
# ---------------------------------------------------------------------------


class TestAuditLoggerPersistence:
    """AuditLogger with Redis persistence."""

    def test_graceful_degradation_without_redis(self):
        """AuditLogger works normally when Redis is unreachable."""
        al = AuditLogger(redis_url="redis://localhost:59999/0")
        assert al.redis_available is False
        aid = al.log_event("test", "u1", "gateway", "test")
        assert al.count == 1
        trail = al.get_trail(audit_id=aid)
        assert len(trail) == 1
        assert trail[0]["event"] == "test"

    def test_no_redis_url_means_in_memory_only(self):
        """When no redis_url is given, operates in-memory only."""
        al = AuditLogger()
        assert al.redis_available is False
        al.log_event("e1", "u1", "guardian", "mars")
        al.log_event("e2", "u1", "guardian", "sentinel")
        assert al.count == 2
        assert al.verify_integrity() is True

    def test_redis_url_empty_string(self):
        """Empty string redis_url is treated as disabled."""
        al = AuditLogger(redis_url="")
        assert al.redis_available is False

    def test_hash_chain_intact_after_multiple_events(self):
        """Hash chain integrity is maintained with persistence layer."""
        al = AuditLogger(redis_url="redis://localhost:59999/0")  # unreachable
        for i in range(10):
            al.log_event(f"event_{i}", "u1", "gateway", "test")
        assert al.count == 10
        assert al.verify_integrity() is True


# ---------------------------------------------------------------------------
# PrivacyBudgetTracker persistence tests
# ---------------------------------------------------------------------------


class TestPrivacyBudgetPersistence:
    """PrivacyBudgetTracker with Redis persistence."""

    def test_graceful_degradation_without_redis(self):
        """Tracker works normally when Redis is unreachable."""
        pbt = PrivacyBudgetTracker(total_budget=1.0, redis_url="redis://localhost:59999/0")
        assert pbt.redis_available is False
        assert pbt.remaining("user1") == 1.0
        assert pbt.consume(0.3, "user1") is True
        assert abs(pbt.remaining("user1") - 0.7) < 1e-9

    def test_no_redis_url_means_in_memory_only(self):
        """When no redis_url is given, operates in-memory only."""
        pbt = PrivacyBudgetTracker(total_budget=2.0)
        assert pbt.redis_available is False
        pbt.consume(0.5, "u1")
        assert abs(pbt.remaining("u1") - 1.5) < 1e-9

    def test_redis_url_empty_string(self):
        """Empty string redis_url is treated as disabled."""
        pbt = PrivacyBudgetTracker(redis_url="")
        assert pbt.redis_available is False

    def test_budget_reset_works_without_redis(self):
        """Reset restores full budget even without Redis."""
        pbt = PrivacyBudgetTracker(total_budget=1.0, redis_url="redis://localhost:59999/0")
        pbt.consume(0.5, "u1")
        pbt.reset("u1")
        assert pbt.remaining("u1") == 1.0

    def test_budget_exhaustion_without_redis(self):
        """Budget exhaustion is enforced without Redis."""
        pbt = PrivacyBudgetTracker(total_budget=0.2, redis_url="redis://localhost:59999/0")
        assert pbt.consume(0.1, "u1") is True
        assert pbt.consume(0.1, "u1") is True
        assert pbt.consume(0.1, "u1") is False  # exhausted
