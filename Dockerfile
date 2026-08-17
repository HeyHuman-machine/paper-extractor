FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 先只复制依赖清单，让依赖层可以被 Docker 缓存。
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 业务代码在运行时使用容器内的 /app 根目录。
COPY app ./app
COPY ui ./ui
COPY scripts ./scripts
COPY README.md ./README.md

RUN mkdir -p data/inbox data/output storage logs

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000 8501

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
