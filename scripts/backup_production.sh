#!/bin/sh
set -eu

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${1:-backups/$STAMP}"
mkdir -p "$DEST"

echo "[1/3] Backup PostgreSQL..."
docker compose exec -T db pg_dump -U labhub -d labhub -Fc > "$DEST/labhub.dump"

echo "[2/3] Backup uploads..."
mkdir -p "$DEST/uploads"
docker compose cp app:/data/uploads/. "$DEST/uploads/"

echo "[3/3] Checksums..."
(
  cd "$DEST"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)

echo "Backup selesai: $DEST"
