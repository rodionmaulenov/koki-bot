from aiogram import Router

from handlers.appeal.review import router as review_router
from handlers.appeal.submit import router as submit_router

router = Router()
router.include_router(submit_router)
router.include_router(review_router)
