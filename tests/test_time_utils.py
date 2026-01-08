"""Тесты для time_utils."""
from datetime import datetime

from app.utils.time_utils import (
    get_tashkent_now,
    format_date,
    is_too_early,
    MONTHS,
)


class TestGetTashkentNow:
    """Тесты для get_tashkent_now."""

    def test_returns_datetime(self):
        """Возвращает datetime."""
        result = get_tashkent_now()
        assert isinstance(result, datetime)

    def test_has_timezone(self):
        """Имеет timezone."""
        result = get_tashkent_now()
        assert result.tzinfo is not None

    def test_timezone_name(self):
        """Правильная timezone."""
        result = get_tashkent_now()
        assert "Tashkent" in str(result.tzinfo)


class TestFormatDate:
    """Тесты для format_date."""

    def test_formats_date_correctly(self):
        """Форматирует дату правильно."""
        result = format_date("2026-01-06")
        assert result == "6 Янв 26"

    def test_different_months(self):
        """Разные месяцы."""
        assert format_date("2026-03-15") == "15 Мар 26"
        assert format_date("2026-12-01") == "1 Дек 26"

    def test_invalid_date_returns_original(self):
        """Невалидная дата возвращает исходную строку."""
        result = format_date("invalid")
        assert result == "invalid"

    def test_empty_string(self):
        """Пустая строка."""
        result = format_date("")
        assert result == ""

    def test_none_returns_none(self):
        """None возвращает None или строку."""
        result = format_date(None)
        assert result is None or result == ""


class TestMonthsDict:
    """Тесты для словаря месяцев."""

    def test_all_months_present(self):
        """Все 12 месяцев есть."""
        assert len(MONTHS) == 12

    def test_months_range(self):
        """Месяцы от 1 до 12."""
        for i in range(1, 13):
            assert i in MONTHS


class TestIsTooEarly:
    """Тесты для is_too_early."""

    def test_in_window_returns_false(self):
        """В окне приёма — можно отправлять."""
        now = get_tashkent_now()
        # intake_time = 5 минут назад (в окне)
        minutes = now.hour * 60 + now.minute - 5
        if minutes < 0:
            minutes += 24 * 60
        intake_time = f"{minutes // 60:02d}:{minutes % 60:02d}"

        too_early, window_start = is_too_early(intake_time)
        assert too_early is False
        assert window_start == ""

    def test_too_early_returns_true(self):
        """Слишком рано — нельзя отправлять."""
        now = get_tashkent_now()
        # intake_time = 30 минут в будущем (слишком рано)
        minutes = now.hour * 60 + now.minute + 30
        intake_time = f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"

        too_early, window_start = is_too_early(intake_time)
        assert too_early is True
        assert window_start != ""

    def test_window_start_format(self):
        """window_start в формате HH:MM."""
        now = get_tashkent_now()
        minutes = now.hour * 60 + now.minute + 30
        intake_time = f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"

        _, window_start = is_too_early(intake_time)
        assert ":" in window_start
        assert len(window_start) == 5