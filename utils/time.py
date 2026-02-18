from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")


def get_tashkent_now() -> datetime:
    return datetime.now(tz=TASHKENT_TZ)


def calculate_time_range_before(
    minutes_before: int, interval_minutes: int = 5,
) -> tuple[time, time]:
    """Calculate intake_time range for 'X minutes before intake'.

    If now is 12:35 and minutes_before=60, we want courses where
    intake_time is between 13:30 and 13:40 (now+55..now+65 minutes).
    Interval covers the scheduler tick (±interval/2).

    NOTE: If range straddles midnight (range_start > range_end as time()),
    the DB query `intake_time >= start AND intake_time <= end` returns
    empty. This affects a ~4-minute window around midnight — extremely
    unlikely in practice since girls don't set intake_time to 00:00.
    """
    now = get_tashkent_now()
    center = now + timedelta(minutes=minutes_before)
    half = interval_minutes // 2
    range_start = center - timedelta(minutes=half)
    range_end = center + timedelta(minutes=half)
    return range_start.time(), range_end.time()


def calculate_time_range_after(
    minutes_after: int, interval_minutes: int = 5,
) -> tuple[time, time]:
    """Calculate intake_time range for 'X minutes after intake'.

    If now is 14:35 and minutes_after=30, we want courses where
    intake_time is between 14:00 and 14:10 (now-35..now-25 minutes).
    """
    now = get_tashkent_now()
    center = now - timedelta(minutes=minutes_after)
    half = interval_minutes // 2
    range_start = center - timedelta(minutes=half)
    range_end = center + timedelta(minutes=half)
    return range_start.time(), range_end.time()
