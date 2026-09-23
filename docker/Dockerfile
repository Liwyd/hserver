FROM python:3.11-alpine

ENV TZ=UTC
ENV PYTHONUNBUFFERED=1
ENV UV_VERSION=0.4.18

RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    postgresql-dev \
    && pip install --no-cache-dir uv==$UV_VERSION

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN uv run alembic upgrade head

CMD ["uv", "run", "python", "-m", "bot.main"]