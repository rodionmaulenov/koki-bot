# Koki Bot

Telegram бот для 21/42-дневной программы приёма КОК (контрацептивов).

## Что делает

- **Менеджер** загружает документы девушки (паспорт, чек, карта) → OCR через Gemini Vision → генерация invite-ссылки
- **Девушка** проходит онбординг (5 шагов) → выбирает день цикла и время приёма
- **Ежедневно** девушка отправляет видео приёма таблетки → AI проверяет → менеджер подтверждает/отклоняет
- **Автоматика**: напоминания, страйки за опоздание, автоснятие, пересъёмка видео, апелляции
- **8 фоновых задач** каждые 5 минут: напоминания, дедлайны, автоснятие

## Tech Stack

- Python 3.13+, Aiogram 3.x, Dishka DI
- Supabase (PostgreSQL), Redis
- Google Gemini 2.5 Flash (видео-верификация, OCR)
- Docker, GitHub Actions (CI/CD)

## Запуск (development)

```bash
# Установить зависимости
uv sync

# Скопировать и заполнить .env
cp .env.example .env

# Запустить Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Запустить бота
uv run python main.py
```

## Запуск (production)

```bash
# На сервере
docker compose pull
docker compose up -d
```

Деплой автоматический: push в `main` → GitHub Actions → GHCR → SSH deploy.

## Структура

```
main.py              # Entry point (polling + scheduler)
handlers/            # Telegram handlers (onboarding, video, add, appeal, menu)
services/            # Business logic (video, add, ocr, gemini)
repositories/        # Supabase CRUD
workers/             # Scheduler + 8 periodic tasks
models/              # Pydantic models
keyboards/           # Inline keyboards
templates.py         # All UI texts
topic_access/        # TrackedBot, access control middleware
di/                  # Dishka DI provider
```

## Тесты

```bash
# Все тесты
uv run pytest tests/ -v

# Mock тесты (быстро, параллельно)
uv run pytest tests/ -v -n auto --ignore=tests/repositories
```
