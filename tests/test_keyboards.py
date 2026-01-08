"""Тесты для keyboards."""
import pytest
from freezegun import freeze_time

from app.keyboards import (
    cycle_day_keyboard,
    time_keyboard,
    time_keyboard_today,
    understand_button,
)


class TestUnderstandButton:
    """Тесты для understand_button."""

    def test_returns_markup(self):
        """Возвращает InlineKeyboardMarkup."""
        result = understand_button()
        assert result is not None
        assert len(result.inline_keyboard) == 1

    def test_button_text(self):
        """Текст кнопки."""
        result = understand_button()
        button = result.inline_keyboard[0][0]
        assert button.text == "Понятно ✓"

    def test_callback_data(self):
        """Callback data."""
        result = understand_button()
        button = result.inline_keyboard[0][0]
        assert button.callback_data == "understand"


class TestCycleDayKeyboard:
    """Тесты для cycle_day_keyboard."""

    def test_returns_markup(self):
        """Возвращает InlineKeyboardMarkup."""
        result = cycle_day_keyboard()
        assert result is not None

    def test_four_buttons(self):
        """4 кнопки (2 ряда по 2)."""
        result = cycle_day_keyboard()
        total_buttons = sum(len(row) for row in result.inline_keyboard)
        assert total_buttons == 4

    def test_two_rows(self):
        """2 ряда."""
        result = cycle_day_keyboard()
        assert len(result.inline_keyboard) == 2

    def test_callback_data_format(self):
        """Формат callback_data: cycle_1, cycle_2, etc."""
        result = cycle_day_keyboard()
        callbacks = []
        for row in result.inline_keyboard:
            for button in row:
                callbacks.append(button.callback_data)

        assert callbacks == ["cycle_1", "cycle_2", "cycle_3", "cycle_4"]


class TestTimeKeyboard:
    """Тесты для time_keyboard."""

    def test_returns_markup(self):
        """Возвращает InlineKeyboardMarkup."""
        result = time_keyboard()
        assert result is not None

    def test_time_range(self):
        """Время от 7:00 до 23:30."""
        result = time_keyboard()
        callbacks = []
        for row in result.inline_keyboard:
            for button in row:
                callbacks.append(button.callback_data)

        assert "time_7_00" in callbacks
        assert "time_23_30" in callbacks

    def test_half_hours_included(self):
        """Есть получасовые слоты."""
        result = time_keyboard()
        callbacks = []
        for row in result.inline_keyboard:
            for button in row:
                callbacks.append(button.callback_data)

        assert "time_12_00" in callbacks
        assert "time_12_30" in callbacks

    def test_four_buttons_per_row(self):
        """По 4 кнопки в ряду (кроме последнего)."""
        result = time_keyboard()
        for row in result.inline_keyboard[:-1]:
            assert len(row) == 4


class TestTimeKeyboardToday:
    """Тесты для time_keyboard_today."""

    def test_excludes_past_times(self, monkeypatch):
        """Исключает прошедшее время."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        fake_now = datetime(2026, 1, 5, 10, 0, tzinfo=ZoneInfo("Asia/Tashkent"))
        monkeypatch.setattr("app.keyboards.get_tashkent_now", lambda: fake_now)

        result = time_keyboard_today()
        callbacks = []
        for row in result.inline_keyboard:
            for button in row:
                callbacks.append(button.callback_data)

        assert "time_7_00" not in callbacks
        assert "time_10_00" not in callbacks

    def test_returns_none_when_too_late(self, monkeypatch):
        """Возвращает None когда слишком поздно."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        fake_now = datetime(2026, 1, 5, 23, 45, tzinfo=ZoneInfo("Asia/Tashkent"))
        monkeypatch.setattr("app.keyboards.get_tashkent_now", lambda: fake_now)

        result = time_keyboard_today()
        assert result is None

    def test_early_morning_starts_at_seven(self, monkeypatch):
        """Рано утром начинает с 7:00."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        fake_now = datetime(2026, 1, 5, 6, 0, tzinfo=ZoneInfo("Asia/Tashkent"))
        monkeypatch.setattr("app.keyboards.get_tashkent_now", lambda: fake_now)

        result = time_keyboard_today()
        first_callback = result.inline_keyboard[0][0].callback_data
        assert first_callback == "time_7_00"