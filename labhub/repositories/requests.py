import json
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from labhub.models import ServiceRequest


ACTIVE_ROOM_STATUSES = {"PENDING", "APPROVED"}


def room_has_overlap(session: Session, room_name: str, start_at: datetime, end_at: datetime):
    return bool(
        session.scalar(
            select(func.count(ServiceRequest.id)).where(
                ServiceRequest.request_type == "ROOM_BOOKING",
                ServiceRequest.room_name == room_name,
                ServiceRequest.status.in_(ACTIVE_ROOM_STATUSES),
                ServiceRequest.start_at < end_at,
                ServiceRequest.end_at > start_at,
            )
        )
    )


def list_requests(session: Session, requester_id: str | None = None, request_type: str | None = None):
    filters = []
    if requester_id:
        filters.append(ServiceRequest.requester_id == requester_id)
    if request_type:
        filters.append(ServiceRequest.request_type == request_type)
    return session.scalars(
        select(ServiceRequest).where(*filters).order_by(ServiceRequest.created_at.desc()).limit(200)
    ).all()


def request_counts(session: Session):
    rows = session.execute(
        select(ServiceRequest.request_type, ServiceRequest.status, func.count(ServiceRequest.id))
        .group_by(ServiceRequest.request_type, ServiceRequest.status)
    ).all()
    return [{"request_type": row[0], "status": row[1], "count": row[2]} for row in rows]


def request_to_dict(item: ServiceRequest):
    return {
        "id": item.id,
        "request_code": item.request_code,
        "request_type": item.request_type,
        "requester_name": item.requester_name,
        "requester_id": item.requester_id,
        "title": item.title,
        "description": item.description,
        "status": item.status,
        "equipment_id": item.equipment_id,
        "room_name": item.room_name,
        "start_at": item.start_at,
        "end_at": item.end_at,
        "quantity": item.quantity,
        "details": json.loads(item.metadata_json or "{}"),
        "file_path": item.file_path,
        "admin_note": item.admin_note,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }
