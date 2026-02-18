"""Tests for workers/tasks/topic_cleanup.py — delete topics 24h after course ends.

Key logic tested:
- No users with topic → early return (get_ended_user_ids NOT called)
- Users with topic but course still active → no deletion
- Happy path: ended course 24h+ ago → delete_forum_topic + clear_topic_id
- delete_forum_topic fails → clear_topic_id STILL called (self-healing)
- Multiple users: only eligible ones cleaned up
- Correct cutoff (now - 24h) passed to get_ended_user_ids
- Correct chat_id (settings.kok_group_id) passed to delete_forum_topic
"""
from datetime import timedelta
from unittest.mock import AsyncMock, call, patch

from workers.tasks.topic_cleanup import CLEANUP_AFTER_HOURS, run

from .conftest import JUN_15, KOK_GROUP_ID, make_settings, make_user

_PATCH = "workers.tasks.topic_cleanup"


class TestRun:

    # ── Early return ──────────────────────────────────────────────────

    async def test_no_users_with_topic_does_nothing(self):
        """get_with_topic() returns [] → early return, no DB queries."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        user_repo.get_with_topic = AsyncMock(return_value=[])

        with patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15):
            await run(bot, make_settings(), course_repo, user_repo)

        course_repo.get_ended_user_ids.assert_not_called()
        bot.delete_forum_topic.assert_not_called()
        user_repo.clear_topic_id.assert_not_called()

    # ── No eligible users ─────────────────────────────────────────────

    async def test_course_still_active_no_deletion(self):
        """User has topic but course not ended → no deletion."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        user = make_user(user_id=100, topic_id=999)
        user_repo.get_with_topic = AsyncMock(return_value=[user])
        course_repo.get_ended_user_ids = AsyncMock(return_value=set())

        with patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15):
            await run(bot, make_settings(), course_repo, user_repo)

        bot.delete_forum_topic.assert_not_called()
        user_repo.clear_topic_id.assert_not_called()

    async def test_course_ended_less_than_24h_no_deletion(self):
        """Ended < 24h ago → get_ended_user_ids returns empty (cutoff filters)."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        user = make_user(user_id=100, topic_id=999)
        user_repo.get_with_topic = AsyncMock(return_value=[user])
        course_repo.get_ended_user_ids = AsyncMock(return_value=set())

        with patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15):
            await run(bot, make_settings(), course_repo, user_repo)

        bot.delete_forum_topic.assert_not_called()
        user_repo.clear_topic_id.assert_not_called()

    # ── Happy path ────────────────────────────────────────────────────

    async def test_happy_path_deletes_topic_and_clears_id(self):
        """Ended 24h+ ago → delete_forum_topic + clear_topic_id."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        user = make_user(user_id=100, topic_id=999)
        user_repo.get_with_topic = AsyncMock(return_value=[user])
        course_repo.get_ended_user_ids = AsyncMock(return_value={100})

        with patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15):
            await run(bot, make_settings(), course_repo, user_repo)

        bot.delete_forum_topic.assert_called_once_with(
            chat_id=KOK_GROUP_ID,
            message_thread_id=999,
        )
        user_repo.clear_topic_id.assert_called_once_with(100)

    async def test_correct_cutoff_passed(self):
        """get_ended_user_ids receives now - 24h as cutoff."""
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        user = make_user(user_id=100, topic_id=999)
        user_repo.get_with_topic = AsyncMock(return_value=[user])
        course_repo.get_ended_user_ids = AsyncMock(return_value=set())

        with patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15):
            await run(AsyncMock(), make_settings(), course_repo, user_repo)

        expected_cutoff = JUN_15 - timedelta(hours=CLEANUP_AFTER_HOURS)
        course_repo.get_ended_user_ids.assert_called_once_with(
            [100], expected_cutoff,
        )
        assert CLEANUP_AFTER_HOURS == 24

    async def test_correct_chat_id_from_settings(self):
        """delete_forum_topic uses settings.kok_group_id."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        user = make_user(user_id=100, topic_id=555)
        user_repo.get_with_topic = AsyncMock(return_value=[user])
        course_repo.get_ended_user_ids = AsyncMock(return_value={100})

        with patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15):
            await run(bot, make_settings(), course_repo, user_repo)

        assert bot.delete_forum_topic.call_args.kwargs["chat_id"] == KOK_GROUP_ID

    # ── Error handling ────────────────────────────────────────────────

    async def test_delete_topic_fails_still_clears_id(self):
        """delete_forum_topic raises → clear_topic_id STILL called."""
        bot = AsyncMock()
        bot.delete_forum_topic = AsyncMock(side_effect=RuntimeError("API error"))
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        user = make_user(user_id=100, topic_id=999)
        user_repo.get_with_topic = AsyncMock(return_value=[user])
        course_repo.get_ended_user_ids = AsyncMock(return_value={100})

        with patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15):
            await run(bot, make_settings(), course_repo, user_repo)

        bot.delete_forum_topic.assert_called_once()
        user_repo.clear_topic_id.assert_called_once_with(100)

    # ── Multiple users ────────────────────────────────────────────────

    async def test_multiple_users_only_eligible_cleaned(self):
        """3 users with topics, 2 ended → only 2 deleted."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        user1 = make_user(user_id=100, topic_id=111)
        user2 = make_user(user_id=200, topic_id=222)
        user3 = make_user(user_id=300, topic_id=333)
        user_repo.get_with_topic = AsyncMock(return_value=[user1, user2, user3])
        course_repo.get_ended_user_ids = AsyncMock(return_value={100, 300})

        with patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15):
            await run(bot, make_settings(), course_repo, user_repo)

        assert bot.delete_forum_topic.call_count == 2
        assert user_repo.clear_topic_id.call_count == 2

        delete_calls = bot.delete_forum_topic.call_args_list
        assert delete_calls[0] == call(chat_id=KOK_GROUP_ID, message_thread_id=111)
        assert delete_calls[1] == call(chat_id=KOK_GROUP_ID, message_thread_id=333)

        clear_calls = user_repo.clear_topic_id.call_args_list
        assert clear_calls[0] == call(100)
        assert clear_calls[1] == call(300)

    async def test_one_delete_fails_others_continue(self):
        """First delete fails, second succeeds → both clear_topic_id called."""
        bot = AsyncMock()
        bot.delete_forum_topic = AsyncMock(
            side_effect=[RuntimeError("fail"), None],
        )
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        user1 = make_user(user_id=100, topic_id=111)
        user2 = make_user(user_id=200, topic_id=222)
        user_repo.get_with_topic = AsyncMock(return_value=[user1, user2])
        course_repo.get_ended_user_ids = AsyncMock(return_value={100, 200})

        with patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15):
            await run(bot, make_settings(), course_repo, user_repo)

        assert bot.delete_forum_topic.call_count == 2
        assert user_repo.clear_topic_id.call_count == 2

    async def test_user_ids_passed_to_get_ended(self):
        """All user IDs from get_with_topic passed to get_ended_user_ids."""
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        users = [
            make_user(user_id=10, topic_id=1),
            make_user(user_id=20, topic_id=2),
            make_user(user_id=30, topic_id=3),
        ]
        user_repo.get_with_topic = AsyncMock(return_value=users)
        course_repo.get_ended_user_ids = AsyncMock(return_value=set())

        with patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15):
            await run(AsyncMock(), make_settings(), course_repo, user_repo)

        passed_ids = course_repo.get_ended_user_ids.call_args.args[0]
        assert passed_ids == [10, 20, 30]
