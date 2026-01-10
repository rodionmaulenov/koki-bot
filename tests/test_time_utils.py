"""Тесты для time_utils."""
from datetime import datetime

from app.utils.time_utils import (
    get_tashkent_now,
    format_date,
    is_too_early,
    is_created_today,
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


class TestParseTimeString:
    """Тесты для parse_time_string."""

    def test_parses_hour_only(self):
        """Парсит только час."""
        from app.utils.time_utils import parse_time_string
        from datetime import time

        result = parse_time_string("15")
        assert result == time(15, 0)

    def test_parses_hour_minute(self):
        """Парсит час и минуты."""
        from app.utils.time_utils import parse_time_string
        from datetime import time

        result = parse_time_string("15:30")
        assert result == time(15, 30)

    def test_parses_morning_words(self):
        """Парсит словесные варианты утра."""
        from app.utils.time_utils import parse_time_string
        from datetime import time

        assert parse_time_string("morning") == time(9, 0)
        assert parse_time_string("утром") == time(9, 0)
        assert parse_time_string("утро") == time(9, 0)

    def test_parses_evening_words(self):
        """Парсит словесные варианты вечера."""
        from app.utils.time_utils import parse_time_string
        from datetime import time

        assert parse_time_string("вечером") == time(19, 0)
        assert parse_time_string("evening") == time(19, 0)

    def test_parses_day_words(self):
        """Парсит словесные варианты дня."""
        from app.utils.time_utils import parse_time_string
        from datetime import time

        assert parse_time_string("днём") == time(14, 0)
        assert parse_time_string("день") == time(14, 0)

    def test_empty_string_returns_none(self):
        """Пустая строка возвращает None."""
        from app.utils.time_utils import parse_time_string

        assert parse_time_string("") is None
        assert parse_time_string(None) is None

    def test_invalid_returns_none(self):
        """Невалидный формат возвращает None."""
        from app.utils.time_utils import parse_time_string

        assert parse_time_string("abc") is None
        assert parse_time_string("25:00") is None

    def test_strips_extra_text(self):
        """Убирает лишний текст."""
        from app.utils.time_utils import parse_time_string
        from datetime import time

        result = parse_time_string("в 15 часов")
        assert result == time(15, 0)


class TestIsTimePassed:
    """Тесты для is_time_passed."""

    def test_time_passed(self):
        """Время прошло."""
        from unittest.mock import patch
        from datetime import datetime, time
        import pytz

        fixed_time = datetime(2026, 1, 10, 15, 30, 0, tzinfo=pytz.timezone("Asia/Tashkent"))

        with patch("app.utils.time_utils.get_tashkent_now", return_value=fixed_time):
            from app.utils.time_utils import is_time_passed
            assert is_time_passed(time(14, 0)) is True
            assert is_time_passed(time(15, 0)) is True

    def test_time_not_passed(self):
        """Время ещё не прошло."""
        from unittest.mock import patch
        from datetime import datetime, time
        import pytz

        fixed_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=pytz.timezone("Asia/Tashkent"))

        with patch("app.utils.time_utils.get_tashkent_now", return_value=fixed_time):
            from app.utils.time_utils import is_time_passed
            assert is_time_passed(time(15, 0)) is False


class TestCalculateDelayMinutes:
    """Тесты для calculate_delay_minutes."""

    def test_calculates_delay(self):
        """Вычисляет опоздание."""
        from app.utils.time_utils import calculate_delay_minutes

        assert calculate_delay_minutes("12:00", "14:30") == 150
        assert calculate_delay_minutes("12:00", "12:30") == 30

    def test_no_delay_on_time(self):
        """Нет опоздания если вовремя."""
        from app.utils.time_utils import calculate_delay_minutes

        assert calculate_delay_minutes("12:00", "12:00") == 0

    def test_no_delay_if_early(self):
        """Нет опоздания если раньше."""
        from app.utils.time_utils import calculate_delay_minutes

        assert calculate_delay_minutes("12:00", "11:30") == 0

    def test_handles_seconds_format(self):
        """Обрабатывает формат с секундами."""
        from app.utils.time_utils import calculate_delay_minutes

        assert calculate_delay_minutes("12:00:00", "14:30:00") == 150

    def test_handles_invalid_input(self):
        """Обрабатывает невалидный ввод."""
        from app.utils.time_utils import calculate_delay_minutes

        assert calculate_delay_minutes("invalid", "12:00") == 0
        assert calculate_delay_minutes(None, "12:00") == 0


class TestCalculateTimeRangeBefore:
    """Тесты для calculate_time_range_before."""

    def test_calculates_range(self):
        """Вычисляет диапазон в будущем."""
        from unittest.mock import patch
        from datetime import datetime
        import pytz

        fixed_time = datetime(2026, 1, 10, 11, 0, 0, tzinfo=pytz.timezone("Asia/Tashkent"))

        with patch("app.utils.time_utils.get_tashkent_now", return_value=fixed_time):
            from app.utils.time_utils import calculate_time_range_before
            start, end = calculate_time_range_before(60)  # 60 минут вперёд
            assert "11:55" <= start <= "12:00"
            assert "12:00" <= end <= "12:05"


class TestCalculateTimeRangeAfter:
    """Тесты для calculate_time_range_after."""

    def test_calculates_range(self):
        """Вычисляет диапазон в прошлом."""
        from unittest.mock import patch
        from datetime import datetime
        import pytz

        fixed_time = datetime(2026, 1, 10, 12, 30, 0, tzinfo=pytz.timezone("Asia/Tashkent"))

        with patch("app.utils.time_utils.get_tashkent_now", return_value=fixed_time):
            from app.utils.time_utils import calculate_time_range_after
            start, end = calculate_time_range_after(30)  # 30 минут назад
            assert "11:55" <= start <= "12:00"
            assert "12:00" <= end <= "12:05"


class TestIsTooEarly:
    """Тесты для is_too_early."""

    def test_in_window_returns_false(self):
        """В окне приёма — можно отправлять."""
        from unittest.mock import patch
        from datetime import datetime
        import pytz

        # Фиксированное время: 12:00 Ташкент
        fixed_time = datetime(2026, 1, 10, 12, 0, 0, tzinfo=pytz.timezone("Asia/Tashkent"))

        with patch("app.utils.time_utils.get_tashkent_now", return_value=fixed_time):
            # intake_time = 12:05 (5 минут в будущем, но в окне 10 минут)
            too_early, window_start = is_too_early("12:05")
            assert too_early is False
            assert window_start == ""

    def test_too_early_returns_true(self):
        """Слишком рано — нельзя отправлять."""
        from unittest.mock import patch
        from datetime import datetime
        import pytz

        # Фиксированное время: 10:00 Ташкент
        fixed_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=pytz.timezone("Asia/Tashkent"))

        with patch("app.utils.time_utils.get_tashkent_now", return_value=fixed_time):
            # intake_time = 10:30 (30 минут в будущем)
            too_early, window_start = is_too_early("10:30")
            assert too_early is True
            assert window_start == "10:20"

    def test_window_start_format(self):
        """window_start в формате HH:MM."""
        from unittest.mock import patch
        from datetime import datetime
        import pytz

        # Фиксированное время: 10:00 Ташкент
        fixed_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=pytz.timezone("Asia/Tashkent"))

        with patch("app.utils.time_utils.get_tashkent_now", return_value=fixed_time):
            _, window_start = is_too_early("10:30")
            assert ":" in window_start
            assert len(window_start) == 5


class TestIsCreatedToday:
    """Тесты для is_created_today."""

    def test_created_today_utc_morning(self):
        """Создано сегодня утром UTC — сегодня по Ташкенту."""
        from unittest.mock import patch
        from datetime import datetime
        import pytz

        # Ташкент: 10 января 2026, 10:00 (UTC: 05:00)
        fixed_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=pytz.timezone("Asia/Tashkent"))

        with patch("app.utils.time_utils.get_tashkent_now", return_value=fixed_time):
            # Создано 10 января в 05:00 UTC = 10:00 Ташкент
            result = is_created_today("2026-01-10T05:00:00Z")
            assert result is True

    def test_created_yesterday_utc_evening(self):
        """Создано вчера вечером UTC — вчера по Ташкенту."""
        from unittest.mock import patch
        from datetime import datetime
        import pytz

        # Ташкент: 10 января 2026, 10:00
        fixed_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=pytz.timezone("Asia/Tashkent"))

        with patch("app.utils.time_utils.get_tashkent_now", return_value=fixed_time):
            # Создано 9 января в 15:00 UTC = 20:00 Ташкент 9 января
            result = is_created_today("2026-01-09T15:00:00Z")
            assert result is False

    def test_created_late_utc_same_day_tashkent(self):
        """Создано поздно вечером UTC — тот же день по Ташкенту."""
        from unittest.mock import patch
        from datetime import datetime
        import pytz

        # Ташкент: 11 января 2026, 01:30 (после полуночи)
        fixed_time = datetime(2026, 1, 11, 1, 30, 0, tzinfo=pytz.timezone("Asia/Tashkent"))

        with patch("app.utils.time_utils.get_tashkent_now", return_value=fixed_time):
            # Создано 10 января в 20:00 UTC = 11 января 01:00 Ташкент
            result = is_created_today("2026-01-10T20:00:00Z")
            assert result is True

    def test_timezone_boundary_case(self):
        """Граничный случай: UTC вечер = Ташкент следующий день."""
        from unittest.mock import patch
        from datetime import datetime
        import pytz

        # Ташкент: 11 января 2026, 10:00
        fixed_time = datetime(2026, 1, 11, 10, 0, 0, tzinfo=pytz.timezone("Asia/Tashkent"))

        with patch("app.utils.time_utils.get_tashkent_now", return_value=fixed_time):
            # Создано 10 января в 20:00 UTC = 11 января 01:00 Ташкент — это сегодня!
            result = is_created_today("2026-01-10T20:00:00Z")
            assert result is True

            # Создано 10 января в 15:00 UTC = 10 января 20:00 Ташкент — это вчера
            result = is_created_today("2026-01-10T15:00:00Z")
            assert result is False

    def test_empty_string(self):
        """Пустая строка возвращает False."""
        result = is_created_today("")
        assert result is False

    def test_none_like_empty(self):
        """None-подобное значение возвращает False."""
        result = is_created_today("")
        assert result is False

    def test_without_z_suffix(self):
        """Дата без Z суффикса (с +00:00)."""
        from unittest.mock import patch
        from datetime import datetime
        import pytz

        fixed_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=pytz.timezone("Asia/Tashkent"))

        with patch("app.utils.time_utils.get_tashkent_now", return_value=fixed_time):
            result = is_created_today("2026-01-10T05:00:00+00:00")
            assert result is True