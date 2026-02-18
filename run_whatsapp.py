import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / (".env.test" if os.getenv("ENV") == "test" else ".env"))

import uvicorn
from dishka import make_async_container
from rich.logging import RichHandler

from config import Settings, get_settings
from di.provider import AppProvider
from whatsapp.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    settings: Settings = get_settings()

    if not settings.whatsapp_phone_number_id or not settings.whatsapp_access_token:
        logger.error("WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN are required")
        return

    container = make_async_container(AppProvider(settings))
    app = create_app(container)

    logger.info("Starting WhatsApp API server on port 8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
