from pathlib import Path
import json
import os
import re
from datetime import date, datetime, time as dt_time, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi import Depends, File, Form, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel

from labhub.auth import CurrentUser, SESSION_COOKIE, STUDENT_SESSION_COOKIE, create_admin_session, create_guest_session, create_student_session, current_user, hash_password, student_session, valid_admin_session, verify_admin_password, verify_password
from labhub.database import get_session, init_database
from labhub.edge_auth import configured_device_id, require_edge_device
from labhub.models import CounterState, DeviceCommand, EdgeDeviceState, Equipment, LabSetting, Notification, ServiceRequest, StudentUser, VisitorEvent
from labhub.repositories.equipment import equipment_summary, list_equipment
from labhub.repositories.requests import list_requests, request_counts, request_to_dict, room_has_overlap
from labhub.schemas import EquipmentCreate, EquipmentItem, EquipmentList, EquipmentSummary, EquipmentUpdate, ServiceRequestCreate, ServiceRequestItem, StatusUpdate
from labhub.xlsx_import import read_first_sheet


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
UPLOAD_DIR = Path(os.getenv("LABHUB_UPLOAD_DIR", str(BASE_DIR / "storage" / "uploads")))
WIB = timezone(timedelta(hours=7))
ENVIRONMENT = os.getenv("LABHUB_ENV", "development").strip().lower()
COOKIE_SECURE = os.getenv(
    "LABHUB_COOKIE_SECURE",
    "1" if ENVIRONMENT == "production" else "0",
).strip() == "1"
ALLOW_UNVERIFIED_REGISTRATION = os.getenv(
    "LABHUB_ALLOW_UNVERIFIED_REGISTRATION",
    "0" if ENVIRONMENT == "production" else "1",
).strip() == "1"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "LABHUB_ALLOWED_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]

app = FastAPI(
    title="Lab Robotika Visitor API",
    version="2.0.0"
)


@app.on_event("startup")
def startup():
    init_database()


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=[
        "Content-Type",
        "X-LabHub-User",
        "X-LabHub-Name",
        "X-LabHub-Role",
        "X-LabHub-Device",
        "X-LabHub-Device-Token",
    ],
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def wib_day_bounds(target_date: date | None = None) -> tuple[datetime, datetime]:
    day = target_date or datetime.now(WIB).date()
    start_local = datetime.combine(day, dt_time.min, tzinfo=WIB)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


class AdminLoginPayload(BaseModel):
    password: str


class StudentAuthPayload(BaseModel):
    email: str
    password: str


class LabStatusPayload(BaseModel):
    is_open: bool


class EdgeHeartbeatPayload(BaseModel):
    camera_ip: str | None = None
    stream: str | None = None
    mode: str | None = None
    occupancy: int = 0


class EdgeVisitorEventPayload(BaseModel):
    event_uuid: str
    timestamp: datetime
    track_id: int | None = None
    direction: str
    occupancy_after: int


class EdgeVisitorEventBatch(BaseModel):
    events: list[EdgeVisitorEventPayload]


@app.post("/api/admin/login")
def admin_login(payload: AdminLoginPayload, response: Response):
    if not verify_admin_password(payload.password):
        raise HTTPException(status_code=401, detail="Password salah")
    token, max_age = create_admin_session()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="strict",
        secure=COOKIE_SECURE,
        path="/",
    )
    return {"authenticated": True, "name": "Laboran"}


@app.get("/api/admin/session")
def admin_session(request: Request):
    authenticated = valid_admin_session(request.cookies.get(SESSION_COOKIE))
    if not authenticated:
        raise HTTPException(status_code=401, detail="Sesi admin tidak aktif")
    return {"authenticated": True, "name": "Laboran"}


@app.post("/api/admin/logout")
def admin_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"authenticated": False}


def normalized_uii_email(value: str) -> str:
    email = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9._%+-]+@(?:[a-z0-9-]+\.)*uii\.ac\.id", email):
        raise HTTPException(status_code=422, detail="Gunakan email resmi UII")
    return email


def set_student_cookie(response: Response, email: str):
    token, max_age = create_student_session(email)
    response.set_cookie(
        STUDENT_SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="strict",
        secure=COOKIE_SECURE,
        path="/",
    )


@app.post("/api/auth/register", status_code=201)
def student_register(payload: StudentAuthPayload, response: Response, session: Session = Depends(get_session)):
    if not ALLOW_UNVERIFIED_REGISTRATION:
        raise HTTPException(
            status_code=503,
            detail="Registrasi production dinonaktifkan sampai verifikasi email UII/SSO diaktifkan",
        )
    email = normalized_uii_email(payload.email)
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="Password minimal 8 karakter")
    if session.query(StudentUser).filter(StudentUser.email == email).first():
        raise HTTPException(status_code=409, detail="Email sudah terdaftar")
    user = StudentUser(email=email, password_hash=hash_password(payload.password))
    session.add(user)
    session.commit()
    set_student_cookie(response, email)
    return {"authenticated": True, "email": email}


@app.post("/api/auth/login")
def student_login(payload: StudentAuthPayload, response: Response, session: Session = Depends(get_session)):
    email = normalized_uii_email(payload.email)
    user = session.query(StudentUser).filter(StudentUser.email == email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email atau password salah")
    set_student_cookie(response, email)
    return {"authenticated": True, "email": email}


@app.post("/api/auth/guest")
def guest_login(response: Response):
    token, max_age = create_guest_session()
    response.set_cookie(
        STUDENT_SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="strict",
        secure=COOKIE_SECURE,
        path="/",
    )
    return {"authenticated": True, "email": "Tamu", "guest": True}


@app.get("/api/auth/session")
def student_auth_session(request: Request, session: Session = Depends(get_session)):
    data = student_session(request.cookies.get(STUDENT_SESSION_COOKIE))
    if data and data.get("role") == "GUEST":
        return {"authenticated": True, "email": "Tamu", "guest": True}
    user = session.query(StudentUser).filter(StudentUser.email == data.get("sub")).first() if data else None
    if not user:
        raise HTTPException(status_code=401, detail="Sesi mahasiswa tidak aktif")
    return {"authenticated": True, "email": user.email}


@app.post("/api/auth/logout")
def student_logout(response: Response):
    response.delete_cookie(STUDENT_SESSION_COOKIE, path="/")
    return {"authenticated": False}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "Lab Robotika Visitor API",
        "environment": ENVIRONMENT,
    }


@app.post("/api/edge/heartbeat")
def edge_heartbeat(
    payload: EdgeHeartbeatPayload,
    device_id: str = Depends(require_edge_device),
    session: Session = Depends(get_session),
):
    if payload.occupancy < 0:
        raise HTTPException(status_code=422, detail="Occupancy tidak boleh negatif")

    now = utc_now()
    device = session.get(EdgeDeviceState, device_id)
    if device is None:
        device = EdgeDeviceState(device_id=device_id)
        session.add(device)
    device.camera_ip = (payload.camera_ip or "")[:64] or None
    device.stream = (payload.stream or "")[:120] or None
    device.mode = (payload.mode or "")[:80] or None
    device.last_seen_at = now

    counter = session.get(CounterState, device_id)
    if counter is None:
        counter = CounterState(device_id=device_id, occupancy=payload.occupancy, updated_at=now)
        session.add(counter)
    else:
        counter.occupancy = payload.occupancy
        counter.updated_at = now

    session.commit()
    return {"status": "ok", "server_time": now.isoformat()}


@app.post("/api/edge/events")
def edge_events(
    payload: EdgeVisitorEventBatch,
    device_id: str = Depends(require_edge_device),
    session: Session = Depends(get_session),
):
    if not payload.events:
        return {"accepted": 0, "duplicates": 0}
    if len(payload.events) > 500:
        raise HTTPException(status_code=413, detail="Maksimal 500 event per batch")

    accepted = 0
    duplicates = 0
    counter = session.get(CounterState, device_id)

    for incoming in payload.events:
        if not re.fullmatch(r"[A-Za-z0-9._:-]{8,80}", incoming.event_uuid):
            raise HTTPException(status_code=422, detail="event_uuid tidak valid")
        direction = incoming.direction.strip().upper()
        if direction not in {"IN", "OUT"}:
            raise HTTPException(status_code=422, detail="Direction harus IN atau OUT")
        if incoming.occupancy_after < 0:
            raise HTTPException(status_code=422, detail="occupancy_after tidak boleh negatif")

        existing = session.query(VisitorEvent.id).filter(
            VisitorEvent.event_uuid == incoming.event_uuid
        ).first()
        if existing:
            duplicates += 1
            continue

        occurred_at = incoming.timestamp
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=WIB)
        occurred_at = occurred_at.astimezone(timezone.utc)

        session.add(
            VisitorEvent(
                event_uuid=incoming.event_uuid,
                device_id=device_id,
                occurred_at=occurred_at,
                track_id=incoming.track_id,
                direction=direction,
                occupancy_after=incoming.occupancy_after,
            )
        )
        accepted += 1

        if counter is None:
            counter = CounterState(
                device_id=device_id,
                occupancy=incoming.occupancy_after,
                updated_at=occurred_at,
            )
            session.add(counter)
        elif as_utc(counter.updated_at) is None or occurred_at >= as_utc(counter.updated_at):
            counter.occupancy = incoming.occupancy_after
            counter.updated_at = occurred_at

    session.commit()
    return {"accepted": accepted, "duplicates": duplicates}


@app.get("/api/edge/commands")
def edge_commands(
    device_id: str = Depends(require_edge_device),
    session: Session = Depends(get_session),
):
    rows = (
        session.query(DeviceCommand)
        .filter(
            DeviceCommand.device_id == device_id,
            DeviceCommand.acknowledged_at.is_(None),
        )
        .order_by(DeviceCommand.created_at.asc(), DeviceCommand.id.asc())
        .limit(20)
        .all()
    )
    return {
        "commands": [
            {
                "id": row.id,
                "command": row.command,
                "payload": json.loads(row.payload_json) if row.payload_json else {},
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@app.post("/api/edge/commands/{command_id}/ack")
def acknowledge_edge_command(
    command_id: int,
    device_id: str = Depends(require_edge_device),
    session: Session = Depends(get_session),
):
    command = (
        session.query(DeviceCommand)
        .filter(DeviceCommand.id == command_id, DeviceCommand.device_id == device_id)
        .first()
    )
    if not command:
        raise HTTPException(status_code=404, detail="Command tidak ditemukan")
    if command.acknowledged_at is None:
        command.acknowledged_at = utc_now()
        session.commit()
    return {"status": "ok"}


@app.get("/api/counter/status")
def counter_status(session: Session = Depends(get_session)):
    device_id = configured_device_id()
    device = session.get(EdgeDeviceState, device_id)
    last_seen = as_utc(device.last_seen_at) if device else None
    active = bool(last_seen and utc_now() - last_seen <= timedelta(seconds=15))
    camera_status = "connected" if device and device.camera_ip else "—"
    return {
        "active": active,
        "status": "LIVE" if active else "OFFLINE",
        "last_heartbeat": last_seen.isoformat() if last_seen else None,
        "camera_ip": device.camera_ip if device and ENVIRONMENT != "production" else camera_status,
        "stream": device.stream if device else "—",
        "mode": device.mode if device else "Edge",
    }


@app.post("/api/admin/counter/reset")
def reset_counter(request: Request, session: Session = Depends(get_session)):
    if not valid_admin_session(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status_code=401, detail="Sesi admin tidak aktif")

    device_id = configured_device_id()
    today = datetime.now(WIB).date()
    start_utc, end_utc = wib_day_bounds(today)

    (
        session.query(VisitorEvent)
        .filter(
            VisitorEvent.device_id == device_id,
            VisitorEvent.occurred_at >= start_utc,
            VisitorEvent.occurred_at < end_utc,
        )
        .delete(synchronize_session=False)
    )

    now = utc_now()
    counter = session.get(CounterState, device_id)
    if counter is None:
        counter = CounterState(device_id=device_id, occupancy=0, updated_at=now)
        session.add(counter)
    else:
        counter.occupancy = 0
        counter.updated_at = now

    pending_reset = (
        session.query(DeviceCommand)
        .filter(
            DeviceCommand.device_id == device_id,
            DeviceCommand.command == "RESET_COUNTER",
            DeviceCommand.acknowledged_at.is_(None),
        )
        .first()
    )
    if pending_reset is None:
        session.add(
            DeviceCommand(
                device_id=device_id,
                command="RESET_COUNTER",
                payload_json=json.dumps({"requested_at": now.isoformat()}),
            )
        )

    session.commit()
    return {
        "reset": True,
        "date": today.isoformat(),
        "inside": 0,
        "today_in": 0,
        "today_out": 0,
    }


@app.get("/api/lab/status")
def lab_status(session: Session = Depends(get_session)):
    setting = session.get(LabSetting, "operational_status")
    return {
        "is_open": setting is None or setting.value == "OPEN",
        "status": "OPEN" if setting is None or setting.value == "OPEN" else "CLOSED",
        "updated_at": setting.updated_at.isoformat() if setting else None,
    }


@app.patch("/api/admin/lab/status")
def update_lab_status(payload: LabStatusPayload, request: Request, session: Session = Depends(get_session)):
    if not valid_admin_session(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status_code=401, detail="Sesi admin tidak aktif")
    setting = session.get(LabSetting, "operational_status")
    if setting is None:
        setting = LabSetting(key="operational_status", value="OPEN" if payload.is_open else "CLOSED")
        session.add(setting)
    else:
        setting.value = "OPEN" if payload.is_open else "CLOSED"
        setting.updated_at = datetime.now()
    session.commit()
    session.refresh(setting)
    return {"is_open": payload.is_open, "status": setting.value, "updated_at": setting.updated_at.isoformat()}


@app.get("/", include_in_schema=False)
def root():
    if FRONTEND_DIST.exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    return health()


@app.get("/api/visitors")
def visitors(session: Session = Depends(get_session)):
    device_id = configured_device_id()
    today = datetime.now(WIB).date()
    start_utc, end_utc = wib_day_bounds(today)

    today_in = (
        session.query(VisitorEvent.id)
        .filter(
            VisitorEvent.device_id == device_id,
            VisitorEvent.occurred_at >= start_utc,
            VisitorEvent.occurred_at < end_utc,
            VisitorEvent.direction == "IN",
        )
        .count()
    )
    today_out = (
        session.query(VisitorEvent.id)
        .filter(
            VisitorEvent.device_id == device_id,
            VisitorEvent.occurred_at >= start_utc,
            VisitorEvent.occurred_at < end_utc,
            VisitorEvent.direction == "OUT",
        )
        .count()
    )
    state = session.get(CounterState, device_id)
    last_event = (
        session.query(VisitorEvent)
        .filter(VisitorEvent.device_id == device_id)
        .order_by(VisitorEvent.occurred_at.desc(), VisitorEvent.id.desc())
        .first()
    )

    return {
        "date": today.isoformat(),
        "today_in": int(today_in),
        "today_out": int(today_out),
        "inside": int(state.occupancy) if state else 0,
        "last_event": last_event.direction if last_event else None,
        "last_event_time": last_event.occurred_at.isoformat() if last_event else None,
        "updated_at": state.updated_at.isoformat() if state else None,
    }


@app.get("/api/visitors/recent")
def recent_visitors(limit: int = 20, session: Session = Depends(get_session)):
    limit = max(1, min(limit, 100))
    device_id = configured_device_id()
    rows = (
        session.query(VisitorEvent)
        .filter(VisitorEvent.device_id == device_id)
        .order_by(VisitorEvent.occurred_at.desc(), VisitorEvent.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "events": [
            {
                "id": row.id,
                "timestamp": row.occurred_at.isoformat(),
                "track_id": row.track_id,
                "direction": row.direction,
                "occupancy_after": row.occupancy_after,
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


def ensure_staff(user: CurrentUser):
    if user.role not in {"LABORAN", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Akses laboran diperlukan")


def apply_equipment_values(item: Equipment, payload: EquipmentCreate | EquipmentUpdate):
    if payload.quantity_total < 0 or payload.quantity_available < 0 or payload.quantity_available > payload.quantity_total:
        raise HTTPException(status_code=422, detail="Quantity inventory tidak valid")
    if not payload.asset_code.strip() or not payload.name.strip() or not payload.category.strip():
        raise HTTPException(status_code=422, detail="Kode aset, nama, dan kategori wajib diisi")
    for field in ("asset_code", "name", "category", "quantity_total", "quantity_available", "condition", "location", "description"):
        value = getattr(payload, field)
        setattr(item, field, value.strip() if isinstance(value, str) else value)


@app.post("/api/laboran/equipment", response_model=EquipmentItem, status_code=201)
def create_equipment(
    payload: EquipmentCreate,
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    ensure_staff(user)
    item = Equipment()
    apply_equipment_values(item, payload)
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Kode aset sudah digunakan")
    session.refresh(item)
    return item


@app.patch("/api/laboran/equipment/{equipment_id}", response_model=EquipmentItem)
def update_equipment(
    equipment_id: int,
    payload: EquipmentUpdate,
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    ensure_staff(user)
    item = session.get(Equipment, equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Alat tidak ditemukan")
    apply_equipment_values(item, payload)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Kode aset sudah digunakan")
    session.refresh(item)
    return item


@app.delete("/api/laboran/equipment/{equipment_id}", status_code=204)
def delete_equipment(
    equipment_id: int,
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    ensure_staff(user)
    item = session.get(Equipment, equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Alat tidak ditemukan")
    session.delete(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Alat sudah dipakai pada request dan tidak dapat dihapus")


@app.post("/api/laboran/equipment/import")
async def import_equipment_excel(
    upload: UploadFile = File(...),
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    ensure_staff(user)
    if Path(upload.filename or "").suffix.lower() != ".xlsx":
        raise HTTPException(status_code=422, detail="Gunakan file Excel .xlsx")
    content = await upload.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Ukuran Excel maksimal 5 MB")
    try:
        rows = read_first_sheet(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not rows:
        raise HTTPException(status_code=422, detail="Excel kosong")
    required = ["asset_code", "name", "category", "quantity_total", "quantity_available", "condition", "location", "description"]
    headers = [str(value).strip().lower() for value in rows[0]]
    missing = [column for column in required[:5] if column not in headers]
    if missing:
        raise HTTPException(status_code=422, detail=f"Kolom wajib tidak ditemukan: {', '.join(missing)}")
    imported = updated = skipped = 0
    for row_number, row in enumerate(rows[1:], start=2):
        values = {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
        if not str(values.get("asset_code", "")).strip():
            skipped += 1
            continue
        try:
            total = int(float(values.get("quantity_total", 0)))
            available = int(float(values.get("quantity_available", 0)))
            payload = EquipmentCreate(
                asset_code=str(values["asset_code"]), name=str(values["name"]), category=str(values["category"]),
                quantity_total=total, quantity_available=available,
                condition=str(values.get("condition") or "GOOD"), location=str(values.get("location") or ""),
                description=str(values.get("description") or "") or None,
            )
            item = session.query(Equipment).filter(Equipment.asset_code == payload.asset_code.strip()).first()
            if item:
                apply_equipment_values(item, payload); updated += 1
            else:
                item = Equipment(); apply_equipment_values(item, payload); session.add(item); imported += 1
        except (ValueError, TypeError) as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=f"Data tidak valid pada baris {row_number}: {exc}")
    session.commit()
    return {"imported": imported, "updated": updated, "skipped": skipped}


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
    if user.role == "GUEST":
        return []
    items = list_requests(session, requester_id=user.user_id, request_type=request_type)
    return [request_to_dict(item) for item in items]


@app.post("/api/requests", response_model=ServiceRequestItem, status_code=201)
def create_request(
    payload: ServiceRequestCreate,
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    if user.role == "GUEST":
        raise HTTPException(status_code=403, detail="Login dengan email UII diperlukan untuk membuat pengajuan")
    validate_request(payload, session)
    item = ServiceRequest(
        request_code=f"{payload.request_type[:3]}-{datetime.now(WIB):%y%m%d}-{uuid4().hex[:6].upper()}",
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
    session.flush()
    session.add(Notification(
        recipient_role="LABORAN",
        kind="NEW_REQUEST",
        title="Pengajuan baru",
        message=f"{user.name} mengajukan {payload.request_type.replace('_', ' ').lower()}: {item.title}",
        request_id=item.id,
    ))
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
    folder = UPLOAD_DIR / item.request_type.lower() / datetime.now(WIB).strftime("%Y/%m")
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = f"{item.request_code}_{uuid4().hex[:8]}{extension}"
    path = folder / safe_name
    path.write_bytes(content)
    item.file_path = str(path.relative_to(UPLOAD_DIR.parent)) if path.is_relative_to(UPLOAD_DIR.parent) else str(path)
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


def visible_notifications_query(session: Session, user: CurrentUser):
    query = session.query(Notification)
    if user.role in {"LABORAN", "ADMIN"}:
        return query.filter(Notification.recipient_role == "LABORAN")
    if user.role == "GUEST":
        return query.filter(Notification.id < 0)
    return query.filter(Notification.recipient_user_id == user.user_id)


@app.get("/api/notifications")
def notifications(
    limit: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    query = visible_notifications_query(session, user)
    rows = query.order_by(Notification.created_at.desc()).limit(limit).all()
    unread = query.filter(Notification.read_at.is_(None)).count()
    return {
        "unread": unread,
        "items": [
            {
                "id": item.id,
                "kind": item.kind,
                "title": item.title,
                "message": item.message,
                "request_id": item.request_id,
                "read": item.read_at is not None,
                "created_at": item.created_at,
            }
            for item in rows
        ],
    }


@app.patch("/api/notifications/{notification_id}/read")
def read_notification(
    notification_id: int,
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    item = visible_notifications_query(session, user).filter(Notification.id == notification_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    if item.read_at is None:
        item.read_at = datetime.now()
        session.commit()
    return {"status": "ok"}


@app.patch("/api/notification-actions/read-all")
def read_all_notifications(
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_session),
):
    updated = visible_notifications_query(session, user).filter(Notification.read_at.is_(None)).update(
        {Notification.read_at: datetime.now()},
        synchronize_session=False,
    )
    session.commit()
    return {"status": "ok", "updated": updated}


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
    previous_status = item.status
    item.status = payload.status
    item.admin_note = payload.admin_note
    if previous_status != payload.status:
        session.add(Notification(
            recipient_user_id=item.requester_id,
            kind="STATUS_UPDATE",
            title="Status pengajuan diperbarui",
            message=f"{item.title}: {previous_status.replace('_', ' ')} → {payload.status.replace('_', ' ')}",
            request_id=item.id,
        ))
    session.commit()
    session.refresh(item)
    return request_to_dict(item)


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
