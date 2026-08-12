from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EquipmentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_code: str
    name: str
    category: str
    quantity_total: int
    quantity_available: int
    condition: str
    location: str
    description: str | None
    photo_path: str | None
    updated_at: datetime


class EquipmentList(BaseModel):
    items: list[EquipmentItem]
    total: int
    page: int
    page_size: int


class EquipmentSummary(BaseModel):
    total_assets: int
    total_units: int
    available_units: int
    unavailable_units: int
    categories: list[str]


class EquipmentCreate(BaseModel):
    asset_code: str
    name: str
    category: str
    quantity_total: int
    quantity_available: int
    condition: str = "GOOD"
    location: str = ""
    description: str | None = None


class EquipmentUpdate(EquipmentCreate):
    pass


RequestType = Literal["EQUIPMENT_LOAN", "ROOM_BOOKING", "PRINT_3D", "MAINTENANCE"]


class ServiceRequestCreate(BaseModel):
    request_type: RequestType
    title: str
    description: str | None = None
    equipment_id: int | None = None
    room_name: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    quantity: int = 1
    details: dict[str, Any] = Field(default_factory=dict)


class ServiceRequestItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_code: str
    request_type: str
    requester_name: str
    requester_id: str
    title: str
    description: str | None
    status: str
    equipment_id: int | None
    room_name: str | None
    start_at: datetime | None
    end_at: datetime | None
    quantity: int
    details: dict[str, Any]
    file_path: str | None
    admin_note: str | None
    created_at: datetime
    updated_at: datetime


class StatusUpdate(BaseModel):
    status: str
    admin_note: str | None = None
