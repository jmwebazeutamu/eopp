# Youth Employment Platform — backend image
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq for psycopg, curl for the container healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ /app/requirements/
ARG REQUIREMENTS=development
RUN pip install --upgrade pip && pip install -r /app/requirements/${REQUIREMENTS}.txt

COPY . /app/

# Non-root: the pilot is a government-owned deployment and Sprint 10 includes a
# security review. Cheaper to start here than to retrofit.
RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
