"""Hình vẽ mặt bằng tầng gửi cho frontend, dùng chung tọa độ với đồ thị điều hướng."""

from app.schema.wayfinding import FloorPlan, MapBlock, MapLandmark, MapRoom, MapSign, MapZone

from .catalog import ENGLISH_ZONE_NAMES, ZONES
from .geometry import (
    CROSSINGS, EAST_LANE, EXITS, FLOORS, HALL, HEIGHT, SHAPES, SUNROOMS, core_blocks, landmarks,
    WEST_LANE, WIDTH,
)
from .layout import room_slots


def demo_floor_plan(floor_id: int, level: int) -> FloorPlan | None:
    if level not in FLOORS:
        return None
    x1, y1, x2, y2 = HALL
    # Hai làn đi bộ và các lối băng ngang (dùng cho bản đồ cũ và khung nhìn).
    corridors = [(WEST_LANE, y1, WEST_LANE, y2), (EAST_LANE, y1, EAST_LANE, y2)]
    corridors += [(WEST_LANE, y, EAST_LANE, y) for y in CROSSINGS]
    marks = [
        MapLandmark(code=code, x=x, y=y, kind=kind)
        for code, (x, y, kind, *_) in landmarks(level).items()
    ]
    blocks = [MapBlock(kind="sunroom", x=x, y=y, width=w, height=h) for x, y, w, h in SUNROOMS[level]]
    blocks += [MapBlock(kind=kind, x=x, y=y, width=w, height=h) for kind, x, y, w, h in core_blocks(level)]

    zones, rooms = [], []
    for zone in (zone for zone in ZONES if zone.floor == level):
        shape = SHAPES[zone.code]
        x, y, width, height = shape.bounds
        rx, ry, rw, rh = shape.rooms
        zones.append(MapZone(
            code=zone.code, name=zone.name, name_en=ENGLISH_ZONE_NAMES[zone.code],
            x=x, y=y, width=width, height=height, tone=shape.tone,
            number=zone.number if zone.signed else None,  # quầy lễ tân không có số trên bảng
            outline=list(shape.outline), label_x=rx + rw // 2, label_y=ry + rh // 2,
        ))
        for slot in room_slots(zone):
            left, top, room_width, room_height = slot.rect
            rooms.append(MapRoom(
                code=slot.code, zone=zone.code, x=left, y=top, width=room_width, height=room_height,
                door_side="south" if slot.bank < 0 else "north",
            ))
    return FloorPlan(
        floor_id=floor_id, width=WIDTH, height=HEIGHT, corridors=corridors,
        zones=zones, rooms=rooms, landmarks=marks,
        hall=[(x1, y1), (x2, y1), (x2, y2), (x1, y2)], blocks=blocks,
        exits=[MapSign(x=x, y=y) for x, y in EXITS[level]],
    )
