# =============================================================================
# Malika Bot — Dockerfile
# =============================================================================

FROM python:3.13-slim

# Не буферизовать stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Устанавливаем uv (быстрый пакетный менеджер)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Копируем файлы зависимостей
COPY pyproject.toml uv.lock ./

# Устанавливаем зависимости
RUN uv sync --frozen --no-dev

# Копируем код приложения
COPY app/ ./app/
COPY run_polling.py ./

# Создаём директорию для временных файлов (видео от Gemini)
RUN mkdir -p /app/temp

# По умолчанию запускаем бота
CMD ["uv", "run", "python", "run_polling.py"]