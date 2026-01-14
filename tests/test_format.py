"""Тесты для утилит форматирования."""
from app.utils.format import short_name


class TestShortName:
    """Тесты для функции short_name."""

    def test_full_name(self):
        """Сокращает полное ФИО."""
        assert short_name("Иванова Мария Петровна") == "Иванова М. П."

    def test_empty_string(self):
        """Пустая строка."""
        assert short_name("") == ""