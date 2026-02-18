"""Tests for workers/dedup.py — Redis-based deduplication.

Key logic tested:
- was_sent: returns False when key absent, True when present
- mark_sent: sets key with REDIS_TTL=86400 via setex
- Key format: "sent:{course_id}:{date}:{reminder_type}"
- Isolation: different day/type/course → different keys
"""
from datetime import datetime
from unittest.mock import AsyncMock, patch

from utils.time import TASHKENT_TZ
from workers.dedup import REDIS_TTL, mark_sent, was_sent

_PATCH_NOW = "workers.dedup.get_tashkent_now"
_JUN_15 = datetime(2025, 6, 15, 14, 0, tzinfo=TASHKENT_TZ)
_JUN_14 = datetime(2025, 6, 14, 14, 0, tzinfo=TASHKENT_TZ)


# =============================================================================
# WAS_SENT
# =============================================================================


class TestWasSent:
    async def test_not_sent_returns_false(self, mock_redis: AsyncMock):
        """Key does not exist → was_sent returns False."""
        mock_redis.exists = AsyncMock(return_value=0)

        with patch(_PATCH_NOW, return_value=_JUN_15):
            result = await was_sent(mock_redis, course_id=42, reminder_type="reminder_10min")

        assert result is False

    async def test_already_sent_returns_true(self, mock_redis: AsyncMock):
        """Key exists → was_sent returns True."""
        mock_redis.exists = AsyncMock(return_value=1)

        with patch(_PATCH_NOW, return_value=_JUN_15):
            result = await was_sent(mock_redis, course_id=42, reminder_type="reminder_10min")

        assert result is True

    async def test_key_format(self, mock_redis: AsyncMock):
        """Key must be exactly 'sent:{course_id}:{date}:{reminder_type}'."""
        mock_redis.exists = AsyncMock(return_value=0)

        with patch(_PATCH_NOW, return_value=_JUN_15):
            await was_sent(mock_redis, course_id=42, reminder_type="reminder_10min")

        mock_redis.exists.assert_called_once_with("sent:42:2025-06-15:reminder_10min")


# =============================================================================
# MARK_SENT
# =============================================================================


class TestMarkSent:
    async def test_sets_key_with_24h_ttl(self, mock_redis: AsyncMock):
        """mark_sent calls setex with TTL=86400 and value '1'."""
        with patch(_PATCH_NOW, return_value=_JUN_15):
            await mark_sent(mock_redis, course_id=42, reminder_type="reminder_10min")

        mock_redis.setex.assert_called_once_with(
            "sent:42:2025-06-15:reminder_10min", REDIS_TTL, "1",
        )
        assert REDIS_TTL == 86400

    async def test_key_format_matches_was_sent(self, mock_redis: AsyncMock):
        """mark_sent and was_sent produce the same key for same args."""
        mock_redis.exists = AsyncMock(return_value=0)

        with patch(_PATCH_NOW, return_value=_JUN_15):
            await was_sent(mock_redis, course_id=99, reminder_type="strike_30min")
            was_sent_key = mock_redis.exists.call_args[0][0]

            await mark_sent(mock_redis, course_id=99, reminder_type="strike_30min")
            mark_sent_key = mock_redis.setex.call_args[0][0]

        assert was_sent_key == mark_sent_key
        assert was_sent_key == "sent:99:2025-06-15:strike_30min"


# =============================================================================
# ISOLATION — different inputs → different keys
# =============================================================================


class TestIsolation:
    async def test_different_day_different_key(self, mock_redis: AsyncMock):
        """Different Tashkent dates produce different keys."""
        mock_redis.exists = AsyncMock(return_value=0)

        with patch(_PATCH_NOW, return_value=_JUN_14):
            await was_sent(mock_redis, course_id=42, reminder_type="reminder_10min")
        key_day_14 = mock_redis.exists.call_args[0][0]

        mock_redis.exists.reset_mock()

        with patch(_PATCH_NOW, return_value=_JUN_15):
            await was_sent(mock_redis, course_id=42, reminder_type="reminder_10min")
        key_day_15 = mock_redis.exists.call_args[0][0]

        assert key_day_14 != key_day_15
        assert "2025-06-14" in key_day_14
        assert "2025-06-15" in key_day_15

    async def test_different_types_different_key(self, mock_redis: AsyncMock):
        """Same course, different reminder types → different keys."""
        mock_redis.exists = AsyncMock(return_value=0)

        with patch(_PATCH_NOW, return_value=_JUN_15):
            await was_sent(mock_redis, course_id=42, reminder_type="reminder_10min")
            key_10min = mock_redis.exists.call_args[0][0]

            mock_redis.exists.reset_mock()

            await was_sent(mock_redis, course_id=42, reminder_type="strike_30min")
            key_30min = mock_redis.exists.call_args[0][0]

        assert key_10min != key_30min
        assert key_10min == "sent:42:2025-06-15:reminder_10min"
        assert key_30min == "sent:42:2025-06-15:strike_30min"

    async def test_different_courses_different_key(self, mock_redis: AsyncMock):
        """Different course IDs → different keys."""
        mock_redis.exists = AsyncMock(return_value=0)

        with patch(_PATCH_NOW, return_value=_JUN_15):
            await was_sent(mock_redis, course_id=42, reminder_type="reminder_10min")
            key_42 = mock_redis.exists.call_args[0][0]

            mock_redis.exists.reset_mock()

            await was_sent(mock_redis, course_id=99, reminder_type="reminder_10min")
            key_99 = mock_redis.exists.call_args[0][0]

        assert key_42 != key_99
        assert key_42 == "sent:42:2025-06-15:reminder_10min"
        assert key_99 == "sent:99:2025-06-15:reminder_10min"