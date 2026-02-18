from dishka import AsyncContainer
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from whatsapp.routes.health import router as health_router
from whatsapp.routes.webhook import router as webhook_router


def create_app(container: AsyncContainer) -> FastAPI:
    app = FastAPI(title="Koki WhatsApp API")

    app.include_router(health_router)
    app.include_router(webhook_router)

    setup_dishka(container=container, app=app)

    return app
