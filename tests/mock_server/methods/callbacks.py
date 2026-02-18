"""
Callback query related API method handlers.

Handles: answerCallbackQuery
"""
import logging
from typing import Any

from tests.mock_server.responses import make_error_response, make_true_response

logger = logging.getLogger("mock_server.methods.callbacks")


def handle_answer_callback_query(data: dict[str, Any]) -> dict[str, Any]:
    """Handle answerCallbackQuery API call."""
    callback_query_id = data.get("callback_query_id")

    if callback_query_id is None:
        return make_error_response("Bad Request: callback_query_id is required")

    logger.debug(
        "answerCallbackQuery: id=%s, text=%s",
        callback_query_id,
        data.get("text"),
    )

    return make_true_response()
