#!/bin/sh
set -eu

SOURCE="${1:-}"
if [ -z "$SOURCE" ] || [ ! -f "$SOURCE/labhub.dump" ]; then
  echo "Usage: $0 backups/YYYYMMDDTHHMMSSZ" >&2
  exit 2
fi

if [ -f "$SOURCE/SHA256SUMS" ]; then
  echo "[1/5] Verifikasi checksum..."
  (cd "$SOURCE" && sha256sum -c SHA256SUMS)
else
  echo "PERINGATAN: SHA256SUMS tidak ditemukan." >&2
fi

echo "[2/5] Hentikan aplikasi agar database konsisten saat restore..."
docker compose stop app

cleanup() {
  docker compose start app >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "[3/5] Restore PostgreSQL..."
cat "$SOURCE/labhub.dump" | docker compose exec -T db pg_restore -U labhub -d labhub --clean --if-exists --no-owner

echo "[4/5] Restore uploads..."
if [ -d "$SOURCE/uploads" ]; then
  docker compose exec -T app sh -c 'rm -rf /data/uploads/* && mkdir -p /data/uploads' || true
  docker compose cp "$SOURCE/uploads/." app:/data/uploads/
fi

echo "[5/5] Jalankan aplikasi kembali..."
docker compose start app
trap - EXIT INT TERM

echo "Restore selesai. Cek: docker compose ps && docker compose logs --tail=100 app"
