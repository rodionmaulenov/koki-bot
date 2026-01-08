"""Расписание периодических задач."""

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from app.workers.broker import broker
import app.workers.tasks  # noqa: E402, F401

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)