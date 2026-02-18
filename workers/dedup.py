from redis.asyncio import Redis

from utils.time import get_tashkent_now

REDIS_TTL = 86400  # 24 hours


async def was_sent(redis: Redis, course_id: int, reminder_type: str) -> bool:
    """Check if reminder was already sent today for this course."""
    today = get_tashkent_now().date().isoformat()
    key = f"sent:{course_id}:{today}:{reminder_type}"
    return bool(await redis.exists(key))


async def mark_sent(redis: Redis, course_id: int, reminder_type: str) -> None:
    """Mark reminder as sent today."""
    today = get_tashkent_now().date().isoformat()
    key = f"sent:{course_id}:{today}:{reminder_type}"
    await redis.setex(key, REDIS_TTL, "1")
