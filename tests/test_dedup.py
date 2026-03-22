"""Tests for MessageDedup."""

import time

from tg_gemini.dedup import MessageDedup


class TestIsDuplicate:
    def test_first_occurrence_not_duplicate(self) -> None:
        d = MessageDedup()
        assert d.is_duplicate("msg-1") is False

    def test_second_occurrence_is_duplicate(self) -> None:
        d = MessageDedup()
        d.is_duplicate("msg-1")
        assert d.is_duplicate("msg-1") is True

    def test_empty_id_never_duplicate(self) -> None:
        d = MessageDedup()
        assert d.is_duplicate("") is False
        assert d.is_duplicate("") is False

    def test_different_ids_independent(self) -> None:
        d = MessageDedup()
        assert d.is_duplicate("a") is False
        assert d.is_duplicate("b") is False
        assert d.is_duplicate("a") is True
        assert d.is_duplicate("b") is True

    def test_expired_entry_not_duplicate(self) -> None:
        d = MessageDedup(ttl_secs=1.0)
        now = time.monotonic()
        # Manually inject an expired entry
        d._seen["msg-old"] = now - 2.0
        assert d.is_duplicate("msg-old") is False  # expired → treated as new

    def test_fresh_entry_is_duplicate(self) -> None:
        d = MessageDedup(ttl_secs=60.0)
        now = time.monotonic()
        d._seen["msg-fresh"] = now - 0.5  # recent
        assert d.is_duplicate("msg-fresh") is True

    def test_empty_string_not_tracked(self) -> None:
        d = MessageDedup()
        d.is_duplicate("")
        assert "" not in d._seen

    def test_many_unique_ids(self) -> None:
        d = MessageDedup()
        for i in range(100):
            assert d.is_duplicate(str(i)) is False

    def test_repeat_after_first_is_duplicate(self) -> None:
        d = MessageDedup(ttl_secs=60.0)
        d.is_duplicate("x")
        for _ in range(5):
            assert d.is_duplicate("x") is True


class TestCleanExpired:
    def test_removes_old_entries(self) -> None:
        d = MessageDedup(ttl_secs=1.0)
        now = time.monotonic()
        d._seen["old"] = now - 5.0
        d._seen["fresh"] = now
        d._clean_expired()
        assert "old" not in d._seen
        assert "fresh" in d._seen

    def test_empty_seen_no_error(self) -> None:
        d = MessageDedup()
        d._clean_expired()  # should not raise

    def test_boundary_exactly_at_ttl(self) -> None:
        d = MessageDedup(ttl_secs=1.0)
        now = time.monotonic()
        # Exactly at TTL boundary — >= condition makes this expire
        d._seen["boundary"] = now - 1.0
        d._clean_expired()
        assert "boundary" not in d._seen

    def test_clean_triggered_by_is_duplicate(self) -> None:
        d = MessageDedup(ttl_secs=1.0)
        now = time.monotonic()
        d._seen["stale"] = now - 5.0
        # Trigger cleanup via is_duplicate
        d.is_duplicate("trigger")
        assert "stale" not in d._seen
        assert "trigger" in d._seen
