"""Load synthetic floor 3–4 wayfinding data into PostgreSQL."""

import unicodedata

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models import (
    Building,
    Department,
    Doctor,
    Floor,
    HospitalSite,
    Kiosk,
    NavigationEdge,
    NavigationNode,
    Room,
    Service,
    ServiceAlias,
    ServiceLocation,
)

from .catalog import ENGLISH_ZONE_NAMES, SITE_CODE, ZONES
from .doctors import doctor_slots
from .layout import FLOORS, HEIGHT, WIDTH, build_layout, room_slots


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    return " ".join("".join(c for c in folded if not unicodedata.combining(c)).split())


def sync(session, model, scope, keys, rows):
    """Insert or refresh the listed records, preserving IDs and unrelated records."""
    query = select(model).filter_by(**scope).execution_options(include_deleted=True)
    existing = {
        tuple(getattr(record, key) for key in keys): record for record in session.scalars(query)
    }
    result = {}
    for row in rows:
        identity = tuple(row[key] for key in keys)
        record = existing.get(identity)
        if record is None:
            record = model(**scope, **row)
            session.add(record)
        else:
            for key, value in row.items():
                setattr(record, key, value)
            record.restore()
        result[identity] = record
    session.flush()
    return result


def retire(session, model, scope, keep):
    """Ẩn (soft-delete) bản ghi cũ không còn trong mặt bằng mới, tránh lối tắt sai."""
    # So sánh theo đối tượng trong session (cạnh dùng khóa ghép, không có cột id).
    kept = set(keep.values())
    for record in session.scalars(select(model).filter_by(**scope)):
        if record not in kept:
            record.soft_delete()
            if hasattr(record, "is_active"):
                record.is_active = False
    session.flush()


def seed(session) -> dict[str, int]:
    # Concurrent invocations of this loader should see the same IDs.
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:code))"), {"code": SITE_CODE})
    site = sync(
        session, HospitalSite, {}, ("code",), [
            {"code": SITE_CODE, "name": "Vinmec · Bản đồ mô phỏng tầng 3–4"},
        ],
    )[SITE_CODE,]
    scope = {"site_id": site.id}
    building = sync(
        session, Building, scope, ("code",), [
            {"code": "DEMO", "name": "Tòa nhà mô phỏng"},
        ],
    )["DEMO",]
    floors = sync(
        session, Floor, {**scope, "building_id": building.id}, ("level",), [
            {"level": floor, "label": f"Tầng {floor}", "map_asset_url": None}
            for floor in FLOORS
        ],
    )
    departments = sync(
        session, Department, scope, ("code",), [
            {"code": zone.code, "name": zone.name, "name_en": ENGLISH_ZONE_NAMES[zone.code]}
            for zone in ZONES
        ],
    )
    layout = build_layout()
    nodes = sync(
        session, NavigationNode, scope, ("floor_id", "code"), [
            {
                "floor_id": floors[floor,].id, "code": code, "label": point.label,
                "x": point.x / WIDTH, "y": point.y / HEIGHT,
            }
            for (floor, code), point in layout.nodes.items()
        ],
    )

    def node_id(key):
        floor, code = key
        return nodes[floors[floor,].id, code].id

    edges = sync(
        session, NavigationEdge, scope, ("from_node_id", "to_node_id", "kind"), [
            {
                "from_node_id": node_id(edge.origin), "to_node_id": node_id(edge.destination),
                "kind": edge.kind, "cost_seconds": edge.cost, "instruction": edge.instruction,
                "instruction_en": edge.instruction_en,
                "wheelchair_accessible": edge.kind != "stairs", "is_active": True,
            }
            for edge in layout.edges
        ],
    )
    # Đồ thị cũ (bản sơ đồ trước) bị ẩn đi để chỉ còn lối đi theo mặt bằng mới.
    retire(session, NavigationEdge, scope, edges)
    retire(session, NavigationNode, scope, nodes)
    # 4 kiosk = 4 bảng sơ đồ (2 bảng mỗi tầng). Giữ mã KIOSK-3/KIOSK-4 (thang máy B) cho client cũ.
    kiosks = sync(
        session, Kiosk, scope, ("code",), [
            {
                "code": code, "name": f"Kiosk tầng {floor} · thang máy {lift}",
                "origin_node_id": node_id((floor, node)), "is_active": True,
            }
            for floor in FLOORS
            for code, node, lift in ((f"KIOSK-{floor}-A", "KIOSK-A", "A"), (f"KIOSK-{floor}", "KIOSK", "B"))
        ],
    )
    slots = [slot for zone in ZONES for slot in room_slots(zone)]
    rooms = sync(
        session, Room, scope, ("code",), [
            {
                "code": slot.code, "name": slot.name, "description": slot.description,
                "entrance_node_id": node_id((slot.zone.floor, slot.code)),
                "department_id": departments[slot.zone.code,].id, "is_active": True,
            }
            for slot in slots
        ],
    )
    # Share a service across rooms for the same activity, including A/B room pairs.
    service_by_room = {
        slot.code: slot.name[:-2] if slot.name.endswith((" A", " B", " C", " D")) else slot.name
        for slot in slots
    }
    service_rows = {}
    for room_code, name in service_by_room.items():
        service_rows.setdefault(name, {
            "code": f"DV-{room_code}", "name": name, "normalized_name": normalize(name),
        })
    services = sync(session, Service, scope, ("code",), service_rows.values())
    service_ids = {name: services[row["code"],].id for name, row in service_rows.items()}
    aliases = {
        "Thanh toán viện phí": (
            "thanh toán", "trả tiền", "đóng viện phí", "quầy thu ngân", "pay", "cashier",
            "pay my bill", "pay the hospital bill", "hospital billing",
        ),
        "Siêu âm tim qua thành ngực": ("siêu âm tim", "echocardiogram", "heart ultrasound"),
        "Khám mắt tổng quát": ("khám mắt", "eye exam"),
        "Tiếp nhận mẫu nước tiểu": ("nộp mẫu nước tiểu", "nộp mẫu tiểu", "urine sample", "urine specimen"),
        "Điện tâm đồ": ("ECG", "đo điện tim", "electrocardiogram", "EKG"),
        "Chụp nhũ ảnh": ("X-quang tuyến vú", "mammogram", "mammography"),
        "Nhận thuốc theo đơn": ("lấy thuốc", "nhận thuốc", "pick up my medication", "prescription pickup"),
        "Nội soi đại tràng": ("soi đại tràng", "colonoscopy"),
        "Nội soi dạ dày": ("soi dạ dày", "gastroscopy", "upper endoscopy"),
        "Lấy mẫu HbA1c": ("xét nghiệm HbA1c", "HbA1c test"),
        "Phân tích dáng chạy": ("đo dáng chạy", "running gait analysis"),
        # Quầy lễ tân – tư vấn ở cửa Trung tâm KSK Tổng quát, tầng 4.
        "Lễ tân và hướng dẫn": ("quầy lễ tân", "lễ tân", "reception", "reception desk", "information desk"),
        "Tư vấn dịch vụ và đặt lịch": (
            "quầy tư vấn", "tư vấn dịch vụ", "đặt lịch khám", "service advice desk", "book an appointment",
        ),
    }
    alias_rows = sync(
        session, ServiceAlias, scope, ("service_id", "normalized_alias"), [
            {"service_id": service_ids[name], "normalized_alias": normalize(alias), "alias": alias}
            for name, values in aliases.items() for alias in values
        ],
    )
    locations = sync(
        session, ServiceLocation, scope, ("service_id", "room_id"), [
            {"service_id": service_ids[name], "room_id": rooms[code,].id, "is_active": True}
            for code, name in service_by_room.items()
        ],
    )
    # Bác sĩ mô phỏng: mỗi người gắn với một phòng khám, tên có thể trùng.
    doctors = sync(
        session, Doctor, scope, ("code",), [
            {
                "code": doctor.code, "title": doctor.title, "name": doctor.name,
                "normalized_name": normalize(doctor.name),
                "room_id": rooms[doctor.room_code,].id, "is_active": True,
            }
            for doctor in doctor_slots()
        ],
    )
    # Ẩn phòng/dịch vụ mang mã cũ (vd. "4-04-11") sau khi đổi sang mã theo tầng.
    for model, keep in (
        (Doctor, doctors), (ServiceLocation, locations), (ServiceAlias, alias_rows), (Service, services), (Room, rooms),
    ):
        retire(session, model, scope, keep)
    return {
        "floors": len(floors), "departments": len(departments), "rooms": len(rooms),
        "services": len(services), "nodes": len(nodes), "edges": len(edges), "kiosks": len(kiosks),
        "doctors": len(doctors),
    }


def main() -> None:
    with SessionLocal.begin() as session:
        counts = seed(session)
    print(f"{SITE_CODE}: {counts}")


if __name__ == "__main__":
    main()
