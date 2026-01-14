"""Сервис для генерации дашбордов."""

from datetime import datetime, timedelta, timezone
from app.utils.time_utils import get_tashkent_now, MONTHS
from app.config import get_settings
from app.utils.format import short_name

# Разделитель секций
SEPARATOR = "━" * 24


class DashboardService:
    """Генерирует дашборды для группы менеджеров."""

    def __init__(self, supabase, kok_group_id: int):
        self.supabase = supabase
        self.kok_group_id = kok_group_id  # Группа с топиками девушек

    @staticmethod
    def _format_date(date_str: str) -> str:
        """Форматирует дату: 2026-01-06 → 6 Янв"""
        try:
            date = datetime.fromisoformat(date_str).date()
            month = MONTHS[date.month]
            return f"{date.day} {month}"
        except (ValueError, TypeError):
            return date_str

    @staticmethod
    def _format_time(time_str: str) -> str:
        """Форматирует время: 14:30:00 → 14:30"""
        if not time_str:
            return "—"
        return time_str[:5]

    def _make_topic_link(self, topic_id: int | None, name: str) -> str:
        """Создаёт кликабельную ссылку на топик в группе КОК."""
        if not topic_id:
            return name

        # Убираем -100 из chat_id для ссылки
        chat_id = str(self.kok_group_id)
        if chat_id.startswith("-100"):
            chat_id = chat_id[4:]

        short = short_name(name)
        return f'<a href="https://t.me/c/{chat_id}/{topic_id}">{short}</a>'

    async def generate_full_dashboard(self) -> str:
        """Генерирует единый дашборд КОК."""
        now = get_tashkent_now()
        today = now.date()
        time_str = now.strftime("%H:%M")
        date_str = self._format_date(today.isoformat())

        lines = [f"📊 <b>КОК</b> — {date_str}, {time_str}"]

        # === АКТИВНЫЕ ===
        active_section = await self._generate_active_section()
        lines.append(SEPARATOR)
        lines.extend(active_section)
        lines.append("")  # Отступ перед разделителем

        # === ОТКАЗЫ (10 дней) ===
        refusals_section = await self._generate_refusals_section(today, days=10)
        lines.append(SEPARATOR)
        lines.extend(refusals_section)
        lines.append("")  # Отступ перед разделителем

        # === ЗАВЕРШИЛИ (текущий и прошлый месяц) ===
        completed_section = await self._generate_completed_section(today)
        lines.append(SEPARATOR)
        lines.extend(completed_section)
        lines.append("")  # Отступ перед разделителем

        # === ИТОГО ===
        totals = await self._get_totals()
        lines.append(SEPARATOR)
        lines.append(f"💊 {totals['active']} · ✅ {totals['completed']} · ❌ {totals['refused']}")

        return "\n".join(lines)

    async def _generate_active_section(self) -> list[str]:
        """Генерирует секцию активных курсов."""
        # Получаем активные курсы
        result = await self.supabase.table("courses") \
            .select("*, users(*, managers(*))") \
            .eq("status", "active") \
            .execute()

        courses = result.data or []

        lines = [f"💊 <b>Активные</b>", ""]

        if not courses:
            lines.append("— пусто —")
            return lines

        # Получаем intake_logs за сегодня
        tashkent_now = get_tashkent_now()
        tashkent_midnight = tashkent_now.replace(hour=0, minute=0, second=0, microsecond=0)
        utc_today = tashkent_midnight.astimezone(timezone.utc).isoformat()

        today_logs = await self.supabase.table("intake_logs") \
            .select("course_id, status") \
            .gte("created_at", utc_today) \
            .in_("status", ["taken", "late", "pending_review"]) \
            .execute()

        sent_today = set()
        pending_ids = set()

        for log in (today_logs.data or []):
            if log["status"] == "pending_review":
                pending_ids.add(log["course_id"])
            else:
                sent_today.add(log["course_id"])

        # Группируем по менеджерам
        by_manager: dict[str, list] = {}

        for course in courses:
            user = course.get("users") or {}
            manager = user.get("managers") or {}
            manager_name = manager.get("name", "—")

            if manager_name not in by_manager:
                by_manager[manager_name] = []

            # Определяем статус
            course_id = course.get("id")
            late_count = course.get("late_count", 0)
            has_risk = late_count >= 2

            if course_id in pending_ids:
                icon = "⏳⚠️" if has_risk else "⏳"
            elif course_id in sent_today:
                icon = "✅⚠️" if has_risk else "✅"
            elif has_risk:
                icon = "⚠️"
            else:
                icon = "⬜"

            total_days = course.get("total_days") or 21

            by_manager[manager_name].append({
                "name": user.get("name", "—"),
                "topic_id": user.get("topic_id"),
                "completed_days": course.get("current_day", 1) - 1,
                "total_days": total_days,
                "intake_time": self._format_time(course.get("intake_time")),
                "icon": icon,
            })

        # Формируем текст
        for manager_name, girls in sorted(by_manager.items()):
            lines.append(f"👩‍💼 {manager_name}")
            for girl in sorted(girls, key=lambda x: x["completed_days"], reverse=True):
                name_link = self._make_topic_link(girl["topic_id"], girl["name"])
                lines.append(
                    f"   {girl['icon']} {name_link} — {girl['completed_days']}/{girl['total_days']}, {girl['intake_time']}"
                )

        return lines

    async def _generate_refusals_section(self, today, days: int = 10) -> list[str]:
        """Генерирует секцию отказов."""
        start_date = today - timedelta(days=days - 1)

        # Получаем refused курсы за период
        result = await self.supabase.table("courses") \
            .select("*, users(*, managers(*))") \
            .eq("status", "refused") \
            .gte("created_at", start_date.isoformat()) \
            .execute()

        courses = result.data or []

        lines = [f"❌ <b>Отказы</b>", ""]

        if not courses:
            lines.append("— пусто —")
            return lines

        # Группируем по менеджерам
        by_manager: dict[str, list] = {}

        for course in courses:
            user = course.get("users") or {}
            manager = user.get("managers") or {}
            manager_name = manager.get("name", "—")

            if manager_name not in by_manager:
                by_manager[manager_name] = []

            # Определяем причину
            late_count = course.get("late_count", 0)
            if late_count >= 3:
                reason = "3 опоздания"
            else:
                reason = "пропуск"

            created_at = course.get("created_at", "")[:10]

            by_manager[manager_name].append({
                "name": user.get("name", "—"),
                "topic_id": user.get("topic_id"),
                "reason": reason,
                "date": self._format_date(created_at),
            })

        # Формируем текст
        for manager_name, girls in sorted(by_manager.items()):
            lines.append(f"👩‍💼 {manager_name}")
            for girl in sorted(girls, key=lambda x: x["date"], reverse=True):
                name_link = self._make_topic_link(girl["topic_id"], girl["name"])
                lines.append(
                    f"   • {name_link} — {girl['reason']}, {girl['date']}"
                )

        return lines

    async def _generate_completed_section(self, today) -> list[str]:
        """Генерирует секцию завершивших (текущий и прошлый месяц)."""
        # Текущий месяц
        current_month_start = today.replace(day=1)
        # Прошлый месяц
        prev_month_end = current_month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)

        # Получаем completed за 2 месяца
        result = await self.supabase.table("courses") \
            .select("*, users(*, managers(*))") \
            .eq("status", "completed") \
            .gte("created_at", prev_month_start.isoformat()) \
            .execute()

        courses = result.data or []

        lines = [f"✅ <b>Завершили</b>", ""]

        if not courses:
            lines.append("— пусто —")
            return lines

        # Разделяем по месяцам
        current_month_courses = []
        prev_month_courses = []

        for course in courses:
            created_at = course.get("created_at", "")[:10]
            try:
                course_date = datetime.fromisoformat(created_at).date()
                if course_date >= current_month_start:
                    current_month_courses.append(course)
                else:
                    prev_month_courses.append(course)
            except (ValueError, TypeError):
                pass

        # Текущий месяц
        if current_month_courses:
            month_name = MONTHS[today.month]
            lines.append(f"{month_name} - {len(current_month_courses)}")
            lines.extend(self._format_completed_by_manager(current_month_courses))

        # Прошлый месяц
        if prev_month_courses:
            month_name = MONTHS[prev_month_end.month]
            lines.append(f"{month_name} - {len(prev_month_courses)}")
            lines.extend(self._format_completed_by_manager(prev_month_courses))

        return lines

    def _format_completed_by_manager(self, courses: list) -> list[str]:
        """Форматирует завершивших по менеджерам."""
        by_manager: dict[str, list] = {}

        for course in courses:
            user = course.get("users") or {}
            manager = user.get("managers") or {}
            manager_name = manager.get("name", "—")

            if manager_name not in by_manager:
                by_manager[manager_name] = []

            created_at = course.get("created_at", "")[:10]

            by_manager[manager_name].append({
                "name": user.get("name", "—"),
                "topic_id": user.get("topic_id"),
                "date": self._format_date(created_at),
            })

        lines = []
        for manager_name, girls in sorted(by_manager.items()):
            lines.append(f"👩‍💼 {manager_name}")
            for girl in sorted(girls, key=lambda x: x["date"], reverse=True):
                name_link = self._make_topic_link(girl["topic_id"], girl["name"])
                lines.append(f"   • {name_link} — {girl['date']}")

        return lines

    async def _get_totals(self) -> dict:
        """Получает общее количество по статусам (за всё время)."""
        result = await self.supabase.table("courses") \
            .select("status") \
            .execute()

        courses = result.data or []

        totals = {"active": 0, "completed": 0, "refused": 0}
        for course in courses:
            status = course.get("status")
            if status in totals:
                totals[status] += 1

        return totals

    async def update_dashboard(self, bot, thread_id: int) -> None:
        """Обновляет единый дашборд."""
        from app.services.stats_messages import StatsMessagesService

        settings = get_settings()
        stats_service = StatsMessagesService(self.supabase, settings.bot_type)
        dashboard_text = await self.generate_full_dashboard()

        existing = await stats_service.get()

        if existing and existing.get("message_id"):
            try:
                await bot.edit_message_text(
                    chat_id=settings.commands_group_id,
                    message_id=existing["message_id"],
                    text=dashboard_text,
                    parse_mode="HTML",
                )
                await stats_service.update_timestamp()
                print(f"📊 Dashboard '{settings.bot_type}' updated")
                return
            except Exception as e:
                error_msg = str(e).lower()

                if "message is not modified" in error_msg:
                    print(f"📊 Dashboard '{settings.bot_type}' unchanged")
                    return

                if "message to edit not found" in error_msg:
                    print(f"⚠️ Dashboard message not found, recreating...")
                else:
                    print(f"⚠️ Edit failed: {e}")
                    return

        # Создаём новое сообщение
        try:
            # Для General топика НЕ передаём message_thread_id
            # thread_id=0 или thread_id=None = General топик
            send_kwargs = {
                "chat_id": settings.commands_group_id,
                "text": dashboard_text,
                "parse_mode": "HTML",
            }
            if thread_id and thread_id > 0:
                send_kwargs["message_thread_id"] = thread_id

            message = await bot.send_message(**send_kwargs)

            await stats_service.upsert(message_id=message.message_id)
            print(f"📊 Dashboard '{settings.bot_type}' created, message_id={message.message_id}")
        except Exception as e:
            print(f"❌ Failed to create dashboard: {e}")