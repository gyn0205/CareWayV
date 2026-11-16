"""Display geometry for the same synthetic floor coordinates used by the seed."""

from app.schema.wayfinding import FloorPlan, MapLandmark, MapRoom, MapZone

from .catalog import ENGLISH_ZONE_NAMES, ZONES
from .layout import FLOORS, HEIGHT, LANDMARKS, SPINE_X, WIDTH, room_slots, side_sign, zone_y


def demo_floor_plan(floor_id: int, level: int) -> FloorPlan | None:
    if level not in FLOORS:
        return None
    ys = [y for _, y, _, _ in LANDMARKS.values()]
    corridors = [(SPINE_X, min(ys), SPINE_X, max(ys))]
    landmarks = []
    for code, (x, y, _, _) in LANDMARKS.items():
        kind = {
            "LIFT": "elevator", "STAIRS": "stairs", "WC": "restroom", "KIOSK": "kiosk",
        }[code.split("-")[0]]
        landmarks.append(MapLandmark(code=code, x=x, y=y, kind=kind))
        corridors.append((SPINE_X, y, x, y))

    zones, rooms = [], []
    for zone in (zone for zone in ZONES if zone.floor == level):
        slots = room_slots(zone)
        y = zone_y(zone)
        sign = side_sign(zone)
        near = SPINE_X + sign * 74
        far = SPINE_X + sign * max(230, max(abs(slot.x - SPINE_X) for slot in slots) + 24)
        zones.append(MapZone(
            code=zone.code, name=zone.name, name_en=ENGLISH_ZONE_NAMES[zone.code],
            x=min(near, far), y=y - 60, width=abs(far - near), height=120,
        ))
        last = max(slots, key=lambda slot: slot.column)
        corridors.append((SPINE_X, y, last.x, y))
        for slot in slots:
            rooms.append(MapRoom(
                code=slot.code, x=slot.x - 19, y=slot.y - 35 if slot.bank < 0 else slot.y,
                width=38, height=35, door_side="south" if slot.bank < 0 else "north",
            ))
    return FloorPlan(
        floor_id=floor_id, width=WIDTH, height=HEIGHT, corridors=corridors,
        zones=zones, rooms=rooms, landmarks=landmarks,
    )
