"""
Telegram API method handlers.

Each module handles a group of related API methods.
"""
from tests.mock_server.methods.callbacks import handle_answer_callback_query
from tests.mock_server.methods.forum import (
    handle_close_forum_topic,
    handle_create_forum_topic,
    handle_edit_forum_topic,
    handle_get_file,
    handle_pin_chat_message,
    handle_reopen_forum_topic,
)
from tests.mock_server.methods.media import (
    handle_edit_message_caption,
    handle_edit_message_media,
    handle_send_document,
    handle_send_photo,
    handle_send_video,
    handle_send_video_note,
)
from tests.mock_server.methods.messages import (
    handle_delete_message,
    handle_delete_messages,
    handle_edit_message_reply_markup,
    handle_edit_message_text,
    handle_send_message,
)

__all__ = [
    # Messages
    "handle_send_message",
    "handle_delete_message",
    "handle_delete_messages",
    "handle_edit_message_text",
    "handle_edit_message_reply_markup",
    # Callbacks
    "handle_answer_callback_query",
    # Media
    "handle_send_photo",
    "handle_send_video",
    "handle_send_video_note",
    "handle_send_document",
    "handle_edit_message_caption",
    "handle_edit_message_media",
    # Forum topics
    "handle_create_forum_topic",
    "handle_edit_forum_topic",
    "handle_close_forum_topic",
    "handle_reopen_forum_topic",
    "handle_pin_chat_message",
    "handle_get_file",
]
