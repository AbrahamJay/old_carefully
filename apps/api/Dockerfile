FROM python:3.12-slim

# tzdata：app/core/time.py 用 ZoneInfo("Asia/Shanghai")，slim 镜像默认没有时区库
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
# 启动迁移与运维脚本依赖这些文件，缺了会直接导致 AUTO_MIGRATE 启动失败
COPY alembic.ini ./
COPY migrations ./migrations
COPY sql ./sql
COPY scripts ./scripts

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
