"""Tọa độ và câu chỉ đường cho đồ thị điều hướng, dựng từ mặt bằng trong geometry.py."""

from dataclasses import dataclass, field
from math import ceil, hypot

from .catalog import ENGLISH_ZONE_NAMES, ZONES, Zone
from .geometry import (
    CENTER_X, CROSSINGS, EAST_LANE, FLOORS, HALL_BOTTOM, HALL_TOP, HEIGHT, LANDMARKS, SHAPES, landmarks,
    WEST_LANE, WIDTH, Shape,
)

__all__ = ["FLOORS", "HEIGHT", "LANDMARKS", "WIDTH", "Layout", "RoomSlot", "build_layout", "room_slots"]

NodeKey = tuple[int, str]
AISLE_WIDTH = 12


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    label: str


@dataclass(frozen=True)
class Edge:
    origin: NodeKey
    destination: NodeKey
    kind: str
    cost: int
    instruction: str
    instruction_en: str


@dataclass
class Layout:
    nodes: dict[NodeKey, Point] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def connect(
        self, a: NodeKey, b: NodeKey, kind: str, forward: str, backward: str,
        *, forward_en: str, backward_en: str,
    ) -> None:
        start, end = self.nodes[a], self.nodes[b]
        cost = {"elevator": 42, "stairs": 33}.get(kind)
        if cost is None:
            # Khoảng 0,12 giây cho mỗi đơn vị bản đồ.
            cost = max(1, round(hypot(end.x - start.x, end.y - start.y) * 0.12))
        self.edges.extend((
            Edge(a, b, kind, cost, forward, forward_en),
            Edge(b, a, kind, cost, backward, backward_en),
        ))


def shape(zone: Zone) -> Shape:
    return SHAPES[zone.code]


def near_east(zone: Zone) -> bool:
    """Lối vào nằm ở mép phải vùng phòng → các cột phòng đánh số từ phải sang trái."""
    x, _, width, _ = shape(zone).rooms
    return shape(zone).path[-1][0] > x + width / 2


def aisle_ys(zone: Zone) -> list[int]:
    _, y, _, height = shape(zone).rooms
    band = height // shape(zone).aisles
    return [y + band * index + band // 2 for index in range(shape(zone).aisles)]


@dataclass(frozen=True)
class RoomSlot:
    zone: Zone
    number: int
    name: str
    aisle: int      # hành lang nội bộ thứ mấy (0 = trên cùng)
    column: int     # cột thứ mấy tính từ lối vào
    bank: int       # -1 = dãy trên (cửa quay xuống), 1 = dãy dưới (cửa quay lên)
    columns: int    # số cột của hành lang nội bộ này

    @property
    def code(self) -> str:
        return f"{self.zone.code}-{self.number:02d}"

    @property
    def rect(self) -> tuple[int, int, int, int]:
        """Hình chữ nhật của phòng (x, y, rộng, cao)."""
        x0, _, width, height = shape(self.zone).rooms
        band = height // shape(self.zone).aisles
        column_width = width / self.columns
        index = self.columns - 1 - self.column if near_east(self.zone) else self.column
        left = round(x0 + column_width * index + 2)
        right = round(x0 + column_width * (index + 1) - 2)
        room_height = (band - AISLE_WIDTH) // 2 - 3
        aisle = aisle_ys(self.zone)[self.aisle]
        top = aisle - AISLE_WIDTH // 2 - room_height if self.bank < 0 else aisle + AISLE_WIDTH // 2
        return left, top, right - left, room_height

    @property
    def door(self) -> tuple[float, float]:
        left, top, width, height = self.rect
        return left + width / 2, top + height if self.bank < 0 else top

    @property
    def junction(self) -> tuple[float, float]:
        return self.door[0], aisle_ys(self.zone)[self.aisle]

    @property
    def junction_code(self) -> str:
        if shape(self.zone).aisles == 1:
            return f"AISLE-{self.zone.code}-{self.column + 1:02d}"
        return f"AISLE-{self.zone.code}-{self.aisle + 1}-{self.column + 1:02d}"

    @property
    def row_label(self) -> str:
        return "hàng trên" if self.bank < 0 else "hàng dưới"

    @property
    def group_label(self) -> str:
        if shape(self.zone).aisles == 1:
            return f"cụm cửa số {self.column + 1}"
        return f"cụm cửa số {self.column + 1} của dãy {self.aisle + 1}"

    @property
    def description(self) -> str:
        if not self.zone.signed:
            # Quầy: mô tả vị trí theo quầy, không theo dãy phòng.
            return (
                f"{self.name} tại {self.zone.name}, tầng {self.zone.floor}, "
                f"ngay cửa Trung tâm Khám Sức khỏe Tổng quát, quay ra hành lang chính."
            )
        return (
            f"{self.name} tại {self.zone.name}, tầng {self.zone.floor}. "
            f"Từ cửa {self.zone.sign_label}, theo hành lang nội bộ đến {self.group_label}, "
            f"tìm biển {self.code} ở {self.row_label} trên sơ đồ."
        )


def room_slots(zone: Zone) -> tuple[RoomSlot, ...]:
    aisles = shape(zone).aisles
    per_aisle = ceil(len(zone.rooms) / aisles)
    slots = []
    for aisle in range(aisles):
        names = zone.rooms[aisle * per_aisle:(aisle + 1) * per_aisle]
        split = (len(names) + 1) // 2
        for index, name in enumerate(names):
            slots.append(RoomSlot(
                zone, aisle * per_aisle + index + 1, name, aisle,
                index % split, -1 if index < split else 1, split,
            ))
    return tuple(slots)


def lane_code(lane: str, y: int) -> str:
    return f"HALL-{lane}-{y}"


def lane_x(lane: str) -> int:
    return {"W": WEST_LANE, "M": CENTER_X, "E": EAST_LANE}[lane]


def entry_lane(zone: Zone) -> str:
    return "W" if shape(zone).path[0][0] < CENTER_X else "E"


def build_layout() -> Layout:
    layout = Layout()
    for floor in FLOORS:
        add_hall(layout, floor)
        for zone in ZONES:
            if zone.floor == floor:
                add_zone(layout, zone)
    for code in ("LIFT-A", "LIFT-B", "STAIRS"):
        kind = "stairs" if code == "STAIRS" else "elevator"
        label, label_en = LANDMARKS[code][3:5]
        layout.connect(
            (3, code), (4, code), kind,
            f"Dùng {label} lên tầng 4 và ra sảnh.",
            f"Dùng {label} xuống tầng 3 và ra sảnh.",
            forward_en=f"Take {label_en} up to floor 4 and exit into the lobby.",
            backward_en=f"Take {label_en} down to floor 3 and exit into the lobby.",
        )
    return layout


def lane_stops(floor: int) -> dict[str, list[int]]:
    """Các tung độ có nút trên mỗi làn: lối băng ngang, mốc và cửa khu bên hông."""
    stops = {"W": set(CROSSINGS), "E": set(CROSSINGS)}
    for x, y, _, _, _, link in landmarks(floor).values():
        if link == "west":
            stops["W"].add(y)
    for zone in ZONES:
        # Cửa chính và (nếu có) cửa thứ hai bên hông của khu.
        for door_x, door_y in (shape(zone).path[0], *shape(zone).side_door[:1]):
            if zone.floor == floor and HALL_TOP < door_y < HALL_BOTTOM:
                stops[entry_lane(zone)].add(door_y)
    return {lane: sorted(ys) for lane, ys in stops.items()}


def add_hall(layout: Layout, floor: int) -> None:
    stops = lane_stops(floor)
    side_vi = {"W": "trái", "E": "phải"}
    side_en = {"W": "left", "E": "right"}
    # Hai làn đi bộ dọc hai bên lõi hành lang.
    for lane, ys in stops.items():
        for y in ys:
            layout.nodes[floor, lane_code(lane, y)] = Point(lane_x(lane), y, f"Hành lang chính (bên {side_vi[lane]})")
        for a, b in zip(ys, ys[1:]):
            distance = round((b - a) * 0.12)
            layout.connect(
                (floor, lane_code(lane, a)), (floor, lane_code(lane, b)), "walk",
                f"Đi dọc hành lang chính (bên {side_vi[lane]}) khoảng {distance} m về phía cuối sơ đồ.",
                f"Đi dọc hành lang chính (bên {side_vi[lane]}) khoảng {distance} m về phía đầu sơ đồ.",
                forward_en=f"Follow the {side_en[lane]} side of the main corridor for about {distance} metres towards the bottom of the map.",
                backward_en=f"Follow the {side_en[lane]} side of the main corridor for about {distance} metres towards the top of the map.",
            )
    # Lối băng ngang giữa các khối lõi; có nút giữa để vào thang máy, thang bộ, kiosk.
    for y in CROSSINGS:
        stations = ["W"]
        if any(link in (f"mid-{y}", f"crossing-{y}") for *_, link in landmarks(floor).values()):
            layout.nodes[floor, lane_code("M", y)] = Point(CENTER_X, y, "Sảnh giữa hành lang")
            stations.append("M")
        stations.append("E")
        chain = [(floor, lane_code(lane, y)) for lane in stations]
        for code, (x, ly, _, label, label_en, link) in landmarks(floor).items():
            if link == f"crossing-{y}":
                layout.nodes[floor, code] = Point(x, ly, label)
                chain.insert(1, (floor, code))
        for a, b in zip(chain, chain[1:]):
            layout.connect(
                a, b, "walk",
                "Băng ngang hành lang sang phía bên phải trên sơ đồ.",
                "Băng ngang hành lang sang phía bên trái trên sơ đồ.",
                forward_en="Cross the corridor to the right side of the map.",
                backward_en="Cross the corridor to the left side of the map.",
            )
    # Mốc trong lõi: thang máy, thang bộ, WC.
    for code, (x, y, _, label, label_en, link) in landmarks(floor).items():
        if link.startswith("crossing-"):
            continue
        layout.nodes[floor, code] = Point(x, y, label)
        if link == "west":
            source = (floor, lane_code("W", y))
            forward, forward_en = f"Rẽ vào {label} trong lõi hành lang.", f"Turn into {label_en} in the corridor core."
        else:
            source = (floor, lane_code("M", int(link.removeprefix("mid-"))))
            forward, forward_en = f"Đi tới {label} ở giữa hành lang.", f"Walk to {label_en} in the middle of the corridor."
        layout.connect(
            source, (floor, code), "walk", forward, f"Từ {label}, đi ra hành lang chính.",
            forward_en=forward_en, backward_en=f"From {label_en}, head back to the main corridor.",
        )


def add_zone(layout: Layout, zone: Zone) -> None:
    floor = zone.floor
    plan = shape(zone)
    name_en = ENGLISH_ZONE_NAMES[zone.code]
    area_en = f"area {zone.number}, {name_en}" if zone.signed else name_en
    lane = entry_lane(zone)
    stops = lane_stops(floor)[lane]
    door_x, door_y = plan.path[0]
    entry = (floor, zone.entry_code)
    layout.nodes[entry] = Point(door_x, door_y, f"Lối vào {zone.name}")

    # Nối cửa khu với làn hành lang: cửa bên hông hoặc cửa ở đầu/cuối hành lang.
    if door_y <= HALL_TOP or door_y >= HALL_BOTTOM:
        top = door_y <= HALL_TOP
        source = (floor, lane_code(lane, stops[0] if top else stops[-1]))
        where, where_en = ("đầu", "top") if top else ("cuối", "bottom")
        forward = f"Đi hết hành lang chính về phía {where} sơ đồ, vào {zone.sign_label}."
        forward_en = f"Walk to the {where_en} end of the main corridor and enter {area_en}."
    else:
        source = (floor, lane_code(lane, door_y))
        side, side_en = ("trái", "left") if lane == "W" else ("phải", "right")
        forward = f"Rẽ {side} vào cửa {zone.sign_label}."
        forward_en = f"Turn {side_en} into {area_en}."
    layout.connect(
        source, entry, "walk", forward, f"Qua cửa {zone.name} để ra hành lang chính.",
        forward_en=forward_en, backward_en=f"Exit {name_en} to reach the main corridor.",
    )

    # Lối đi trong khu từ cửa tới hành lang nội bộ.
    previous = entry
    for index, (x, y) in enumerate(plan.path[1:], start=1):
        key = (floor, f"PATH-{zone.code}-{index}")
        layout.nodes[key] = Point(x, y, f"Lối đi trong {zone.name}")
        layout.connect(
            previous, key, "walk",
            f"Đi theo lối chính trong {zone.name}.", f"Đi về phía cửa {zone.name}.",
            forward_en=f"Follow the main walkway inside {name_en}.",
            backward_en=f"Head back towards the entrance to {name_en}.",
        )
        previous = key

    # Lối vào thứ hai (ví dụ hai lối hai bên quầy lễ tân khu KSK): nối vào cuối lối chính.
    if plan.side_door:
        side, side_en = ("trái", "left") if lane == "W" else ("phải", "right")
        doors = [(floor, f"DOOR-{zone.code}-2")] + [
            (floor, f"DOOR-{zone.code}-2-{index}") for index in range(1, len(plan.side_door))
        ]
        for key, (x, y) in zip(doors, plan.side_door):
            layout.nodes[key] = Point(x, y, f"Lối vào thứ hai · {zone.name}")
        layout.connect(
            (floor, lane_code(lane, plan.side_door[0][1])), doors[0], "walk",
            f"Rẽ {side} vào lối bên của {zone.sign_label}.", f"Qua lối bên của {zone.name} để ra hành lang chính.",
            forward_en=f"Turn {side_en} into the side entrance of {area_en}.",
            backward_en=f"Exit {name_en} through the side entrance to reach the main corridor.",
        )
        for a, b in zip([*doors, previous], [*doors[1:], previous]):
            layout.connect(
                a, b, "walk",
                f"Đi theo lối bên trong {zone.name}.", f"Đi về phía lối bên của {zone.name}.",
                forward_en=f"Follow the side walkway inside {name_en}.",
                backward_en=f"Head back towards the side entrance of {name_en}.",
            )

    # Xương sống nội bộ: nối điểm cuối lối vào với đầu mỗi hành lang nội bộ.
    spine_x, spine_y = plan.path[-1]
    heads = {}
    stations = [(spine_y, previous)]
    for aisle, y in enumerate(aisle_ys(zone)):
        if y == spine_y:
            heads[aisle] = previous
            continue
        key = (floor, f"SPINE-{zone.code}-{aisle + 1}")
        layout.nodes[key] = Point(spine_x, y, f"Dãy phòng {aisle + 1} · {zone.name}")
        heads[aisle] = key
        stations.append((y, key))
    stations.sort()
    for (_, a), (_, b) in zip(stations, stations[1:]):
        layout.connect(
            a, b, "walk",
            f"Đi tiếp theo hành lang nội bộ của {zone.name}.", f"Quay lại hành lang nội bộ của {zone.name}.",
            forward_en=f"Continue along the inner corridor of {name_en}.",
            backward_en=f"Return along the inner corridor of {name_en}.",
        )

    # Mỗi cột cửa là một nút trên hành lang nội bộ; phòng nối từ nút cột.
    slots = room_slots(zone)
    for aisle in range(plan.aisles):
        previous = heads[aisle]
        for slot in sorted({s.column: s for s in slots if s.aisle == aisle and s.bank < 0}.values(), key=lambda s: s.column):
            key = (floor, slot.junction_code)
            layout.nodes[key] = Point(*slot.junction, f"Cụm cửa {slot.column + 1} · {zone.name}")
            if zone.signed:
                forward = f"Đi sâu vào hành lang {zone.name} đến {slot.group_label}."
                forward_en = f"Follow the corridor inside {name_en} to door group {slot.column + 1}."
            else:
                # Quầy (không phải khu khám): chỉ cần bước tới mặt quầy.
                forward, forward_en = f"Bước tới mặt {zone.name}.", f"Step up to the {name_en}."
            layout.connect(
                previous, key, "walk", forward, f"Đi về phía lối vào {zone.name}.",
                forward_en=forward_en, backward_en=f"Head back towards the entrance to {name_en}.",
            )
            previous = key
    for slot in slots:
        entrance = (floor, slot.code)
        layout.nodes[entrance] = Point(*slot.door, f"{slot.code} · {slot.name}")
        row_en = "upper row" if slot.bank < 0 else "lower row"
        if zone.signed:
            forward = f"Tại {slot.group_label}, tìm biển {slot.code} ở {slot.row_label}: {slot.name}."
            forward_en = f"At door group {slot.column + 1}, look for room {slot.code} in the {row_en} on the map."
        else:
            # Khách quay mặt vào quầy (hướng tây): phía trên bản đồ nằm bên tay phải.
            side_en = "right" if slot.bank < 0 else "left"
            side = "phải" if slot.bank < 0 else "trái"
            forward = f"Gặp nhân viên ở bên {side} quầy ({slot.code}): {slot.name}."
            forward_en = f"Speak to the staff on the {side_en} side of the desk ({slot.code})."
        layout.connect(
            (floor, slot.junction_code), entrance, "walk", forward,
            f"Rời {slot.code}, trở lại hành lang.",
            forward_en=forward_en, backward_en=f"Leave {slot.code} and return to the corridor.",
        )
