"""
Telegram Error Handler - sends ERROR+ logs to a Telegram topic.
"""
import logging
import traceback
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError


class TelegramErrorHandler(logging.Handler):
    """
    Logging handler that sends ERROR and CRITICAL logs to a Telegram topic.

    Features:
    - Sends to a specific topic (thread) in a group
    - Includes stack trace
    - Includes timestamp
    - Dedup (skips same error twice in a row)
    - Filters out non-actionable network errors
    """

    IGNORED_PATTERNS = (
        "ServerDisconnectedError",
        "Connection reset by peer",
    )

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        topic_id: int,
        min_level: int = logging.ERROR,
    ):
        super().__init__(level=min_level)
        self.bot = bot
        self.chat_id = chat_id
        self.topic_id = topic_id
        self._last_error: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if any(pattern in msg for pattern in self.IGNORED_PATTERNS):
            return

        try:
            import asyncio
            asyncio.create_task(self._async_emit(record))
        except RuntimeError:
            import sys
            print(
                f"[TelegramErrorHandler] {record.levelname}: {record.getMessage()}",
                file=sys.stderr,
            )

    async def _async_emit(self, record: logging.LogRecord) -> None:
        try:
            message = self._format_message(record)

            if message == self._last_error:
                return
            self._last_error = message

            await self.bot.send_message(
                chat_id=self.chat_id,
                message_thread_id=self.topic_id,
                text=message,
                parse_mode="HTML",
            )
        except TelegramAPIError as e:
            print(f"Failed to send error to Telegram: {e}")

    def _format_message(self, record: logging.LogRecord) -> str:
        emoji = "🔴" if record.levelno >= logging.ERROR else "🟡"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        location = f"{record.filename}:{record.lineno}"

        parts = [
            f"{emoji} <b>{record.levelname}</b>",
            f"📍 <code>{location}</code>",
            f"🕐 {timestamp}",
            "",
            f"<b>Message:</b>",
            f"<code>{self._escape_html(record.getMessage())}</code>",
        ]

        if record.exc_info:
            tb = "".join(traceback.format_exception(*record.exc_info))
            if len(tb) > 2000:
                tb = tb[:1000] + "\n...\n" + tb[-1000:]
            parts.extend([
                "",
                f"<b>Traceback:</b>",
                f"<pre>{self._escape_html(tb)}</pre>",
            ])

        message = "\n".join(parts)

        if len(message) > 4000:
            message = message[:3950] + "\n\n... (truncated)"

        return message

    @staticmethod
    def _escape_html(text: str) -> str:
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )


def setup_telegram_error_handler(
    bot: Bot,
    chat_id: int,
    topic_id: int,
    logger_name: str | None = None,
) -> TelegramErrorHandler:
    handler = TelegramErrorHandler(
        bot=bot,
        chat_id=chat_id,
        topic_id=topic_id,
    )

    target_logger = logging.getLogger(logger_name)
    target_logger.addHandler(handler)

    return handler
