from aiogram import Router

from handlers.appeal import router as appeal_router
from handlers.card import router as card_router
from handlers.video.receive import router as receive_router
from handlers.video.review import router as review_router

router = Router()
router.include_router(appeal_router)  # Must be before receive (FSM state priority)
router.include_router(card_router)
router.include_router(receive_router)
router.include_router(review_router)
