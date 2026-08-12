import sqlite3
from datetime import datetime

import edge_sync_agent as edge


def create_local_db(path):
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE visitor_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_date TEXT NOT NULL,
                track_id INTEGER,
                direction TEXT NOT NULL,
                occupancy_after INTEGER NOT NULL
            );
            CREATE TABLE counter_state (
                id INTEGER PRIMARY KEY,
                occupancy INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO counter_state(id, occupancy, updated_at)
            VALUES(1, 2, '2026-08-12 10:00:00');
            """
        )
        today = datetime.now(edge.WIB).date().isoformat()
        conn.execute(
            "INSERT INTO visitor_events(timestamp, event_date, track_id, direction, occupancy_after) VALUES(?, ?, 1, 'IN', 1)",
            (f"{today} 10:00:00", today),
        )
        conn.execute(
            "INSERT INTO visitor_events(timestamp, event_date, track_id, direction, occupancy_after) VALUES(?, ?, 2, 'IN', 2)",
            (f"{today} 10:01:00", today),
        )
        conn.commit()
    finally:
        conn.close()


def test_reset_keeps_sqlite_sequence_and_clears_today(tmp_path, monkeypatch):
    db_file = tmp_path / "lab_visitors.db"
    create_local_db(db_file)
    monkeypatch.setattr(edge, "DB_FILE", db_file)

    assert edge.local_event_sequence() == 2
    edge.reset_local_today()
    assert edge.local_event_sequence() == 2
    assert edge.pending_events(0) == []
    assert edge.local_occupancy() == 0


def test_reset_command_runs_before_ack_and_removes_buffered_rows(tmp_path, monkeypatch):
    db_file = tmp_path / "lab_visitors.db"
    reset_file = tmp_path / "counter_reset.request"
    create_local_db(db_file)
    monkeypatch.setattr(edge, "DB_FILE", db_file)
    monkeypatch.setattr(edge, "RESET_REQUEST_FILE", reset_file)

    calls = []

    def fake_request(method, path, payload=None, timeout=10):
        calls.append((method, path, len(edge.pending_events(0))))
        if path == "/api/edge/commands":
            return {"commands": [{"id": 7, "command": "RESET_COUNTER", "payload": {}}]}
        return {"status": "ok"}

    monkeypatch.setattr(edge, "request_json", fake_request)
    monkeypatch.setattr(edge.time, "sleep", lambda _seconds: reset_file.unlink(missing_ok=True))

    edge.process_commands()

    assert edge.pending_events(0) == []
    assert calls[0][:2] == ("GET", "/api/edge/commands")
    assert calls[-1][0] == "POST"
    assert calls[-1][1] == "/api/edge/commands/7/ack"
    assert calls[-1][2] == 0
