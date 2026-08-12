from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from labhub.database import Base


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        CheckConstraint("quantity_total >= 0", name="ck_equipment_total_nonnegative"),
        CheckConstraint("quantity_available >= 0", name="ck_equipment_available_nonnegative"),
        CheckConstraint(
            "quantity_available <= quantity_total",
            name="ck_equipment_available_not_above_total",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(100), index=True)
    quantity_total: Mapped[int] = mapped_column(Integer, default=0)
    quantity_available: Mapped[int] = mapped_column(Integer, default=0)
    condition: Mapped[str] = mapped_column(String(32), default="GOOD", index=True)
    location: Mapped[str] = mapped_column(String(160), default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )


class StudentUser(Base):
    __tablename__ = "student_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(190), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LabSetting(Base):
    __tablename__ = "lab_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class ServiceRequest(Base):
    __tablename__ = "service_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    request_type: Mapped[str] = mapped_column(String(32), index=True)
    requester_name: Mapped[str] = mapped_column(String(160), index=True)
    requester_id: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    equipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipment.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    room_name: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    recipient_user_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(Text)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("service_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
