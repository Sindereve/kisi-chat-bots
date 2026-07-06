# uv + Python 3.14 (совпадает с .python-version / requires-python)
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

# Сначала только манифесты — слой с зависимостями кешируется, пока не менялся lock.
COPY pyproject.toml uv.lock README.md ./
# UV_HTTP_TIMEOUT: дефолтных 30с мало для тяжёлых колёс (tiktoken/pydantic-core) на медленной сети.
ENV UV_HTTP_TIMEOUT=180
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# Затем код бота.
COPY kiwi ./kiwi

# Состояние и лог — в volume, чтобы переживали пересоздание контейнера.
ENV DB_FILE=/data/state.db LOG_FILE=/data/bot.log
VOLUME /data

# ponytail: root в контейнере; non-root добавить, если появится bind-mount с чужими правами.
CMD ["uv", "run", "--no-sync", "python", "-m", "kiwi"]
