# Backend image (API and, from stage 5, workers). Build context: ./backend
#
# Stage 1 installs dependencies with uv; stage 2 copies only the virtualenv and the code,
# and runs as a non-root user.

ARG PYTHON_IMAGE=docker.io/library/python:3.12-slim

FROM ${PYTHON_IMAGE} AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first: this layer is cached until pyproject.toml/uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM ${PYTHON_IMAGE} AS runtime
# libmagic1: detects the real type of uploaded files (python-magic, stage 4).
RUN apt-get update \
 && apt-get install --yes --no-install-recommends libmagic1 \
 && rm -rf /var/lib/apt/lists/*
# /data is the mount point of the documents volume: a new volume copies this owner,
# so the `app` user can write uploads there.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data/documents /data/tmp \
 && chown -R app:app /data \
 && chmod 700 /data/documents /data/tmp
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

# Worker image (stage 5): the same app plus Tesseract's Spanish and English data for OCR.
# PyMuPDF has the Tesseract engine built in; it only needs the language files.
FROM runtime AS worker
USER root
RUN apt-get update \
 && apt-get install --yes --no-install-recommends tesseract-ocr-spa tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/* \
 && ls /usr/share/tesseract-ocr/*/tessdata/spa.traineddata
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata
USER app
HEALTHCHECK NONE
CMD ["celery", "-A", "app.worker", "worker", "--concurrency=1", "--loglevel=INFO"]
