FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS server
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN groupadd --system labhub && useradd --system --gid labhub --home /app labhub

COPY requirements-server.txt ./
RUN pip install --upgrade pip && pip install -r requirements-server.txt

COPY api_server.py ./
COPY labhub ./labhub
COPY scripts/migrate_sqlite_to_postgres.py ./scripts/migrate_sqlite_to_postgres.py
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

RUN mkdir -p /app/storage/uploads /app/scripts && chown -R labhub:labhub /app
USER labhub

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()" || exit 1

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
