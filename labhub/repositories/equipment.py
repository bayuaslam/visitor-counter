from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from labhub.models import Equipment


def list_equipment(
    session: Session,
    query: str | None,
    category: str | None,
    availability: str | None,
    page: int,
    page_size: int,
):
    filters = []
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(
            or_(
                Equipment.name.ilike(pattern),
                Equipment.asset_code.ilike(pattern),
                Equipment.category.ilike(pattern),
            )
        )
    if category:
        filters.append(Equipment.category == category)
    if availability == "available":
        filters.append(Equipment.quantity_available > 0)
    elif availability == "unavailable":
        filters.append(Equipment.quantity_available == 0)

    base = select(Equipment).where(*filters)
    total = session.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0
    items = session.scalars(
        base.order_by(Equipment.name, Equipment.asset_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return items, total


def equipment_summary(session: Session):
    totals = session.execute(
        select(
            func.count(Equipment.id),
            func.coalesce(func.sum(Equipment.quantity_total), 0),
            func.coalesce(func.sum(Equipment.quantity_available), 0),
        )
    ).one()
    categories = session.scalars(
        select(Equipment.category).distinct().order_by(Equipment.category)
    ).all()
    total_assets, total_units, available_units = map(int, totals)
    return {
        "total_assets": total_assets,
        "total_units": total_units,
        "available_units": available_units,
        "unavailable_units": max(0, total_units - available_units),
        "categories": list(categories),
    }
