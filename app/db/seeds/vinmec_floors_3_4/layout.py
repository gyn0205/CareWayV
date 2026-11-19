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
    number: int     # số thứ tự phòng trên cả tầng (1, 2, 3…)
    name: str
    aisle: int      # hành lang nội bộ thứ mấy (0 = trên cùng)
    column: int     # cột thứ mấy tính từ lối vào
    bank: int       # -1 = dãy trên (cửa quay xuống), 1 = dãy dưới (cửa quay lên)
    columns: int    # số cột của hành lang nội bộ này

    @property
    def code(self) -> str:
        # Mã phòng theo tầng: "4-001", "4-002"…
        return f"{self.zone.floor}-{self.number:03d}"

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
    # Đánh số nối tiếp các khu trước đó trên cùng tầng.
    offset = sum(len(other.rooms) for other in ZONES if other.floor == zone.floor and other.number < zone.number)
    slots = []
    for aisle in range(aisles):
        names = zone.rooms[aisle * per_aisle:(aisle + 1) * per_aisle]
        split = (len(names) + 1) // 2
        for index, name in enumerate(names):
            slots.append(RoomSlot(
                zone, offset + aisle * per_aisle + index + 1, name, aisle,
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
            f"Đi {label} lên tầng 4.",
            f"Đi {label} xuống tầng 3.",
            forward_en=f"Take {label_en} up to floor 4.",
            backward_en=f"Take {label_en} down to floor 3.",
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
    # Câu chỉ đường (rẽ trái/phải, bao nhiêu mét) do service ghép theo hướng người đi;
    # cạnh ở đây chỉ mang cụm "qua mốc nào / đến đâu", "" = đoạn hành lang trơn.
    for lane, ys in stops.items():
        for y in ys:
            layout.nodes[floor, lane_code(lane, y)] = Point(lane_x(lane), y, f"Hành lang chính (bên {side_vi[lane]})")
        for a, b in zip(ys, ys[1:]):
            # Mốc trong lõi mà đoạn này đi ngang qua (thang máy, cầu thang…), để khách đối chiếu.
            passed = [mark for mark in landmarks(floor).values() if mark[2] != "kiosk" and a < mark[1] < b]
            vi = "qua " + " và ".join(mark[3] for mark in passed) if passed else ""
            en = "past " + " and ".join(mark[4] for mark in passed) if passed else ""
            layout.connect(
                (floor, lane_code(lane, a)), (floor, lane_code(lane, b)), "walk", vi, vi,
                forward_en=en, backward_en=en,
            )
    # Lối băng ngang giữa các khối lõi; có nút giữa để vào thang máy, thang bộ.
    # Kiosk đứng ngay giữa lối băng ngang (trước bảng sơ đồ) nên chính nó là nút giữa.
    middles = {}
    for y in CROSSINGS:
        links = {code: link for code, (*_, link) in landmarks(floor).items()}
        kiosk = next((code for code, link in links.items() if link == f"crossing-{y}"), None)
        if kiosk:
            x, ly, _, label, *_ = landmarks(floor)[kiosk]
            layout.nodes[floor, kiosk] = Point(x, ly, label)
            middles[y] = (floor, kiosk)
        elif f"mid-{y}" in links.values():
            layout.nodes[floor, lane_code("M", y)] = Point(CENTER_X, y, "Sảnh giữa hành lang")
            middles[y] = (floor, lane_code("M", y))
        chain = [(floor, lane_code("W", y)), *([middles[y]] if y in middles else []), (floor, lane_code("E", y))]
        for a, b in zip(chain, chain[1:]):
            layout.connect(
                a, b, "walk",
                "sang phía bên kia hành lang", "sang phía bên kia hành lang",
                forward_en="across to the other side of the corridor",
                backward_en="across to the other side of the corridor",
            )
    # Mốc trong lõi: thang máy, thang bộ, WC.
    for code, (x, y, _, label, label_en, link) in landmarks(floor).items():
        if link.startswith("crossing-"):
            continue
        layout.nodes[floor, code] = Point(x, y, label)
        source = (floor, lane_code("W", y)) if link == "west" else middles[int(link.removeprefix("mid-"))]
        layout.connect(
            source, (floor, code), "walk", f"đến {label}", "ra hành lang",
            forward_en=f"to {label_en}", backward_en="out to the corridor",
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
    # Quầy không có cửa riêng: "đến quầy…" thay vì "vào cửa…".
    door, door_en = (f"vào cửa {zone.sign_label}", f"into {area_en}") if zone.signed else (
        f"đến {zone.sign_label}", f"to the {name_en}")
    if door_y <= HALL_TOP or door_y >= HALL_BOTTOM:
        top = door_y <= HALL_TOP
        source = (floor, lane_code(lane, stops[0] if top else stops[-1]))
        forward = f"đến cuối hành lang là cửa {zone.sign_label}"
        forward_en = f"to the end of the corridor, where you enter {area_en}"
    else:
        source = (floor, lane_code(lane, door_y))
        forward, forward_en = door, door_en
    layout.connect(
        source, entry, "walk", forward, "ra hành lang chính",
        forward_en=forward_en, backward_en="out to the main corridor",
    )

    # Lối đi trong khu từ cửa tới hành lang nội bộ (đoạn trơn, không cần nói gì thêm).
    previous = entry
    for index, (x, y) in enumerate(plan.path[1:], start=1):
        key = (floor, f"PATH-{zone.code}-{index}")
        layout.nodes[key] = Point(x, y, f"Lối đi trong {zone.name}")
        layout.connect(previous, key, "walk", "", "", forward_en="", backward_en="")
        previous = key

    # Lối vào thứ hai (ví dụ hai lối hai bên quầy lễ tân khu KSK): nối vào cuối lối chính.
    if plan.side_door:
        doors = [(floor, f"DOOR-{zone.code}-2")] + [
            (floor, f"DOOR-{zone.code}-2-{index}") for index in range(1, len(plan.side_door))
        ]
        for key, (x, y) in zip(doors, plan.side_door):
            layout.nodes[key] = Point(x, y, f"Lối vào thứ hai · {zone.name}")
        layout.connect(
            (floor, lane_code(lane, plan.side_door[0][1])), doors[0], "walk",
            f"vào lối bên của {zone.sign_label}", "ra hành lang chính",
            forward_en=f"into the side entrance of {area_en}", backward_en="out to the main corridor",
        )
        for a, b in zip([*doors, previous], [*doors[1:], previous]):
            layout.connect(a, b, "walk", "", "", forward_en="", backward_en="")

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
        layout.connect(a, b, "walk", "", "", forward_en="", backward_en="")

    # Mỗi cột cửa là một nút trên hành lang nội bộ; phòng nối từ nút cột.
    slots = room_slots(zone)
    for aisle in range(plan.aisles):
        previous = heads[aisle]
        for slot in sorted({s.column: s for s in slots if s.aisle == aisle and s.bank < 0}.values(), key=lambda s: s.column):
            key = (floor, slot.junction_code)
            layout.nodes[key] = Point(*slot.junction, f"Cụm cửa {slot.column + 1} · {zone.name}")
            # Người thật nhìn số trên cửa, không đếm "cụm cửa" → quãng đường do service nói.
            layout.connect(previous, key, "walk", "", "", forward_en="", backward_en="")
            previous = key
    for slot in slots:
        entrance = (floor, slot.code)
        layout.nodes[entrance] = Point(*slot.door, f"{slot.code} · {slot.name}")
        # Rẽ trái hay phải vào phòng do service tính theo chiều đi trong hành lang.
        if zone.signed:
            forward, forward_en = f"đến phòng {slot.code} — {slot.name}", f"to room {slot.code}"
        else:
            forward, forward_en = f"đến quầy {slot.code} — {slot.name}", f"to desk {slot.code}"
        layout.connect(
            (floor, slot.junction_code), entrance, "walk", forward, "",
            forward_en=forward_en, backward_en="",
        )
