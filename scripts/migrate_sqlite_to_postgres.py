import argparse
import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from labhub.database import DATABASE_URL, SessionLocal, init_database
from labhub.models import CounterState, Equipment, LabSetting, Notification, ServiceRequest, StudentUser, VisitorEvent


WIB = timezone(timedelta(hours=7))


def parse_datetime(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def sqlite_rows(path: Path, table: str):
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            return []
        return [dict(row) for row in conn.execute(f'SELECT * FROM "{table}"').fetchall()]
    finally:
        conn.close()


def add_if_missing(session, model, key_name, key_value, values):
    if session.query(model).filter(getattr(model, key_name) == key_value).first():
        return False
    session.add(model(**values))
    return True


def migrate_labhub(session, source: Path):
    counts = {}

    rows = sqlite_rows(source, "equipment")
    counts["equipment"] = 0
    for row in rows:
        values = {key: row.get(key) for key in (
            "id", "asset_code", "name", "category", "quantity_total", "quantity_available",
            "condition", "location", "description", "photo_path"
        )}
        values["created_at"] = parse_datetime(row.get("created_at"))
        values["updated_at"] = parse_datetime(row.get("updated_at"))
        if add_if_missing(session, Equipment, "asset_code", row["asset_code"], values):
            counts["equipment"] += 1

    rows = sqlite_rows(source, "student_users")
    counts["student_users"] = 0
    for row in rows:
        values = {
            "id": row.get("id"),
            "email": row["email"],
            "password_hash": row["password_hash"],
            "created_at": parse_datetime(row.get("created_at")),
        }
        if add_if_missing(session, StudentUser, "email", row["email"], values):
            counts["student_users"] += 1

    rows = sqlite_rows(source, "lab_settings")
    counts["lab_settings"] = 0
    for row in rows:
        values = {
            "key": row["key"],
            "value": row["value"],
            "updated_at": parse_datetime(row.get("updated_at")),
        }
        if add_if_missing(session, LabSetting, "key", row["key"], values):
            counts["lab_settings"] += 1

    rows = sqlite_rows(source, "service_requests")
    counts["service_requests"] = 0
    for row in rows:
        values = {key: row.get(key) for key in (
            "id", "request_code", "request_type", "requester_name", "requester_id", "title",
            "description", "status", "equipment_id", "room_name", "quantity", "metadata_json",
            "file_path", "admin_note"
        )}
        for key in ("start_at", "end_at", "created_at", "updated_at"):
            values[key] = parse_datetime(row.get(key))
        if add_if_missing(session, ServiceRequest, "request_code", row["request_code"], values):
            counts["service_requests"] += 1

    rows = sqlite_rows(source, "notifications")
    counts["notifications"] = 0
    for row in rows:
        values = {key: row.get(key) for key in (
            "id", "recipient_role", "recipient_user_id", "kind", "title", "message", "request_id"
        )}
        values["read_at"] = parse_datetime(row.get("read_at"))
        values["created_at"] = parse_datetime(row.get("created_at"))
        if session.get(Notification, row["id"]) is None:
            session.add(Notification(**values))
            counts["notifications"] += 1

    return counts


def migrate_visitors(session, source: Path, device_id: str):
    rows = sqlite_rows(source, "visitor_events")
    migrated = 0
    for row in rows:
        stamp = parse_datetime(row["timestamp"])
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=WIB)
        stamp = stamp.astimezone(timezone.utc)
        fingerprint = hashlib.sha256(
            f"legacy:{device_id}:{row['id']}:{row['timestamp']}:{row.get('track_id')}:{row['direction']}".encode()
        ).hexdigest()[:40]
        if session.query(VisitorEvent.id).filter(VisitorEvent.event_uuid == fingerprint).first():
            continue
        session.add(VisitorEvent(
            event_uuid=fingerprint,
            device_id=device_id,
            occurred_at=stamp,
            track_id=row.get("track_id"),
            direction=row["direction"],
            occupancy_after=max(0, int(row["occupancy_after"])),
        ))
        migrated += 1

    state_rows = sqlite_rows(source, "counter_state")
    if state_rows:
        source_state = state_rows[0]
        stamp = parse_datetime(source_state.get("updated_at")) or datetime.now(WIB)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=WIB)
        stamp = stamp.astimezone(timezone.utc)
        state = session.get(CounterState, device_id)
        if state is None:
            state = CounterState(device_id=device_id)
            session.add(state)
        state.occupancy = max(0, int(source_state.get("occupancy", 0)))
        state.updated_at = stamp

    return migrated


def reset_postgres_sequences(session):
    if not DATABASE_URL.startswith("postgresql"):
        return
    for table in ("equipment", "student_users", "service_requests", "notifications"):
        session.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1), 1), true)"
        ))


def main():
    parser = argparse.ArgumentParser(description="Migrasikan database SmartLab SQLite ke database server.")
    parser.add_argument("--labhub-db", default="labhub.db")
    parser.add_argument("--visitors-db", default="lab_visitors.db")
    parser.add_argument("--device-id", default=os.getenv("LABHUB_EDGE_DEVICE_ID", "lab-robotika-01"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if DATABASE_URL.startswith("sqlite:"):
        raise SystemExit("DATABASE_URL masih SQLite. Arahkan ke PostgreSQL target sebelum migrasi.")

    init_database()
    with SessionLocal() as session:
        app_counts = migrate_labhub(session, Path(args.labhub_db))
        visitor_count = migrate_visitors(session, Path(args.visitors_db), args.device_id)
        reset_postgres_sequences(session)

        print("Rencana migrasi:")
        for name, count in app_counts.items():
            print(f"  {name}: {count}")
        print(f"  visitor_events: {visitor_count}")

        if args.dry_run:
            session.rollback()
            print("Dry-run selesai, tidak ada perubahan disimpan.")
        else:
            session.commit()
            print("Migrasi selesai dan sudah di-commit.")


if __name__ == "__main__":
    main()
