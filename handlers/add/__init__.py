from aiogram import Router

from handlers.add.card import router as card_router
from handlers.add.passport import router as passport_router
from handlers.add.receipt import router as receipt_router

router = Router()
router.include_router(passport_router)
router.include_router(receipt_router)
router.include_router(card_router)
