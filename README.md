# SmartLab Visitor Counter & LabHub

SmartLab combines a realtime CCTV/YOLO visitor counter with a web portal for laboratory inventory and services.

## Production design

The system is intentionally split in two:

- **Lab edge PC (Windows):** private CCTV RTSP, YOLO tracking, `visitor_counter.py`, local SQLite buffer, `edge_sync_agent.py`.
- **Online server:** FastAPI + React, PostgreSQL, authentication, inventory, service requests, notifications, visitor dashboard, persistent uploads.

The CCTV stream is never required to leave the lab network. The edge PC sends only structured event/heartbeat data to the server over authenticated HTTPS.

## Repository map

```text
api_server.py                    online FastAPI application
labhub/                          auth, database, models, repositories
frontend/                        React/Vite UI
visitor_counter.py               local YOLO counter (lab PC)
edge_sync_agent.py               local-to-cloud retry/dedup sync
line_config.json                 calibrated counting line
requirements-server.txt          online server dependencies
requirements-edge.txt            lab PC computer-vision dependencies
Dockerfile                       production app image
docker-compose.yml               app + PostgreSQL + Caddy HTTPS
Caddyfile                        reverse proxy/TLS
scripts/                         migration, secrets, backup/restore
tests/                           API/auth/edge regression tests
MIGRATION.md                     deployment + migration runbook
```

## Development

Server:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: . .venv/bin/activate
pip install -r requirements-server.txt -r requirements-dev.txt
cp .env.example .env             # Windows: copy .env.example .env
uvicorn api_server:app --reload
```

Frontend:

```sh
cd frontend
npm ci
npm run dev
```

Tests:

```sh
python -m compileall -q api_server.py edge_sync_agent.py labhub scripts tests
pytest -q
cd frontend && npm ci && npm run build
```

## Production

Use `MIGRATION.md`. Production is designed for Docker Compose with PostgreSQL and Caddy HTTPS. Before deployment, generate unique secrets, configure SMTP for UII email verification, migrate existing SQLite data, and configure the lab edge PC with the matching device ID/token.

## Security model

- student account creation requires a verification code delivered to an `@uii.ac.id` address;
- laboran actions require an authenticated admin session;
- guests may browse public information but cannot create service requests;
- edge ingestion requires a dedicated device ID + random device token;
- production cookies are secure/HTTP-only and startup fails closed when required security settings are missing;
- runtime databases, uploads, logs, CCTV credentials, `.env`, captured frames, and telemetry are excluded from Git.

Do not publish RTSP/port 554 to the internet. Keep the camera and YOLO workload on the lab edge PC.
