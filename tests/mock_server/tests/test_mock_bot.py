"""
Tests for MockBot — lightweight bot wrapper for service tests.
"""
import pytest

from tests.mock_server import MockBot


class TestMockBotBasics:
    """Test MockBot lifecycle and basic operations."""

    @pytest.mark.asyncio
    async def test_mock_bot_starts_and_stops(self) -> None:
        """MockBot context manager works correctly."""
        async with MockBot() as mock:
            assert mock.bot is not None

    @pytest.mark.asyncio
    async def test_mock_bot_send_message(self) -> None:
        """MockBot can send messages through the bot."""
        async with MockBot() as mock:
            result = await mock.bot.send_message(chat_id=123, text="Hello")
            assert result.text == "Hello"
            assert result.message_id > 0

    @pytest.mark.asyncio
    async def test_mock_bot_tracks_requests(self) -> None:
        """MockBot tracks all sent messages."""
        async with MockBot() as mock:
            await mock.bot.send_message(chat_id=123, text="First")
            await mock.bot.send_message(chat_id=456, text="Second")

            messages = mock.get_sent_messages()
            assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_mock_bot_delete_message(self) -> None:
        """MockBot tracks deleted messages."""
        async with MockBot() as mock:
            msg = await mock.bot.send_message(chat_id=123, text="Delete me")
            await mock.bot.delete_message(chat_id=123, message_id=msg.message_id)

            deleted = mock.get_deleted_messages()
            assert len(deleted) == 1

    @pytest.mark.asyncio
    async def test_mock_bot_edit_message_text(self) -> None:
        """MockBot tracks edited messages."""
        async with MockBot() as mock:
            msg = await mock.bot.send_message(chat_id=123, text="Original")
            await mock.bot.edit_message_text(
                chat_id=123, message_id=msg.message_id, text="Edited",
            )

            edits = mock.get_edit_message_text_requests()
            assert len(edits) == 1
            assert edits[0].data.get("text") == "Edited"

    @pytest.mark.asyncio
    async def test_mock_bot_clear(self) -> None:
        """MockBot clear resets all state."""
        async with MockBot() as mock:
            await mock.bot.send_message(chat_id=123, text="Message")
            mock.clear()

            assert len(mock.get_sent_messages()) == 0

    @pytest.mark.asyncio
    async def test_mock_bot_chat_state_stores_messages(self) -> None:
        """MockBot chat_state stores messages for inspection."""
        async with MockBot() as mock:
            await mock.bot.send_message(chat_id=123, text="Stored")

            messages = mock.chat_state.get_conversation(123)
            assert len(messages) == 1
            assert messages[0].text == "Stored"


class TestMockBotMedia:
    """Test MockBot media operations."""

    @pytest.mark.asyncio
    async def test_send_video(self) -> None:
        """MockBot can send video."""
        async with MockBot() as mock:
            from aiogram.types import FSInputFile

            # Use bot.send_video with a file_id string (most common in handlers)
            result = await mock.bot.send_video(
                chat_id=123, video="some_video_file_id",
            )
            assert result.message_id > 0
            assert result.video is not None

    @pytest.mark.asyncio
    async def test_send_video_note(self) -> None:
        """MockBot can send video note (round video)."""
        async with MockBot() as mock:
            result = await mock.bot.send_video_note(
                chat_id=123, video_note="some_video_note_id",
            )
            assert result.message_id > 0
            assert result.video_note is not None

    @pytest.mark.asyncio
    async def test_send_photo(self) -> None:
        """MockBot can send photo."""
        async with MockBot() as mock:
            result = await mock.bot.send_photo(
                chat_id=123, photo="some_photo_id",
            )
            assert result.message_id > 0
            assert result.photo is not None

    @pytest.mark.asyncio
    async def test_send_document(self) -> None:
        """MockBot can send document."""
        async with MockBot() as mock:
            result = await mock.bot.send_document(
                chat_id=123, document="some_doc_id",
            )
            assert result.message_id > 0
            assert result.document is not None

    @pytest.mark.asyncio
    async def test_send_message_with_thread_id(self) -> None:
        """MockBot can send message to forum topic."""
        async with MockBot() as mock:
            result = await mock.bot.send_message(
                chat_id=-1001234567890,
                text="In topic",
                message_thread_id=42,
            )
            assert result.message_id > 0
            assert result.message_thread_id == 42


class TestMockBotFileDownload:
    """Test file download functionality."""

    @pytest.mark.asyncio
    async def test_get_file(self) -> None:
        """MockBot handles getFile API call."""
        async with MockBot() as mock:
            file = await mock.bot.get_file("test_file_id")
            assert file.file_id == "test_file_id"
            assert file.file_path is not None

    @pytest.mark.asyncio
    async def test_download_file(self) -> None:
        """MockBot can download files (returns fake bytes)."""
        async with MockBot() as mock:
            file = await mock.bot.get_file("test_file_id")
            from io import BytesIO

            dest = BytesIO()
            await mock.bot.download_file(file.file_path, dest)
            content = dest.getvalue()
            assert len(content) > 0
