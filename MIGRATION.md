# Production Migration

This branch prepares SmartLab for an online deployment without moving direct CCTV/YOLO processing into the public server.

## Target architecture

- **Edge PC in the lab**: CCTV RTSP, YOLO tracking, local retry buffer, line configuration.
- **Online server**: FastAPI, React frontend, authentication, inventory, service requests, notifications, visitor API.
- **Production database**: PostgreSQL.
- **Uploaded files**: persistent/object storage, not ephemeral application disk.

The CCTV RTSP endpoint must remain private on the lab network. The edge PC should push visitor events and heartbeat data to the online API over authenticated HTTPS.

## Migration status

- [x] Create isolated `production-migration` branch.
- [x] Remove runtime telemetry, backup source files, stale frontend build artifacts, and local launcher binary from the migration branch.
- [x] Harden `.gitignore` and add `.env.example`.
- [ ] Split edge counter code from server code.
- [ ] Replace shared local-file heartbeat/reset communication with an authenticated device API.
- [ ] Migrate application and visitor data from SQLite to PostgreSQL.
- [ ] Add verified UII user authentication and production admin login UI.
- [ ] Enable secure cookies, production CORS policy, and rate limiting.
- [ ] Move request uploads to persistent/object storage.
- [ ] Add Docker/production process configuration, health checks, backups, and deployment documentation.

## Important

Do **not** deploy `visitor_counter.py` to a public cloud server as the CCTV processor. It currently depends on the lab LAN, Windows networking/DPAPI behavior, and local RTSP access.

Do **not** commit `.env`, CCTV credentials, session secrets, SQLite databases, uploads, captured images, heartbeats, or runtime CSV/log files.
