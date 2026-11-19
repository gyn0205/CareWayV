"""Read the active wayfinding catalog and navigation graph for a site."""

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Building, Department, Doctor, Floor, HospitalSite, Kiosk, NavigationEdge, NavigationNode, Room,
    Service, ServiceAlias, ServiceLocation,
)


def active_kiosks(db: Session, code: str):
    return db.scalars(select(Kiosk).where(Kiosk.code == code, Kiosk.is_active))


def active_site(db: Session, site_id: int):
    return db.get(HospitalSite, site_id)


def site_floors(db: Session, site_id: int):
    buildings = select(Building.id).where(Building.site_id == site_id)
    return db.scalars(
        select(Floor).where(Floor.site_id == site_id, Floor.building_id.in_(buildings))
    )


def floor_nodes(db: Session, site_id: int, floor_ids: Collection[int], node_ids: Collection[int] | None = None):
    query = select(NavigationNode).where(
        NavigationNode.site_id == site_id, NavigationNode.floor_id.in_(floor_ids),
    )
    if node_ids is not None:
        query = query.where(NavigationNode.id.in_(node_ids))
    return db.scalars(query)


def active_edges(db: Session, site_id: int, wheelchair: bool):
    query = select(NavigationEdge).where(NavigationEdge.site_id == site_id, NavigationEdge.is_active)
    if wheelchair:
        query = query.where(NavigationEdge.wheelchair_accessible)
    return db.scalars(query)


def site_departments(db: Session, site_id: int):
    return db.scalars(select(Department).where(Department.site_id == site_id))


def active_rooms(db: Session, site_id: int):
    return db.scalars(select(Room).where(Room.site_id == site_id, Room.is_active))


def active_service_rooms(db: Session, site_id: int):
    # Explicitly filter soft-deleted records in the multi-table query.
    services, locations, rooms = (
        model.__table__ for model in (Service, ServiceLocation, Room)
    )
    return db.execute(
        select(services.c.id, services.c.name, rooms.c.code)
        .select_from(
            services.join(
                locations, (locations.c.site_id == services.c.site_id)
                & (locations.c.service_id == services.c.id),
            ).join(
                rooms, (rooms.c.site_id == locations.c.site_id) & (rooms.c.id == locations.c.room_id),
            )
        )
        .where(
            services.c.site_id == site_id, services.c.deleted_at.is_(None),
            locations.c.deleted_at.is_(None), locations.c.is_active,
            rooms.c.deleted_at.is_(None), rooms.c.is_active,
        )
    )


def active_doctors(db: Session, site_id: int):
    # Bác sĩ đang khám kèm mã phòng; lọc xoá mềm ở cả hai bảng như truy vấn dịch vụ.
    doctors, rooms = Doctor.__table__, Room.__table__
    return db.execute(
        select(
            doctors.c.code, doctors.c.title, doctors.c.name, doctors.c.normalized_name,
            rooms.c.code.label("room_code"),
        )
        .select_from(doctors.join(
            rooms, (rooms.c.site_id == doctors.c.site_id) & (rooms.c.id == doctors.c.room_id),
        ))
        .where(
            doctors.c.site_id == site_id, doctors.c.deleted_at.is_(None), doctors.c.is_active,
            rooms.c.deleted_at.is_(None), rooms.c.is_active,
        )
    )


def active_service_aliases(db: Session, site_id: int):
    aliases = ServiceAlias.__table__
    return db.execute(
        select(aliases.c.service_id, aliases.c.alias)
        .where(aliases.c.site_id == site_id, aliases.c.deleted_at.is_(None))
    )
