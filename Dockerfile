# syntax=docker/dockerfile:1.4
# Multi-stage: builder compila pacotes com gcc; runtime não carrega ferramentas de build

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Cache do pip entre builds (BuildKit) — rebuild só quando requirements.txt muda
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install --no-warn-script-location -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Usuário não-root com UID/GID fixos (reproduzível entre builds)
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid 1001 --no-create-home --shell /bin/false appuser

WORKDIR /app

# Copiar pacotes compilados do builder (sem gcc)
COPY --from=builder /install /usr/local

# Copiar código com ownership já correto (evita chown -R)
COPY --chown=appuser:appgroup . .

ENV FLASK_APP=run.py
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
# Evita .pyc desnecessários em produção
ENV PYTHONDONTWRITEBYTECODE=1

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1

CMD ["/bin/sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 8 --worker-class gthread --worker-tmp-dir /dev/shm --timeout 120 --access-logfile - --error-logfile - run:app"]
