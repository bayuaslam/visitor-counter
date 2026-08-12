# Production Migration

SmartLab now uses a split **cloud server + lab edge PC** architecture. The CCTV RTSP stream and YOLO inference stay inside the lab LAN; only visitor events, occupancy, heartbeat, and device commands cross the internet over authenticated HTTPS.

## Final architecture

```text
CCTV (private RTSP)
        |
        v
Windows PC Lab
  visitor_counter.py -> lab_visitors.db (local buffer)
  edge_sync_agent.py -- HTTPS + device token --> Online API
                                                |
                                                +--> PostgreSQL
                                                +--> persistent uploads
                                                +--> React frontend
```

## Phase status

- [x] Phase 1 — clean repository, remove runtime telemetry/backups/stale build output, harden ignores.
- [x] Phase 2 — separate cloud API from the local CCTV/YOLO process.
- [x] Phase 3 — add PostgreSQL configuration and SQLite-to-PostgreSQL migration utility.
- [x] Phase 4 — add authenticated, retry-safe edge event sync, heartbeat, deduplication, and reset commands.
- [x] Phase 5 — verified UII email registration, laboran/student login UI, guest restrictions, secure cookies, host/CORS/security policy, and rate limits.
- [x] Phase 6 — Docker production image, PostgreSQL, Caddy HTTPS reverse proxy, persistent uploads, health checks, backup/restore tooling, tests, dependency audits, and CI.

## Server deployment

Requirements: a Linux server/VPS, Docker Engine + Docker Compose, a DNS hostname pointing to the server, and SMTP credentials that can send verification emails.

1. Check out this branch on the server.
2. Copy `.env.production.example` to `.env`.
3. Generate secrets with `python scripts/generate_production_secrets.py` and copy the generated values into `.env`.
4. Set `LABHUB_DOMAIN` and SMTP values in `.env`.
5. Start the stack:

```sh
docker compose up -d --build
```

6. Check it:

```sh
docker compose ps
docker compose logs --tail=100 app
curl -fsS https://YOUR_DOMAIN/api/health
```

Caddy obtains and renews TLS automatically when DNS and ports 80/443 are reachable.

## Existing SQLite data migration

Before switching users to the online server, copy `labhub.db` and `lab_visitors.db` from the old PC to a protected migration working directory. Point `DATABASE_URL` at the target PostgreSQL database and run a dry-run first:

```sh
python scripts/migrate_sqlite_to_postgres.py \
  --labhub-db /secure/path/labhub.db \
  --visitors-db /secure/path/lab_visitors.db \
  --dry-run
```

Then repeat without `--dry-run`. The importer is idempotent for normal reruns and preserves legacy request/equipment identifiers. If old `storage/uploads` contains user files, copy those files separately into the production upload volume after the database migration.

## Lab edge PC

The edge PC keeps the existing CCTV and YOLO workload. Its `.env` must contain the same `LABHUB_EDGE_DEVICE_ID` and `LABHUB_EDGE_DEVICE_TOKEN` used by the server plus the production URL:

```env
LABHUB_SERVER_URL=https://YOUR_DOMAIN
LABHUB_EDGE_DEVICE_ID=lab-robotika-01
LABHUB_EDGE_DEVICE_TOKEN=YOUR_RANDOM_DEVICE_TOKEN
```

Keep the existing CCTV settings/DPAPI credential locally. Then, from an elevated PowerShell opened under the Windows account that owns the camera credential:

```powershell
cd C:\visitor-counter
.\install-smartlab-network-task.ps1
.\install-smartlab-edge-tasks.ps1
```

The network repair task may run as SYSTEM. The visitor counter and sync agent deliberately run as the interactive Windows user so the DPAPI camera credential remains decryptable.

If internet access is interrupted, visitor events continue accumulating in local SQLite. `edge_sync_agent.py` retries automatically and the cloud endpoint deduplicates event IDs.

## Backups

Create a database + uploads backup:

```sh
sh scripts/backup_production.sh
```

Restore one backup directory:

```sh
sh scripts/restore_production.sh backups/YYYYMMDDTHHMMSSZ
```

Copy backup directories off the production server as part of the actual backup policy; a backup stored only on the same host is not sufficient disaster recovery.

## Production safety rules

- Never expose CCTV RTSP or port 554 to the public internet.
- Never commit `.env`, CCTV credentials, session secrets, device tokens, databases, uploads, captured frames, heartbeats, runtime CSVs, or logs.
- Production startup deliberately fails if PostgreSQL, secure cookies, host restrictions, SMTP, session secret, admin hash, or edge token are not configured.
- Keep the web/API and edge PC clocks synchronized; visitor events are normalized to UTC and dashboard day boundaries use WIB (`UTC+7`).
- Run CI and dependency audits before merging or deploying changes.
