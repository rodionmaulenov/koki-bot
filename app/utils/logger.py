"""Простой логгер."""


def log_error(message: str):
    """Ошибка."""
    print(f"❌ ERROR: {message}")


def log_gemini_call(action: str, details: str = ""):
    """Вызов Gemini для проверки видео."""
    if details:
        print(f"👁️ GEMINI {action}: {details}")
    else:
        print(f"👁️ GEMINI {action}")


def log_gemini_result(is_taking_pill: bool, confidence: int, status: str):
    """Результат проверки видео."""
    emoji = "✅" if status == "confirmed" else "⏳" if status == "pending" else "❌"
    print(f"👁️ GEMINI RESULT {emoji} pill={is_taking_pill}, confidence={confidence}%, status={status}")