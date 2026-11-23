# OptiServe backend: FastAPI + in-process background jobs. One worker on purpose: the scheduler runs inside it,
# and more workers would run every job several times.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Runtime dependencies only (the test tools after "# tests" stay out of the image), plus the Postgres driver.
COPY requirements.txt requirements-postgres.txt ./
RUN sed '/^# tests/,$d' requirements.txt > /tmp/requirements.runtime.txt \
    && pip install -r /tmp/requirements.runtime.txt -r requirements-postgres.txt \
    && rm /tmp/requirements.runtime.txt

COPY app ./app
COPY scripts ./scripts

# Unprivileged user; /data holds the SQLite database (mount a volume there).
RUN useradd --system --uid 10001 --no-create-home --home-dir /app optiserve \
    && mkdir -p /data && chown optiserve:optiserve /data
USER optiserve

ENV DATABASE_URL=sqlite:////data/optiserve.db
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
