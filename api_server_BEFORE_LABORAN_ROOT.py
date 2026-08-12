from pathlib import Path
import json
import sqlite3
from datetime import date, datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi import Depends, File, Form, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from labhub.auth import CurrentUser, current_user
from labhub.database import get_session, init_database
from labhub.models import Equipment, ServiceRequest
from labhub.repositories.equipment import equipment_summary, list_equipment
from labhub.repositories.requests import list_requests, request_counts, request_to_dict, room_has_overlap
from labhub.schemas import EquipmentList, EquipmentSummary, ServiceRequestCreate, ServiceRequestItem, StatusUpdate


BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "lab_visitors.db"
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
UPLOAD_DIR = BASE_DIR / "storage" / "uploads"

app = FastAPI(
    title="Lab Robotika Visitor API",
    version="1.0.0"
)


@app.on_event("startup")
def startup():
    init_database()

# Untuk tahap development agar website lokal gampang mengambil data.
# Nanti saat website production sudah punya domain, origin ini kita batasi.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-LabHub-User", "X-LabHub-Name", "X-LabHub-Role"],
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


@app.get("/api/equipment", response_model=EquipmentList)
def equipment_catalog(
    q: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=100),
    availability: str | None = Query(default=None, pattern="^(available|unavailable)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    session: Session = Depends(get_session),
):
    items, total = list_equipment(
        session,
        query=q,
        category=category,
        availability=availability,
        page=page,
        page_size=page_size,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.get("/api/equipment/summary", response_model=EquipmentSummary)
def equipment_catalog_summary(session: Session = Depends(get_session)):
    return equipment_summary(session)


INITIAL_STATUS = {
    "EQUIPMENT_LOAN": "PENDING",
    "ROOM_BOOKING": "PENDING",
    "PRINT_3D": "SUBMITTED",
    "MAINTENANCE": "REPORTED",
}

STATUS_FLOW = {
    "EQUIPMENT_LOAN": ["PENDING", "APPROVED", "BORROWED", "RETURNED", "REJECTED"],
    "ROOM_BOOKING": ["PENDING", "APPROVED", "COMPLETED", "REJECTED", "CANCELLED"],
    "PRINT_3D": ["SUBMITTED", "REVIEW", "APPROVED", "QUEUED", "PRINTING", "FINISHED", "PICKED_UP", "REJECTED"],
    "MAINTENANCE": ["REPORTED", "CHECKING", "REPAIRING", "COMPLETED", "UNREPAIRABLE"],
}


def validate_request(payload: ServiceRequestCreate, session: Session):
    if not payload.title.strip():
        raise HTTPException(status_code=422, detail="Judul wajib diisi")
    if payload.quantity < 1 or payload.quantity > 100:
        raise HTTPException(status_code=422, detail="Quantity harus 1-100")
    if payload.request_type in {"EQUIPMENT_LOAN", "MAINTENANCE"} and not payload.equipment_id:
        raise HTTPException(status_code=422, detail="Alat wajib dipilih")
    if payload.equipment_id and not session.get(Equipment, payload.equipment_id):
        raise HTTPException(status_code=422, detail="Alat tidak ditemukan di inventory")
    if payload.request_type == "ROOM_BOOKING":
        if not payload.room_name or not payload.start_at or not payload.end_at:
            raise HTTPException(status_code=422, detail="Ruangan dan waktu wajib diisi")
        if payload.end_at <= payload.start_at:
            raise HTTPException(status_code=422, detail="Waktu selesai harus setelah waktu mulai")
        if room_has_overlap(session, payload.room_name, payload.start_at, payload.end_at):
            raise HTTPException(status_code=409, detail="Jadwal ruangan bertabrakan dengan booking lain")


@app.get("/api/requests", response_model=list[ServiceRequestItem])
def my_requests(
    request_type: str | None = Query(default=None),
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    items = list_requests(session, requester_id=user.user_id, request_type=request_type)
    return [request_to_dict(item) for item in items]


@app.post("/api/requests", response_model=ServiceRequestItem, status_code=201)
def create_request(
    payload: ServiceRequestCreate,
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    validate_request(payload, session)
    item = ServiceRequest(
        request_code=f"{payload.request_type[:3]}-{datetime.now():%y%m%d}-{uuid4().hex[:6].upper()}",
        request_type=payload.request_type,
        requester_name=user.name,
        requester_id=user.user_id,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        status=INITIAL_STATUS[payload.request_type],
        equipment_id=payload.equipment_id,
        room_name=payload.room_name,
        start_at=payload.start_at,
        end_at=payload.end_at,
        quantity=payload.quantity,
        metadata_json=json.dumps(payload.details),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return request_to_dict(item)


@app.post("/api/requests/{request_id}/file", response_model=ServiceRequestItem)
async def upload_request_file(
    request_id: int,
    upload: UploadFile = File(...),
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    item = session.get(ServiceRequest, request_id)
    if not item or (item.requester_id != user.user_id and user.role not in {"LABORAN", "ADMIN"}):
        raise HTTPException(status_code=404, detail="Request tidak ditemukan")
    allowed = {"PRINT_3D": {".stl", ".3mf"}, "MAINTENANCE": {".jpg", ".jpeg", ".png", ".webp"}}
    extension = Path(upload.filename or "").suffix.lower()
    if extension not in allowed.get(item.request_type, set()):
        raise HTTPException(status_code=422, detail="Extension file tidak diizinkan")
    content = await upload.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Ukuran file maksimal 20 MB")
    folder = UPLOAD_DIR / item.request_type.lower() / datetime.now().strftime("%Y/%m")
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = f"{item.request_code}_{uuid4().hex[:8]}{extension}"
    path = folder / safe_name
    path.write_bytes(content)
    item.file_path = str(path.relative_to(BASE_DIR))
    session.commit()
    session.refresh(item)
    return request_to_dict(item)


@app.get("/api/laboran/requests", response_model=list[ServiceRequestItem])
def laboran_requests(
    request_type: str | None = Query(default=None),
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    if user.role not in {"LABORAN", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Akses laboran diperlukan")
    return [request_to_dict(item) for item in list_requests(session, request_type=request_type)]


@app.get("/api/laboran/summary")
def laboran_summary(
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    if user.role not in {"LABORAN", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Akses laboran diperlukan")
    return {"counts": request_counts(session)}


@app.patch("/api/laboran/requests/{request_id}", response_model=ServiceRequestItem)
def update_request_status(
    request_id: int,
    payload: StatusUpdate,
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    if user.role not in {"LABORAN", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Akses laboran diperlukan")
    item = session.get(ServiceRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Request tidak ditemukan")
    if payload.status not in STATUS_FLOW[item.request_type]:
        raise HTTPException(status_code=422, detail="Status tidak valid untuk jenis request")
    if item.request_type == "ROOM_BOOKING" and payload.status == "APPROVED":
        overlap = session.query(ServiceRequest).filter(
            ServiceRequest.id != item.id,
            ServiceRequest.request_type == "ROOM_BOOKING",
            ServiceRequest.room_name == item.room_name,
            ServiceRequest.status == "APPROVED",
            ServiceRequest.start_at < item.end_at,
            ServiceRequest.end_at > item.start_at,
        ).first()
        if overlap:
            raise HTTPException(status_code=409, detail="Tidak dapat approve: jadwal bertabrakan")
    item.status = payload.status
    item.admin_note = payload.admin_note
    session.commit()
    session.refresh(item)
    return request_to_dict(item)


# Hasil build React dilayani oleh proses FastAPI yang sama. Mount dilakukan
# setelah route API agar /api/* tidak pernah tertangkap oleh frontend.
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/electrical-engineering-logo.webp", include_in_schema=False)
    def institutional_logo():
        return FileResponse(
            FRONTEND_DIST / "electrical-engineering-logo.webp",
            media_type="image/webp",
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend(full_path: str):
        return FileResponse(FRONTEND_DIST / "index.html")
