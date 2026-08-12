import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "lab_visitors.db"
HEARTBEAT_FILE = BASE_DIR / "counter_heartbeat"
RESET_REQUEST_FILE = BASE_DIR / "counter_reset.request"
STATE_FILE = BASE_DIR / "edge_sync_state.json"
WIB = timezone(timedelta(hours=7))


def load_local_env():
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()

SERVER_URL = os.getenv("LABHUB_SERVER_URL", "").rstrip("/")
DEVICE_ID = os.getenv("LABHUB_EDGE_DEVICE_ID", "lab-robotika-01").strip()
DEVICE_TOKEN = os.getenv("LABHUB_EDGE_DEVICE_TOKEN", "")
SYNC_INTERVAL = max(1.0, float(os.getenv("LABHUB_EDGE_SYNC_INTERVAL", "2")))
HEARTBEAT_INTERVAL = max(2.0, float(os.getenv("LABHUB_EDGE_HEARTBEAT_INTERVAL", "5")))
COMMAND_INTERVAL = max(2.0, float(os.getenv("LABHUB_EDGE_COMMAND_INTERVAL", "5")))


def require_config():
    if not SERVER_URL.startswith(("http://", "https://")):
        raise RuntimeError("LABHUB_SERVER_URL belum diisi dengan URL server")
    if len(DEVICE_TOKEN) < 24:
        raise RuntimeError("LABHUB_EDGE_DEVICE_TOKEN minimal 24 karakter")
    if not DEVICE_ID:
        raise RuntimeError("LABHUB_EDGE_DEVICE_ID tidak boleh kosong")


def api_headers():
    return {
        "Content-Type": "application/json",
        "X-LabHub-Device": DEVICE_ID,
        "X-LabHub-Device-Token": DEVICE_TOKEN,
    }


def request_json(method, path, payload=None, timeout=10):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{SERVER_URL}{path}",
        data=body,
        headers=api_headers(),
        method=method,
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


def load_state():
    if not STATE_FILE.exists():
        return {"last_synced_id": 0}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {"last_synced_id": max(0, int(data.get("last_synced_id", 0)))}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"last_synced_id": 0}


def save_state(state):
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temp.replace(STATE_FILE)


def get_local_connection():
    if not DB_FILE.exists():
        return None
    conn = sqlite3.connect(DB_FILE, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def local_occupancy():
    conn = get_local_connection()
    if conn is None:
        return 0
    try:
        row = conn.execute(
            "SELECT occupancy FROM counter_state WHERE id = 1"
        ).fetchone()
        return max(0, int(row["occupancy"])) if row else 0
    finally:
        conn.close()


def heartbeat_payload():
    details = {}
    if HEARTBEAT_FILE.exists():
        try:
            details = json.loads(HEARTBEAT_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            details = {}
    return {
        "camera_ip": details.get("camera_ip"),
        "stream": details.get("stream"),
        "mode": details.get("mode", "Edge"),
        "occupancy": local_occupancy(),
    }


def parse_local_timestamp(value):
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return parsed.replace(tzinfo=WIB).isoformat()


def event_uuid(row):
    source = (
        f"{DEVICE_ID}|{row['id']}|{row['timestamp']}|"
        f"{row['track_id']}|{row['direction']}|{row['occupancy_after']}"
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:40]


def pending_events(last_synced_id, limit=100):
    conn = get_local_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT id, timestamp, track_id, direction, occupancy_after
            FROM visitor_events
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (last_synced_id, limit),
        ).fetchall()
        return rows
    finally:
        conn.close()


def sync_events(state):
    rows = pending_events(state["last_synced_id"])
    if not rows:
        return False

    payload = {
        "events": [
            {
                "event_uuid": event_uuid(row),
                "timestamp": parse_local_timestamp(row["timestamp"]),
                "track_id": row["track_id"],
                "direction": row["direction"],
                "occupancy_after": max(0, int(row["occupancy_after"])),
            }
            for row in rows
        ]
    }
    result = request_json("POST", "/api/edge/events", payload)
    state["last_synced_id"] = int(rows[-1]["id"])
    save_state(state)
    print(
        f"Sync event sampai ID {state['last_synced_id']} "
        f"(accepted={result.get('accepted', 0)}, duplicate={result.get('duplicates', 0)})"
    )
    return True


def send_heartbeat():
    request_json("POST", "/api/edge/heartbeat", heartbeat_payload())


def process_commands():
    result = request_json("GET", "/api/edge/commands")
    for command in result.get("commands", []):
        command_id = int(command["id"])
        command_name = str(command.get("command", "")).upper()
        if command_name == "RESET_COUNTER":
            RESET_REQUEST_FILE.write_text(
                datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S"),
                encoding="utf-8",
            )
            print(f"Command RESET_COUNTER #{command_id} diteruskan ke visitor counter.")
        else:
            print(f"Command #{command_id} tidak dikenal: {command_name}")
        request_json("POST", f"/api/edge/commands/{command_id}/ack", {})


def main():
    require_config()
    state = load_state()
    last_heartbeat = 0.0
    last_command_check = 0.0

    print("======================================")
    print("SMARTLAB EDGE SYNC AGENT")
    print("======================================")
    print(f"Server : {SERVER_URL}")
    print(f"Device : {DEVICE_ID}")
    print("Ctrl+C untuk berhenti.")
    print("")

    while True:
        now = time.monotonic()
        try:
            synced = sync_events(state)
            if synced:
                now = time.monotonic()

            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                send_heartbeat()
                last_heartbeat = now

            if now - last_command_check >= COMMAND_INTERVAL:
                process_commands()
                last_command_check = now

        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            print(f"Server menolak request: HTTP {error.code} {detail[:300]}")
        except (URLError, TimeoutError, OSError, sqlite3.Error, ValueError) as error:
            print(f"Sync tertunda: {error}")

        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nEdge sync agent dihentikan.")
