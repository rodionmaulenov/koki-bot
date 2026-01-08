"""Тесты для handlers/group.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_state():
    """Mock FSMContext."""
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state


class TestAddCommand:
    """Тесты для /add команды (FSM)."""

    @pytest.mark.asyncio
    async def test_not_manager_error(
        self,
        mock_message,
        mock_state,
        manager_service,
    ):
        """Ошибка если не менеджер."""
        from app.handlers.group import add_command

        message = mock_message(text="/add", user_id=999999999)

        await add_command(
            message=message,
            state=mock_state,
            manager_service=manager_service,
        )

        message.reply.assert_called_once()
        call_text = message.reply.call_args[0][0]
        assert "не менеджер" in call_text.lower()

        # FSM не должен активироваться
        mock_state.set_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_asks_for_name(
        self,
        mock_message,
        mock_state,
        manager_service,
        test_manager,
    ):
        """Спрашивает ФИО после команды."""
        from app.handlers.group import add_command

        message = mock_message(
            text="/add",
            user_id=test_manager["telegram_id"],
        )

        await add_command(
            message=message,
            state=mock_state,
            manager_service=manager_service,
        )

        # Проверяем что спросил ФИО
        message.reply.assert_called_once()
        call_text = message.reply.call_args[0][0]
        assert "ФИО" in call_text or "Введи" in call_text

        # FSM активирован
        mock_state.set_state.assert_called_once()
        mock_state.update_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_link(
        self,
        mock_message,
        mock_state,
        user_service,
        course_service,
        bot,
        test_manager,
    ):
        """Создаёт ссылку после ввода ФИО."""
        from app.handlers.group import add_process_name

        message = mock_message(
            text="Иванова Мария Петровна",
            user_id=test_manager["telegram_id"],
        )

        # Устанавливаем данные из первого шага
        mock_state.get_data = AsyncMock(return_value={"manager_id": test_manager["id"]})

        # Мокаем bot.get_me()
        bot_user = MagicMock()
        bot_user.username = "test_bot"
        bot.get_me = AsyncMock(return_value=bot_user)

        await add_process_name(
            message=message,
            state=mock_state,
            user_service=user_service,
            course_service=course_service,
            bot=bot,
        )

        # Проверяем ответ
        message.reply.assert_called_once()
        call_text = message.reply.call_args[0][0]
        assert "Ссылка" in call_text or "t.me" in call_text
        assert "Иванова Мария Петровна" in call_text

        # FSM очищен
        mock_state.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_user_in_db(
        self,
        mock_message,
        mock_state,
        user_service,
        course_service,
        bot,
        test_manager,
        supabase,
    ):
        """Создаёт user в БД."""
        from app.handlers.group import add_process_name

        girl_name = "Тестовая Девушка БД"

        message = mock_message(
            text=girl_name,
            user_id=test_manager["telegram_id"],
        )

        mock_state.get_data = AsyncMock(return_value={"manager_id": test_manager["id"]})

        bot_user = MagicMock()
        bot_user.username = "test_bot"
        bot.get_me = AsyncMock(return_value=bot_user)

        await add_process_name(
            message=message,
            state=mock_state,
            user_service=user_service,
            course_service=course_service,
            bot=bot,
        )

        # Проверяем что user создан
        result = await supabase.table("users") \
            .select("*") \
            .eq("name", girl_name) \
            .execute()

        assert len(result.data) == 1
        assert result.data[0]["manager_id"] == test_manager["id"]

    @pytest.mark.asyncio
    async def test_creates_course_in_db(
        self,
        mock_message,
        mock_state,
        user_service,
        course_service,
        bot,
        test_manager,
        supabase,
    ):
        """Создаёт course в БД."""
        from app.handlers.group import add_process_name

        girl_name = "Курсовая Девушка БД"

        message = mock_message(
            text=girl_name,
            user_id=test_manager["telegram_id"],
        )

        mock_state.get_data = AsyncMock(return_value={"manager_id": test_manager["id"]})

        bot_user = MagicMock()
        bot_user.username = "test_bot"
        bot.get_me = AsyncMock(return_value=bot_user)

        await add_process_name(
            message=message,
            state=mock_state,
            user_service=user_service,
            course_service=course_service,
            bot=bot,
        )

        # Находим user
        user_result = await supabase.table("users") \
            .select("id") \
            .eq("name", girl_name) \
            .execute()

        user_id = user_result.data[0]["id"]

        # Проверяем course
        course_result = await supabase.table("courses") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        assert len(course_result.data) == 1
        assert course_result.data[0]["status"] == "setup"
        assert course_result.data[0]["invite_used"] is False

    @pytest.mark.asyncio
    async def test_short_name_error(
        self,
        mock_message,
        mock_state,
        user_service,
        course_service,
        bot,
        test_manager,
    ):
        """Ошибка если ФИО слишком короткое."""
        from app.handlers.group import add_process_name

        message = mock_message(
            text="Аб",  # Меньше 3 символов
            user_id=test_manager["telegram_id"],
        )

        mock_state.get_data = AsyncMock(return_value={"manager_id": test_manager["id"]})

        await add_process_name(
            message=message,
            state=mock_state,
            user_service=user_service,
            course_service=course_service,
            bot=bot,
        )

        # Просит ввести корректное ФИО
        message.reply.assert_called_once()
        call_text = message.reply.call_args[0][0]
        assert "корректное" in call_text.lower() or "минимум" in call_text.lower()

        # FSM НЕ очищен — ждём правильный ввод
        mock_state.clear.assert_not_called()


class TestAddVideoCommand:
    """Тесты для /add_video команды (FSM)."""

    @pytest.mark.asyncio
    async def test_not_manager_error(
        self,
        mock_message,
        mock_state,
        manager_service,
    ):
        """Ошибка если не менеджер."""
        from app.handlers.group import add_video_command

        message = mock_message(text="/add_video", user_id=999999999)

        await add_video_command(
            message=message,
            state=mock_state,
            manager_service=manager_service,
        )

        message.reply.assert_called_once()
        call_text = message.reply.call_args[0][0]
        assert "не менеджер" in call_text.lower()

    @pytest.mark.asyncio
    async def test_asks_for_name(
        self,
        mock_message,
        mock_state,
        manager_service,
        test_manager,
    ):
        """Спрашивает ФИО после команды."""
        from app.handlers.group import add_video_command

        message = mock_message(
            text="/add_video",
            user_id=test_manager["telegram_id"],
        )

        await add_video_command(
            message=message,
            state=mock_state,
            manager_service=manager_service,
        )

        message.reply.assert_called_once()
        call_text = message.reply.call_args[0][0]
        assert "ФИО" in call_text or "Введи" in call_text

        mock_state.set_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_girl_not_found(
        self,
        mock_message,
        mock_state,
        user_service,
        course_service,
        test_manager,
    ):
        """Ошибка если девушка не найдена."""
        from app.handlers.group import add_video_process_name

        message = mock_message(
            text="Несуществующая Девушка",
            user_id=test_manager["telegram_id"],
        )

        mock_state.get_data = AsyncMock(return_value={"manager_id": test_manager["id"]})

        await add_video_process_name(
            message=message,
            state=mock_state,
            user_service=user_service,
            course_service=course_service,
        )

        message.reply.assert_called_once()
        call_text = message.reply.call_args[0][0]
        assert "не найдена" in call_text.lower()

        mock_state.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_allows_video(
        self,
        mock_message,
        mock_state,
        user_service,
        course_service,
        test_manager,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Разрешает обычное видео."""
        from app.handlers.group import add_video_process_name

        message = mock_message(
            text=test_user_with_telegram["name"],
            user_id=test_manager["telegram_id"],
        )

        mock_state.get_data = AsyncMock(return_value={"manager_id": test_manager["id"]})

        await add_video_process_name(
            message=message,
            state=mock_state,
            user_service=user_service,
            course_service=course_service,
        )

        # Проверяем ответ
        message.reply.assert_called_once()
        call_text = message.reply.call_args[0][0]
        assert "обычное видео" in call_text.lower() or "✅" in call_text

        # Проверяем БД
        course = await supabase.table("courses") \
            .select("allow_video") \
            .eq("id", test_active_course["id"]) \
            .single() \
            .execute()

        assert course.data["allow_video"] is True

        mock_state.clear.assert_called_once()


class TestCompleteCourseCallback:
    """Тесты для досрочного завершения курса."""

    @pytest.mark.asyncio
    async def test_completes_course(
        self,
        mock_callback,
        course_service,
        user_service,
        bot,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Успешно завершает курс досрочно."""
        from app.handlers.group import complete_course_callback

        callback = mock_callback(
            data=f"complete_{test_active_course['id']}",
            user_id=test_user_with_telegram["telegram_id"],
        )

        await complete_course_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            bot=bot,
        )

        # Проверяем что курс завершён
        course = await supabase.table("courses") \
            .select("status") \
            .eq("id", test_active_course["id"]) \
            .single() \
            .execute()

        assert course.data["status"] == "completed"
        callback.message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_course_not_found(
        self,
        mock_callback,
        course_service,
        user_service,
        bot,
    ):
        """Курс не найден."""
        from app.handlers.group import complete_course_callback
        from app import templates

        callback = mock_callback(data="complete_99999")

        await complete_course_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            bot=bot,
        )

        callback.message.edit_text.assert_called_once()
        call_text = callback.message.edit_text.call_args[0][0]
        assert call_text == templates.MANAGER_COURSE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_already_completed(
        self,
        mock_callback,
        course_service,
        user_service,
        bot,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Курс уже завершён."""
        from app.handlers.group import complete_course_callback

        # Завершаем курс
        await supabase.table("courses") \
            .update({"status": "completed"}) \
            .eq("id", test_active_course["id"]) \
            .execute()

        callback = mock_callback(
            data=f"complete_{test_active_course['id']}",
        )

        await complete_course_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            bot=bot,
        )

        call_text = callback.message.edit_text.call_args[0][0]
        assert "уже завершён" in call_text.lower()


class TestExtendCourseCallback:
    """Тесты для продления курса."""

    @pytest.mark.asyncio
    async def test_extends_course(
        self,
        mock_callback,
        course_service,
        user_service,
        manager_service,
        topic_service,
        bot,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Успешно продлевает курс на +21 день."""
        from app.handlers.group import extend_course_callback

        callback = mock_callback(
            data=f"extend_{test_active_course['id']}",
            user_id=test_user_with_telegram["telegram_id"],
        )

        await extend_course_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            manager_service=manager_service,
            topic_service=topic_service,
            bot=bot,
        )

        # Проверяем что total_days увеличился
        course = await supabase.table("courses") \
            .select("total_days") \
            .eq("id", test_active_course["id"]) \
            .single() \
            .execute()

        assert course.data["total_days"] == 42
        callback.message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_extends_already_extended(
        self,
        mock_callback,
        course_service,
        user_service,
        manager_service,
        topic_service,
        bot,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Продлевает уже продлённый курс (42 → 63)."""
        from app.handlers.group import extend_course_callback

        # Устанавливаем total_days = 42
        await supabase.table("courses") \
            .update({"total_days": 42}) \
            .eq("id", test_active_course["id"]) \
            .execute()

        callback = mock_callback(
            data=f"extend_{test_active_course['id']}",
        )

        await extend_course_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            manager_service=manager_service,
            topic_service=topic_service,
            bot=bot,
        )

        course = await supabase.table("courses") \
            .select("total_days") \
            .eq("id", test_active_course["id"]) \
            .single() \
            .execute()

        assert course.data["total_days"] == 63

    @pytest.mark.asyncio
    async def test_extend_not_active(
        self,
        mock_callback,
        course_service,
        user_service,
        manager_service,
        topic_service,
        bot,
        test_active_course,
        supabase,
    ):
        """Нельзя продлить неактивный курс."""
        from app.handlers.group import extend_course_callback

        # Завершаем курс
        await supabase.table("courses") \
            .update({"status": "completed"}) \
            .eq("id", test_active_course["id"]) \
            .execute()

        callback = mock_callback(
            data=f"extend_{test_active_course['id']}",
        )

        await extend_course_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            manager_service=manager_service,
            topic_service=topic_service,
            bot=bot,
        )

        call_text = callback.message.edit_text.call_args[0][0]
        assert "не активен" in call_text.lower()

    @pytest.mark.asyncio
    async def test_extend_course_not_found(
        self,
        mock_callback,
        course_service,
        user_service,
        manager_service,
        topic_service,
        bot,
    ):
        """Курс не найден."""
        from app.handlers.group import extend_course_callback
        from app import templates

        callback = mock_callback(data="extend_99999")

        await extend_course_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            manager_service=manager_service,
            topic_service=topic_service,
            bot=bot,
        )

        call_text = callback.message.edit_text.call_args[0][0]
        assert call_text == templates.MANAGER_COURSE_NOT_FOUND