from pathlib import Path
import sqlite3
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "lab_visitors.db"
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

app = FastAPI(
    title="Lab Robotika Visitor API",
    version="1.0.0"
)

# Untuk tahap development agar website lokal gampang mengambil data.
# Nanti saat website production sudah punya domain, origin ini kita batasi.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_connection():
    if not DB_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="Database lab_visitors.db belum ditemukan. Jalankan visitor_counter.py dulu."
        )

    conn = sqlite3.connect(DB_FILE, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "Lab Robotika Visitor API"
    }


@app.get("/", include_in_schema=False)
def root():
    if FRONTEND_DIST.exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    return health()


@app.get("/api/visitors")
def visitors():
    today = date.today().isoformat()

    with get_connection() as conn:
        totals = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN direction = 'IN' THEN 1 ELSE 0 END), 0) AS today_in,
                COALESCE(SUM(CASE WHEN direction = 'OUT' THEN 1 ELSE 0 END), 0) AS today_out
            FROM visitor_events
            WHERE event_date = ?
            """,
            (today,),
        ).fetchone()

        state = conn.execute(
            """
            SELECT occupancy, updated_at
            FROM counter_state
            WHERE id = 1
            """
        ).fetchone()

        last_event = conn.execute(
            """
            SELECT direction, timestamp
            FROM visitor_events
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    return {
        "date": today,
        "today_in": int(totals["today_in"]),
        "today_out": int(totals["today_out"]),
        "inside": int(state["occupancy"]) if state else 0,
        "last_event": last_event["direction"] if last_event else None,
        "last_event_time": last_event["timestamp"] if last_event else None,
        "updated_at": state["updated_at"] if state else None,
    }


@app.get("/api/visitors/recent")
def recent_visitors(limit: int = 20):
    limit = max(1, min(limit, 100))

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                timestamp,
                track_id,
                direction,
                occupancy_after
            FROM visitor_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return {
        "events": [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "track_id": row["track_id"],
                "direction": row["direction"],
                "occupancy_after": row["occupancy_after"],
            }
            for row in rows
        ]
    }


# Hasil build React dilayani oleh proses FastAPI yang sama. Mount dilakukan
# setelah route API agar /api/* tidak pernah tertangkap oleh frontend.
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend(full_path: str):
        return FileResponse(FRONTEND_DIST / "index.html")
