"""
Build Update objects for simulating user actions.

Creates aiogram Update objects that can be fed to the dispatcher.
"""
from datetime import datetime
from typing import Any

from aiogram.types import (
    CallbackQuery,
    Chat,
    Contact,
    Document,
    Message,
    PhotoSize,
    Update,
    User,
    Video,
    VideoNote,
)


class UpdateBuilder:
    """Builds Update objects for testing."""

    def __init__(
        self,
        user_id: int = 123456789,
        chat_id: int | None = None,
        chat_type: str = "private",
        message_thread_id: int | None = None,
    ) -> None:
        self.user_id = user_id
        self.chat_id = chat_id if chat_id is not None else user_id
        self.chat_type = chat_type
        self.message_thread_id = message_thread_id
        self._update_id_counter = 0
        self._message_id_counter = 0

    def _get_next_update_id(self) -> int:
        """Generate next update ID."""
        self._update_id_counter += 1
        return self._update_id_counter

    def _get_next_message_id(self) -> int:
        """Generate next message ID."""
        self._message_id_counter += 1
        return self._message_id_counter

    def _make_user(self) -> User:
        """Create test user."""
        return User(
            id=self.user_id,
            is_bot=False,
            first_name="Test",
            last_name="User",
            username="testuser",
            language_code="ru",
        )

    def _make_chat(self) -> Chat:
        """Create test chat."""
        if self.chat_type == "supergroup":
            return Chat(
                id=self.chat_id,
                type="supergroup",
                title="Test Group",
                username="test_group",
            )
        return Chat(
            id=self.chat_id,
            type="private",
            first_name="Test",
            last_name="User",
            username="testuser",
        )

    def _make_bot_user(self) -> User:
        """Create bot user for callback query messages."""
        return User(
            id=1234567890,
            is_bot=True,
            first_name="TestBot",
            username="test_bot",
        )

    def make_message_update(self, text: str) -> Update:
        """Create Update with text message."""
        message = Message(
            message_id=self._get_next_message_id(),
            date=datetime.now(),
            chat=self._make_chat(),
            from_user=self._make_user(),
            text=text,
            message_thread_id=self.message_thread_id,
        )
        return Update(
            update_id=self._get_next_update_id(),
            message=message,
        )

    def make_contact_update(
        self,
        phone_number: str,
        first_name: str,
        last_name: str | None = None,
    ) -> Update:
        """Create Update with contact message."""
        contact = Contact(
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            user_id=self.user_id,
        )
        message = Message(
            message_id=self._get_next_message_id(),
            date=datetime.now(),
            chat=self._make_chat(),
            from_user=self._make_user(),
            contact=contact,
        )
        return Update(
            update_id=self._get_next_update_id(),
            message=message,
        )

    def make_callback_update(
        self,
        callback_data: str,
        message_id: int | None = None,
        message_text: str = "Message with buttons",
        reply_markup: dict[str, Any] | None = None,
    ) -> Update:
        """Create Update with callback query (button click)."""
        message = Message(
            message_id=message_id if message_id is not None else self._get_next_message_id(),
            date=datetime.now(),
            chat=self._make_chat(),
            from_user=self._make_bot_user(),
            text=message_text,
            message_thread_id=self.message_thread_id,
        )

        callback = CallbackQuery(
            id=f"callback_{self._get_next_update_id()}",
            from_user=self._make_user(),
            chat_instance=str(self.chat_id),
            data=callback_data,
            message=message,
        )

        return Update(
            update_id=self._get_next_update_id(),
            callback_query=callback,
        )

    def make_photo_update(
        self,
        file_id: str = "test_photo_id",
        caption: str | None = None,
    ) -> Update:
        """Create Update with photo message."""
        photo_sizes = [
            PhotoSize(
                file_id=f"{file_id}_small",
                file_unique_id=f"unique_{file_id}_small",
                width=90,
                height=90,
            ),
            PhotoSize(
                file_id=file_id,
                file_unique_id=f"unique_{file_id}",
                width=800,
                height=600,
            ),
        ]

        message = Message(
            message_id=self._get_next_message_id(),
            date=datetime.now(),
            chat=self._make_chat(),
            from_user=self._make_user(),
            photo=photo_sizes,
            caption=caption,
            message_thread_id=self.message_thread_id,
        )

        return Update(
            update_id=self._get_next_update_id(),
            message=message,
        )

    def make_video_update(
        self,
        file_id: str = "test_video_id",
        caption: str | None = None,
        duration: int = 30,
    ) -> Update:
        """Create Update with video message."""
        video = Video(
            file_id=file_id,
            file_unique_id=f"unique_{file_id}",
            width=1920,
            height=1080,
            duration=duration,
        )

        message = Message(
            message_id=self._get_next_message_id(),
            date=datetime.now(),
            chat=self._make_chat(),
            from_user=self._make_user(),
            video=video,
            caption=caption,
            message_thread_id=self.message_thread_id,
        )

        return Update(
            update_id=self._get_next_update_id(),
            message=message,
        )

    def make_video_note_update(
        self,
        file_id: str = "test_video_note_id",
        duration: int = 15,
        length: int = 240,
    ) -> Update:
        """Create Update with video note message (round video)."""
        video_note = VideoNote(
            file_id=file_id,
            file_unique_id=f"unique_{file_id}",
            length=length,
            duration=duration,
        )

        message = Message(
            message_id=self._get_next_message_id(),
            date=datetime.now(),
            chat=self._make_chat(),
            from_user=self._make_user(),
            video_note=video_note,
            message_thread_id=self.message_thread_id,
        )

        return Update(
            update_id=self._get_next_update_id(),
            message=message,
        )

    def make_document_update(
        self,
        file_id: str = "test_document_id",
        file_name: str | None = "document.pdf",
        mime_type: str = "application/pdf",
        caption: str | None = None,
    ) -> Update:
        """Create Update with document message."""
        document = Document(
            file_id=file_id,
            file_unique_id=f"unique_{file_id}",
            file_name=file_name,
            mime_type=mime_type,
        )

        message = Message(
            message_id=self._get_next_message_id(),
            date=datetime.now(),
            chat=self._make_chat(),
            from_user=self._make_user(),
            document=document,
            caption=caption,
            message_thread_id=self.message_thread_id,
        )

        return Update(
            update_id=self._get_next_update_id(),
            message=message,
        )

    def get_last_message_id(self) -> int:
        """Get the last assigned message ID."""
        return self._message_id_counter

    def reset(self) -> None:
        """Reset counters."""
        self._update_id_counter = 0
        self._message_id_counter = 0
