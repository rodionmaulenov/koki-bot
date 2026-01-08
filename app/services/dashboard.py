"""Сервис для генерации дашбордов."""

from datetime import timedelta
from app.utils.time_utils import get_tashkent_now, MONTHS


class DashboardService:
    """Генерирует дашборды для группы менеджеров."""

    def __init__(self, supabase, group_chat_id: int):
        self.supabase = supabase
        self.group_chat_id = group_chat_id

    @staticmethod
    def _format_date(date_str: str) -> str:
        """Форматирует дату: 2026-01-06 → 6 Янв"""
        from datetime import datetime
        try:
            date = datetime.fromisoformat(date_str).date()
            month = MONTHS[date.month]
            return f"{date.day} {month}"
        except (ValueError, TypeError):
            return date_str

    def _make_topic_link(self, topic_id: int | None, name: str) -> str:
        """Создаёт кликабельную ссылку на топик."""
        if not topic_id:
            return name

        # Убираем -100 из chat_id для ссылки
        chat_id = str(self.group_chat_id)
        if chat_id.startswith("-100"):
            chat_id = chat_id[4:]

        return f'<a href="https://t.me/c/{chat_id}/{topic_id}">{name}</a>'

    async def generate_active_courses(self) -> str:
        """Генерирует дашборд активных курсов."""
        from datetime import datetime, timezone

        now = get_tashkent_now()
        today = now.date().isoformat()
        date_display = self._format_date(today)

        # Получаем активные курсы с user и manager
        result = await self.supabase.table("courses") \
            .select("*, users(*, managers(*))") \
            .eq("status", "active") \
            .execute()

        courses = result.data or []

        if not courses:
            return f"📊 Активные курсы — {date_display}\n\n👥 Всего: 0"

        # Получаем intake_logs за сегодня (UTC)
        utc_now = datetime.now(timezone.utc)
        utc_today = utc_now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

        today_logs = await self.supabase.table("intake_logs") \
            .select("course_id, status") \
            .gte("created_at", utc_today) \
            .in_("status", ["taken", "late", "pending_review"]) \
            .execute()

        sent_today = set()
        pending_course_ids = set()

        for log in (today_logs.data or []):
            if log["status"] == "pending_review":
                pending_course_ids.add(log["course_id"])
            else:
                sent_today.add(log["course_id"])

        # Группируем по менеджерам
        by_manager: dict[str, list] = {}
        pending_reviews: list = []

        for course in courses:
            user = course.get("users") or {}
            manager = user.get("managers") or {}
            manager_name = manager.get("name", "Без менеджера")

            if manager_name not in by_manager:
                by_manager[manager_name] = []

            course_data = {
                "name": user.get("name", "—"),
                "topic_id": user.get("topic_id"),
                "current_day": course.get("current_day", 1),
                "intake_time": (course.get("intake_time") or "—")[:5],
                "late_count": course.get("late_count", 0),
                "course_id": course.get("id"),
                "sent_today": course.get("id") in sent_today,
                "manager_name": manager_name,
            }

            by_manager[manager_name].append(course_data)

            # Собираем pending для отдельной секции
            if course.get("id") in pending_course_ids:
                pending_reviews.append(course_data)

        # Формируем текст
        total = len(courses)
        lines = [f"📊 Активные курсы — {date_display}"]

        # Секция "Ждёт проверки" — сверху, если есть
        if pending_reviews:
            lines.append("")
            lines.append(f"⏳ Ждёт проверки ({len(pending_reviews)}):")
            for girl in pending_reviews:
                name_link = self._make_topic_link(girl["topic_id"], girl["name"])
                lines.append(f"• {name_link} ({girl['manager_name']}) — день {girl['current_day']}/21")

        lines.append("")
        lines.append(f"👥 Всего: {total}")

        for manager_name, girls in sorted(by_manager.items()):
            lines.append("")
            lines.append("━" * 28)
            lines.append(f"👩‍💼 {manager_name} ({len(girls)})")
            lines.append("━" * 28)

            for girl in sorted(girls, key=lambda x: x["current_day"], reverse=True):
                # Иконка статуса
                if girl["late_count"] >= 2:
                    icon = "⚠️"
                    suffix = f" ({girl['late_count']})"
                elif girl["sent_today"]:
                    icon = "✅"
                    suffix = ""
                else:
                    icon = "⬜"
                    suffix = ""

                name_link = self._make_topic_link(girl["topic_id"], girl["name"])
                lines.append(
                    f"{icon} {name_link} — {girl['current_day']}/21, {girl['intake_time']}{suffix}"
                )

        return "\n".join(lines)

    async def generate_refusals(self, days: int = 10) -> str:
        """Генерирует дашборд отказов за последние N дней."""
        now = get_tashkent_now()
        today = now.date()
        start_date = today - timedelta(days=days - 1)

        date_from = self._format_date(start_date.isoformat())
        date_to = self._format_date(today.isoformat())

        # Получаем refused курсы за период (используем created_at вместо updated_at)
        result = await self.supabase.table("courses") \
            .select("*, users(*, managers(*))") \
            .eq("status", "refused") \
            .gte("created_at", start_date.isoformat()) \
            .execute()

        courses = result.data or []

        if not courses:
            return (
                f"🚫 Отказы — последние {days} дней\n"
                f"({date_from} — {date_to})\n\n"
                "Всего: 0"
            )

        # Группируем по менеджерам
        by_manager: dict[str, list] = {}
        for course in courses:
            user = course.get("users") or {}
            manager = user.get("managers") or {}
            manager_name = manager.get("name", "Без менеджера")

            if manager_name not in by_manager:
                by_manager[manager_name] = []

            # Определяем причину
            late_count = course.get("late_count", 0)
            if late_count >= 3:
                reason = "3 опоздания"
            else:
                reason = "пропуск"

            # Дата отказа (из created_at)
            created_at = course.get("created_at", "")[:10]

            by_manager[manager_name].append({
                "name": user.get("name", "—"),
                "topic_id": user.get("topic_id"),
                "current_day": course.get("current_day", 1),
                "reason": reason,
                "date": self._format_date(created_at),
            })

        # Формируем текст
        total = len(courses)
        lines = [
            f"🚫 Отказы — последние {days} дней",
            f"({date_from} — {date_to})",
            "",
            f"Всего: {total}",
        ]

        for manager_name, girls in sorted(by_manager.items()):
            lines.append("")
            lines.append("━" * 28)
            lines.append(f"👩‍💼 {manager_name} ({len(girls)})")
            lines.append("━" * 28)

            for girl in sorted(girls, key=lambda x: x["date"], reverse=True):
                name_link = self._make_topic_link(girl["topic_id"], girl["name"])
                lines.append(
                    f"• {name_link} — {girl['current_day']}/21, {girl['reason']}, {girl['date']}"
                )

        return "\n".join(lines)

    async def update_refusals(self, bot, thread_id: int) -> None:
        """Обновляет дашборд отказов сразу."""
        from app.services.stats_messages import StatsMessagesService

        stats_service = StatsMessagesService(self.supabase)
        refusals_text = await self.generate_refusals(days=10)

        existing = await stats_service.get_by_type("refusals")

        if existing and existing.get("message_id"):
            try:
                await bot.edit_message_text(
                    chat_id=self.group_chat_id,
                    message_id=existing["message_id"],
                    text=refusals_text,
                    parse_mode="HTML",
                )
                print(f"📊 Dashboard 'refusals' updated")
                return
            except Exception as e:
                error_msg = str(e).lower()

                if "message is not modified" in error_msg:
                    print(f"📊 Dashboard 'refusals' unchanged")
                    return

                if "message to edit not found" in error_msg:
                    print(f"⚠️ Refusals message not found, recreating...")
                else:
                    print(f"⚠️ Edit refusals failed: {e}")
                    return

        # Создаём новое сообщение
        try:
            message = await bot.send_message(
                chat_id=self.group_chat_id,
                message_thread_id=thread_id,
                text=refusals_text,
                parse_mode="HTML",
            )

            try:
                await bot.pin_chat_message(
                    chat_id=self.group_chat_id,
                    message_id=message.message_id,
                    disable_notification=True
                )
            except Exception:
                pass

            await stats_service.upsert(
                message_type="refusals",
                message_id=message.message_id,
                chat_id=self.group_chat_id,
                thread_id=thread_id,
            )
            print(f"📊 Dashboard 'refusals' created")
        except Exception as e:
            print(f"❌ Failed to create refusals dashboard: {e}")
