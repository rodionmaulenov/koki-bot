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


@pytest.fixture
def mock_commands_messages_service():
    """Mock CommandsMessagesService."""
    service = MagicMock()
    service.get_all = AsyncMock(return_value=[])
    service.delete_all = AsyncMock()
    service.add = AsyncMock()
    return service


class TestAddCommand:
    """Тесты для /add команды (FSM)."""

    @pytest.mark.asyncio
    async def test_not_manager_error(
        self,
        mock_message,
        mock_state,
        manager_service,
        mock_commands_messages_service,
    ):
        """Ошибка если не менеджер."""
        from app.handlers.group import add_command

        message = mock_message(text="/add", user_id=999999999)

        await add_command(
            message=message,
            state=mock_state,
            manager_service=manager_service,
            commands_messages_service=mock_commands_messages_service,
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
        mock_commands_messages_service,
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
            commands_messages_service=mock_commands_messages_service,
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
        mock_commands_messages_service,
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
            commands_messages_service=mock_commands_messages_service,
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
        mock_commands_messages_service,
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
            commands_messages_service=mock_commands_messages_service,
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
        mock_commands_messages_service,
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
            commands_messages_service=mock_commands_messages_service,
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
    async def test_incomplete_name_error(
        self,
        mock_message,
        mock_state,
        user_service,
        course_service,
        bot,
        test_manager,
        mock_commands_messages_service,
    ):
        """Ошибка если ФИО неполное (меньше 3 слов)."""
        from app.handlers.group import add_process_name

        message = mock_message(
            text="Иванова Мария",  # Только 2 слова
            user_id=test_manager["telegram_id"],
        )

        mock_state.get_data = AsyncMock(return_value={"manager_id": test_manager["id"]})

        await add_process_name(
            message=message,
            state=mock_state,
            user_service=user_service,
            course_service=course_service,
            bot=bot,
            commands_messages_service=mock_commands_messages_service,
        )

        # Просит ввести полное ФИО
        message.reply.assert_called_once()
        call_text = message.reply.call_args[0][0]
        assert "полное фио" in call_text.lower() or "фамилия имя отчество" in call_text.lower()

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
        mock_commands_messages_service,
    ):
        """Ошибка если не менеджер."""
        from app.handlers.group import add_video_command

        message = mock_message(text="/add_video", user_id=999999999)

        await add_video_command(
            message=message,
            state=mock_state,
            manager_service=manager_service,
            commands_messages_service=mock_commands_messages_service,
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
        mock_commands_messages_service,
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
            commands_messages_service=mock_commands_messages_service,
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
        mock_commands_messages_service,
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
            commands_messages_service=mock_commands_messages_service,
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
        mock_commands_messages_service,
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
            commands_messages_service=mock_commands_messages_service,
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
        manager_service,
        topic_service,
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
            manager_service=manager_service,
            topic_service=topic_service,
            bot=bot,
        )

        # Проверяем что курс завершён
        course = await supabase.table("courses") \
            .select("status") \
            .eq("id", test_active_course["id"]) \
            .single() \
            .execute()

        assert course.data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_course_not_found(
        self,
        mock_callback,
        course_service,
        user_service,
        manager_service,
        topic_service,
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
            manager_service=manager_service,
            topic_service=topic_service,
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
        manager_service,
        topic_service,
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
            manager_service=manager_service,
            topic_service=topic_service,
            bot=bot,
        )

        call_text = callback.message.edit_text.call_args[0][0]
        assert "уже завершён" in call_text.lower()

    @pytest.mark.asyncio
    async def test_full_closure_sequence_on_complete(
        self,
        mock_callback,
        course_service,
        user_service,
        bot,
        test_manager,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Выполняет полную последовательность закрытия топика."""
        from app.handlers.group import complete_course_callback
        from app.services.managers import ManagerService

        # Устанавливаем topic_id и registration_message_id
        topic_id = 12345
        registration_message_id = 999

        await supabase.table("users") \
            .update({"topic_id": topic_id}) \
            .eq("id", test_user_with_telegram["id"]) \
            .execute()

        await supabase.table("courses") \
            .update({"registration_message_id": registration_message_id}) \
            .eq("id", test_active_course["id"]) \
            .execute()

        # Mock topic_service
        mock_topic_service = MagicMock()
        mock_topic_service.rename_topic_on_close = AsyncMock()
        mock_topic_service.remove_registration_buttons = AsyncMock()
        mock_topic_service.send_closure_message = AsyncMock()
        mock_topic_service.close_topic = AsyncMock()

        manager_service = ManagerService(supabase)

        callback = mock_callback(
            data=f"complete_{test_active_course['id']}",
            user_id=test_user_with_telegram["telegram_id"],
        )

        await complete_course_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            manager_service=manager_service,
            topic_service=mock_topic_service,
            bot=bot,
        )

        # Проверяем что вся последовательность выполнена
        mock_topic_service.rename_topic_on_close.assert_called_once()
        mock_topic_service.remove_registration_buttons.assert_called_once()
        mock_topic_service.send_closure_message.assert_called_once()
        mock_topic_service.close_topic.assert_called_once()

        # Проверяем параметры rename
        rename_call = mock_topic_service.rename_topic_on_close.call_args
        assert rename_call.kwargs["topic_id"] == topic_id
        assert rename_call.kwargs["status"] == "completed"

        # Проверяем параметры closure message
        closure_call = mock_topic_service.send_closure_message.call_args
        assert closure_call.kwargs["status"] == "completed"

    @pytest.mark.asyncio
    async def test_skips_buttons_removal_if_no_message_id(
        self,
        mock_callback,
        course_service,
        user_service,
        bot,
        test_manager,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Пропускает удаление кнопок если нет registration_message_id."""
        from app.handlers.group import complete_course_callback
        from app.services.managers import ManagerService

        # Устанавливаем topic_id БЕЗ registration_message_id
        topic_id = 12345
        await supabase.table("users") \
            .update({"topic_id": topic_id}) \
            .eq("id", test_user_with_telegram["id"]) \
            .execute()

        mock_topic_service = MagicMock()
        mock_topic_service.rename_topic_on_close = AsyncMock()
        mock_topic_service.remove_registration_buttons = AsyncMock()
        mock_topic_service.send_closure_message = AsyncMock()
        mock_topic_service.close_topic = AsyncMock()

        manager_service = ManagerService(supabase)

        callback = mock_callback(
            data=f"complete_{test_active_course['id']}",
        )

        await complete_course_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            manager_service=manager_service,
            topic_service=mock_topic_service,
            bot=bot,
        )

        # remove_registration_buttons НЕ должен вызываться
        mock_topic_service.remove_registration_buttons.assert_not_called()

        # Остальные методы должны вызываться
        mock_topic_service.rename_topic_on_close.assert_called_once()
        mock_topic_service.send_closure_message.assert_called_once()
        mock_topic_service.close_topic.assert_called_once()


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


class TestClearCommand:
    """Тесты для /clear команды."""

    @pytest.fixture
    def mock_commands_messages_service(self):
        """Mock CommandsMessagesService."""
        service = MagicMock()
        service.get_all = AsyncMock(return_value=[100, 200, 300, 400, 500])
        service.delete_all = AsyncMock()
        service.add = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_clear_deletes_saved_messages(
        self,
        mock_message,
        mock_state,
        bot,
        mock_commands_messages_service,
    ):
        """Команда удаляет только сохранённые сообщения."""
        from app.handlers.group import clear_command

        message = mock_message(text="/clear", user_id=123)
        message.message_id = 1000
        message.delete = AsyncMock()

        deleted_ids = []
        async def mock_delete(chat_id, message_id):
            deleted_ids.append(message_id)
            return True

        bot.delete_message = mock_delete

        await clear_command(
            message=message,
            state=mock_state,
            bot=bot,
            commands_messages_service=mock_commands_messages_service,
        )

        # FSM сброшен
        mock_state.clear.assert_called_once()

        # Удалены только сохранённые ID
        assert set(deleted_ids) == {100, 200, 300, 400, 500, 1000}

        # Таблица очищена
        mock_commands_messages_service.delete_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_handles_empty_table(
        self,
        mock_message,
        mock_state,
        bot,
    ):
        """Нет сохранённых сообщений — ничего не удаляем."""
        from app.handlers.group import clear_command

        message = mock_message(text="/clear", user_id=123)
        message.message_id = 100
        message.delete = AsyncMock()

        # Пустая таблица
        mock_service = MagicMock()
        mock_service.get_all = AsyncMock(return_value=[])
        mock_service.delete_all = AsyncMock()

        await clear_command(
            message=message,
            state=mock_state,
            bot=bot,
            commands_messages_service=mock_service,
        )

        # FSM сброшен
        mock_state.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_skips_rules_message(
        self,
        mock_message,
        mock_state,
        bot,
        monkeypatch,
    ):
        """Сообщение с правилами не удаляется."""
        from app.handlers import group
        from app.handlers.group import clear_command

        message = mock_message(text="/clear", user_id=123)
        message.message_id = 1000
        message.delete = AsyncMock()

        # ID правил = 200 (один из сохранённых)
        rules_id = 200

        mock_settings = MagicMock()
        mock_settings.rules_message_id = rules_id
        monkeypatch.setattr(group, "settings", mock_settings)

        # Сервис возвращает ID включая rules_id
        mock_service = MagicMock()
        mock_service.get_all = AsyncMock(return_value=[100, 200, 300])
        mock_service.delete_all = AsyncMock()

        deleted_ids = []
        async def mock_delete(chat_id, message_id):
            deleted_ids.append(message_id)
            return True

        bot.delete_message = mock_delete

        await clear_command(
            message=message,
            state=mock_state,
            bot=bot,
            commands_messages_service=mock_service,
        )

        # rules_id НЕ был удалён
        assert rules_id not in deleted_ids
        # Остальные удалены
        assert 100 in deleted_ids
        assert 300 in deleted_ids

    @pytest.mark.asyncio
    async def test_clear_resets_fsm_state(
        self,
        mock_message,
        mock_state,
        bot,
        mock_commands_messages_service,
    ):
        """Сбрасывает FSM если был в процессе /add."""
        from app.handlers.group import clear_command

        message = mock_message(text="/clear", user_id=123)
        message.delete = AsyncMock()

        # Симулируем что FSM был активен
        mock_state.get_state = AsyncMock(return_value="AddGirlStates:waiting_for_name")

        await clear_command(
            message=message,
            state=mock_state,
            bot=bot,
            commands_messages_service=mock_commands_messages_service,
        )

        # FSM сброшен
        mock_state.clear.assert_called_once()


class TestVerifyNoCallback:
    """Тесты для отклонения видео менеджером."""

    @pytest.mark.asyncio
    async def test_rejects_video_and_closes_course(
        self,
        mock_callback,
        course_service,
        user_service,
        manager_service,
        intake_logs_service,
        bot,
        test_manager,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Отклоняет видео и завершает курс."""
        from app.handlers.group import verify_no_callback

        # Создаём intake_log для текущего дня
        await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=1,
            status="pending_review",
            video_file_id="test_video",
        )

        mock_topic_service = MagicMock()
        mock_topic_service.rename_topic_on_close = AsyncMock()
        mock_topic_service.remove_registration_buttons = AsyncMock()
        mock_topic_service.send_closure_message = AsyncMock()
        mock_topic_service.close_topic = AsyncMock()

        callback = mock_callback(
            data=f"verify_no_{test_active_course['id']}_1",
            user_id=test_manager["telegram_id"],
        )

        await verify_no_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            manager_service=manager_service,
            intake_logs_service=intake_logs_service,
            topic_service=mock_topic_service,
            bot=bot,
            supabase=supabase,
        )

        # Проверяем что курс refused
        course = await supabase.table("courses") \
            .select("status") \
            .eq("id", test_active_course["id"]) \
            .single() \
            .execute()

        assert course.data["status"] == "refused"

    @pytest.mark.asyncio
    async def test_full_closure_sequence_on_reject(
        self,
        mock_callback,
        course_service,
        user_service,
        intake_logs_service,
        bot,
        test_manager,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Выполняет полную последовательность закрытия при отклонении."""
        from app.handlers.group import verify_no_callback
        from app.services.managers import ManagerService
        from app import templates

        # Устанавливаем topic_id и registration_message_id
        topic_id = 12345
        registration_message_id = 999

        await supabase.table("users") \
            .update({"topic_id": topic_id}) \
            .eq("id", test_user_with_telegram["id"]) \
            .execute()

        await supabase.table("courses") \
            .update({"registration_message_id": registration_message_id}) \
            .eq("id", test_active_course["id"]) \
            .execute()

        # Создаём intake_log
        await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=1,
            status="pending_review",
            video_file_id="test_video",
        )

        mock_topic_service = MagicMock()
        mock_topic_service.rename_topic_on_close = AsyncMock()
        mock_topic_service.remove_registration_buttons = AsyncMock()
        mock_topic_service.send_closure_message = AsyncMock()
        mock_topic_service.close_topic = AsyncMock()

        manager_service = ManagerService(supabase)

        callback = mock_callback(
            data=f"verify_no_{test_active_course['id']}_1",
            user_id=test_manager["telegram_id"],
        )

        await verify_no_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            manager_service=manager_service,
            intake_logs_service=intake_logs_service,
            topic_service=mock_topic_service,
            bot=bot,
            supabase=supabase,
        )

        # Проверяем полную последовательность
        mock_topic_service.rename_topic_on_close.assert_called_once()
        mock_topic_service.remove_registration_buttons.assert_called_once()
        mock_topic_service.send_closure_message.assert_called_once()
        mock_topic_service.close_topic.assert_called_once()

        # Проверяем что статус refused
        rename_call = mock_topic_service.rename_topic_on_close.call_args
        assert rename_call.kwargs["status"] == "refused"

        # Проверяем причину
        closure_call = mock_topic_service.send_closure_message.call_args
        assert closure_call.kwargs["reason"] == templates.REFUSAL_REASON_VIDEO_REJECTED

    @pytest.mark.asyncio
    async def test_updates_intake_log_status(
        self,
        mock_callback,
        course_service,
        user_service,
        manager_service,
        intake_logs_service,
        topic_service,
        bot,
        test_manager,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Обновляет статус intake_log на missed."""
        from app.handlers.group import verify_no_callback

        # Создаём intake_log
        await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=1,
            status="pending_review",
            video_file_id="test_video",
        )

        callback = mock_callback(
            data=f"verify_no_{test_active_course['id']}_1",
            user_id=test_manager["telegram_id"],
        )

        await verify_no_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            manager_service=manager_service,
            intake_logs_service=intake_logs_service,
            topic_service=topic_service,
            bot=bot,
            supabase=supabase,
        )

        # Проверяем статус в intake_logs
        log = await supabase.table("intake_logs") \
            .select("status, verified_by") \
            .eq("course_id", test_active_course["id"]) \
            .eq("day", 1) \
            .single() \
            .execute()

        assert log.data["status"] == "missed"
        assert log.data["verified_by"] == "manager"


class TestVerifyOkCallback:
    """Тесты для verify_ok_callback."""

    @pytest.mark.asyncio
    async def test_verify_ok_updates_progress(
        self,
        supabase,
        mock_bot,
        test_user_with_telegram,
        test_active_course,
        intake_logs_service,
    ):
        """Менеджер принимает видео — прогресс обновляется."""
        from app.handlers.group import verify_ok_callback
        from app.services.courses import CourseService
        from app.services.users import UserService
        from app.services.managers import ManagerService
        from app.services.topic import TopicService
        from unittest.mock import AsyncMock, MagicMock

        # Создаём intake_log для day=1
        await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=1,
            status="pending_review",
            video_file_id="test_video",
        )

        course_service = CourseService(supabase)
        user_service = UserService(supabase)
        manager_service = ManagerService(supabase)
        topic_service = TopicService(mock_bot, -1001234567890)

        callback = MagicMock()
        callback.data = f"verify_ok_{test_active_course['id']}_1"
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.edit_text = AsyncMock()

        await verify_ok_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            manager_service=manager_service,
            intake_logs_service=intake_logs_service,
            topic_service=topic_service,
        )

        # Проверяем что current_day увеличился
        updated = await supabase.table("courses") \
            .select("current_day, status") \
            .eq("id", test_active_course["id"]) \
            .single() \
            .execute()
        assert updated.data["current_day"] == 2
        assert updated.data["status"] == "active"

        # Проверяем что intake_log обновлён
        log = await intake_logs_service.get_by_course_and_day(test_active_course["id"], 1)
        assert log["status"] == "taken"
        assert log["verified_by"] == "manager"

        # Cleanup
        await supabase.table("intake_logs").delete().eq("course_id", test_active_course["id"]).execute()

    @pytest.mark.asyncio
    async def test_verify_ok_last_day_closes_topic(
        self,
        supabase,
        mock_bot,
        test_user_with_telegram,
        test_manager,
        intake_logs_service,
    ):
        """Менеджер принимает видео последнего дня — топик закрывается."""
        from app.handlers.group import verify_ok_callback
        from app.services.courses import CourseService
        from app.services.users import UserService
        from app.services.managers import ManagerService
        from app.services.topic import TopicService
        from unittest.mock import AsyncMock, MagicMock

        # Создаём курс на последнем дне (day=21, total_days=21)
        course_result = await supabase.table("courses").insert({
            "user_id": test_user_with_telegram["id"],
            "invite_code": "test_last_day_verify",
            "status": "active",
            "current_day": 21,
            "total_days": 21,
            "cycle_day": 1,
            "intake_time": "12:00",
            "start_date": "2026-01-01",
        }).execute()
        course_id = course_result.data[0]["id"]

        # Создаём intake_log для day=21
        await intake_logs_service.create(
            course_id=course_id,
            day=21,
            status="pending_review",
            video_file_id="test_video",
        )

        course_service = CourseService(supabase)
        user_service = UserService(supabase)
        manager_service = ManagerService(supabase)
        topic_service = TopicService(mock_bot, -1001234567890)

        callback = MagicMock()
        callback.data = f"verify_ok_{course_id}_21"
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.edit_text = AsyncMock()

        await verify_ok_callback(
            callback=callback,
            course_service=course_service,
            user_service=user_service,
            manager_service=manager_service,
            intake_logs_service=intake_logs_service,
            topic_service=topic_service,
        )

        # Проверяем что курс завершён
        updated = await supabase.table("courses") \
            .select("status, current_day") \
            .eq("id", course_id) \
            .single() \
            .execute()
        assert updated.data["status"] == "completed"
        assert updated.data["current_day"] == 21

        # Проверяем что топик закрыт (close_forum_topic вызван)
        # У test_user_with_telegram должен быть topic_id
        if test_user_with_telegram.get("topic_id"):
            mock_bot.close_forum_topic.assert_called()

        # Cleanup
        await supabase.table("intake_logs").delete().eq("course_id", course_id).execute()
        await supabase.table("courses").delete().eq("id", course_id).execute()