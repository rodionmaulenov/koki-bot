"""Кастомный логгер с цветами."""

from rich.console import Console

console = Console()


def log_user_message(telegram_id: int, text: str):
    """Входящее сообщение от пользователя."""
    console.print(f"📩 [bold cyan]USER[/] ({telegram_id}): {text}")


def log_bot_reply(telegram_id: int, text: str):
    """Ответ бота."""
    console.print(f"📤 [bold green]BOT[/] ({telegram_id}): {text[:100]}...")


def log_db_save(table: str, action: str):
    """Сохранение в БД."""
    console.print(f"💾 [bold yellow]DB[/] {table}: {action}")


def log_ai_call(model: str, prompt_type: str):
    """Вызов AI модели."""
    console.print(f"🤖 [bold magenta]AI[/] {model}: {prompt_type}")


def log_user_prompt(prompt: str):
    """User prompt для AI — полный текст."""
    console.print(f"💬 [bold cyan]USER PROMPT[/]\n{prompt}")


def log_ai_response(response: str):
    """Ответ от AI."""
    console.print(f"✨ [bold green]AI RESPONSE[/]\n{response}")


def log_context(message_count: int, history: str, summary: str = None):
    """Информация о контексте."""
    console.print(f"📋 [bold blue]CONTEXT[/] {message_count} messages")

    if summary:
        console.print(f"   [yellow]SUMMARY:[/] {summary}")

    if history:
        console.print(f"   [dim]HISTORY:[/]\n{history}")


def log_error(message: str):
    """Ошибка."""
    console.print(f"❌ [bold red]ERROR[/] {message}")


def log_status(user_status: str, action: str = None):
    """Статус пользователя."""
    if action:
        console.print(f"👤 [bold white]STATUS[/] {user_status} → {action}")
    else:
        console.print(f"👤 [bold white]STATUS[/] {user_status}")


def log_rag_results(filter_category: str | None, examples: list[dict]):
    """Результаты RAG поиска с полными примерами."""
    cat = filter_category or "ALL"
    console.print(f"🔍 [bold blue]RAG[/] \\[{cat}\\]: {len(examples)} examples")

    for i, ex in enumerate(examples, 1):
        text = ex.get("text") or ""  # Пустая строка вместо None
        answer = ex.get("answer", "")
        similarity = ex.get("similarity")

        if similarity is not None:
            sim_str = f"({similarity:.2f})"
        else:
            sim_str = "(1.00)"

        # Выводим text только если он есть
        if text:
            console.print(f"   {i}. [dim]{sim_str}[/] {text}")
        else:
            console.print(f"   {i}. [dim]{sim_str}[/] ")

        if answer:
            short_answer = answer[:50] + "..." if len(answer) > 50 else answer
            console.print(f"      → {short_answer}")


def log_gemini_call(action: str, details: str = ""):
    """Вызов Gemini для проверки видео."""
    if details:
        console.print(f"👁️ [bold cyan]GEMINI[/] {action}: {details}")
    else:
        console.print(f"👁️ [bold cyan]GEMINI[/] {action}")


def log_gemini_result(is_taking_pill: bool, confidence: int, status: str):
    """Результат проверки видео."""
    emoji = "✅" if status == "confirmed" else "⏳" if status == "pending" else "❌"
    console.print(
        f"👁️ [bold cyan]GEMINI RESULT[/] {emoji} pill={is_taking_pill}, confidence={confidence}%, status={status}")


def log_reminder_sent(telegram_id: int, reminder_type: str):
    """Напоминание отправлено."""
    console.print(f"🔔 [bold green]REMINDER[/] {reminder_type} sent to {telegram_id}")


def log_reminder_failed(telegram_id: int, reminder_type: str, error: str = ""):
    """Напоминание не отправлено."""
    if error:
        console.print(f"🔕 [bold red]REMINDER[/] {reminder_type} failed for {telegram_id}: {error}")
    else:
        console.print(
            f"🔕 [bold yellow]REMINDER[/] {reminder_type} skipped for {telegram_id} (no business_connection_id)")


def log_alert_sent(telegram_id: int, category: str):
    """Логирует успешную отправку alert."""
    print(f"🚨 ALERT {category} sent to {telegram_id}")


def log_alert_failed(telegram_id: int, category: str, reason: str = "no business_connection_id"):
    """Логирует неудачную отправку alert."""
    print(f"⚠️ ALERT {category} failed for {telegram_id}: {reason}")


def log_refusal_sent(telegram_id: int, category: str):
    """Логирует успешное снятие с программы."""
    print(f"🚫 REFUSAL {category} sent to {telegram_id}")


def log_refusal_failed(telegram_id: int, category: str, reason: str = "unknown"):
    """Логирует неудачное снятие с программы."""
    print(f"⚠️ REFUSAL {category} failed for {telegram_id}: {reason}")
