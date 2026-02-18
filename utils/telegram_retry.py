"""Retry wrapper for Telegram Bot API calls.

Retries on transient errors (rate limit, network, timeout).
Does NOT retry on permanent errors (user blocked bot, bad request).
"""
import asyncio
import logging
from typing import Any, Callable, Coroutine

from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter

logger = logging.getLogger(__name__)

TRANSIENT_RETRIES = 2
BASE_DELAY_SECONDS = 1.0


async def tg_retry(
    method: Callable[..., Coroutine],
    *args: Any,
    _retries: int = TRANSIENT_RETRIES,
    **kwargs: Any,
) -> Any:
    """Call a Telegram Bot API method with retry on transient errors.

    Usage:
        await tg_retry(bot.send_message, chat_id=123, text="Hello")

    Retries on:
    - TelegramRetryAfter (HTTP 429 — rate limited)
    - TelegramNetworkError (connection issues)
    - asyncio.TimeoutError

    Does NOT retry on (raises immediately):
    - TelegramForbiddenError (user blocked bot)
    - TelegramBadRequest (invalid request)
    - Any other exception
    """
    last_exc: Exception | None = None
    for attempt in range(_retries + 1):
        try:
            return await method(*args, **kwargs)
        except TelegramRetryAfter as e:
            last_exc = e
            if attempt < _retries:
                delay = e.retry_after + 0.5
                logger.warning(
                    "Rate limited, retry in %.1fs (%d/%d)",
                    delay, attempt + 1, _retries,
                )
                await asyncio.sleep(delay)
                continue
            raise
        except TelegramNetworkError as e:
            last_exc = e
            if attempt < _retries:
                delay = BASE_DELAY_SECONDS * (2 ** attempt)
                logger.warning(
                    "Network error: %s, retry in %.1fs (%d/%d)",
                    e, delay, attempt + 1, _retries,
                )
                await asyncio.sleep(delay)
                continue
            raise
        except TimeoutError as e:
            last_exc = e
            if attempt < _retries:
                delay = BASE_DELAY_SECONDS * (2 ** attempt)
                logger.warning(
                    "Timeout, retry in %.1fs (%d/%d)",
                    delay, attempt + 1, _retries,
                )
                await asyncio.sleep(delay)
                continue
            raise
    raise last_exc  # type: ignore[misc]
