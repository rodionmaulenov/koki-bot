"""Тесты для utils/logger.py."""

from app.utils.logger import log_error, log_gemini_call, log_gemini_result


class TestLogError:
    """Тесты для log_error."""

    def test_outputs_error(self, capsys):
        """Выводит сообщение об ошибке."""
        log_error("Test error message")
        captured = capsys.readouterr()
        assert "ERROR" in captured.out
        assert "Test error message" in captured.out

    def test_has_emoji(self, capsys):
        """Содержит emoji."""
        log_error("test")
        captured = capsys.readouterr()
        assert "❌" in captured.out


class TestLogGeminiCall:
    """Тесты для log_gemini_call."""

    def test_outputs_action(self, capsys):
        """Выводит action."""
        log_gemini_call("verify_video")
        captured = capsys.readouterr()
        assert "GEMINI" in captured.out
        assert "verify_video" in captured.out

    def test_with_details(self, capsys):
        """Выводит детали."""
        log_gemini_call("download", "file_id=abc123")
        captured = capsys.readouterr()
        assert "download" in captured.out
        assert "file_id=abc123" in captured.out

    def test_has_emoji(self, capsys):
        """Содержит emoji."""
        log_gemini_call("test")
        captured = capsys.readouterr()
        assert "👁️" in captured.out


class TestLogGeminiResult:
    """Тесты для log_gemini_result."""

    def test_confirmed_status(self, capsys):
        """Выводит confirmed результат."""
        log_gemini_result(True, 95, "confirmed")
        captured = capsys.readouterr()
        assert "✅" in captured.out
        assert "pill=True" in captured.out
        assert "confidence=95%" in captured.out
        assert "status=confirmed" in captured.out

    def test_pending_status(self, capsys):
        """Выводит pending результат."""
        log_gemini_result(False, 50, "pending")
        captured = capsys.readouterr()
        assert "⏳" in captured.out
        assert "pill=False" in captured.out

    def test_rejected_status(self, capsys):
        """Выводит rejected результат."""
        log_gemini_result(False, 20, "rejected")
        captured = capsys.readouterr()
        assert "❌" in captured.out