"""Schematic coordinates and walking directions for the seeded navigation graph."""

from dataclasses import dataclass, field
from math import hypot

from .catalog import ENGLISH_ZONE_NAMES, ZONES, Zone

WIDTH, HEIGHT = 1200, 1070
FLOORS = (3, 4)
SPINE_X = WIDTH // 2
LANDMARKS = {
    "WC-A": (648, 63, "WC đầu hành lang", "the restroom at the top of the map"),
    "LIFT-A": (552, 218, "Thang máy A", "elevator A"),
    "STAIRS": (552, 473, "Cầu thang bộ", "the stairs"),
    "KIOSK": (648, 697, "Kiosk chỉ đường", "the wayfinding kiosk"),
    "LIFT-B": (552, 737, "Thang máy B", "elevator B"),
    "WC-B": (648, 1002, "WC cuối hành lang", "the restroom at the bottom of the map"),
}

NodeKey = tuple[int, str]


@dataclass(frozen=True)
class Point:
    x: int
    y: int
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
            cost = max(1, round(hypot(end.x - start.x, end.y - start.y) * 0.12))
        self.edges.extend((
            Edge(a, b, kind, cost, forward, forward_en),
            Edge(b, a, kind, cost, backward, backward_en),
        ))


@dataclass(frozen=True)
class RoomSlot:
    zone: Zone
    number: int
    name: str
    column: int
    bank: int

    @property
    def code(self) -> str:
        return f"{self.zone.code}-{self.number:02d}"

    @property
    def x(self) -> int:
        return SPINE_X + side_sign(self.zone) * (103 + 42 * self.column)

    @property
    def y(self) -> int:
        return zone_y(self.zone) + 16 * self.bank

    @property
    def row_label(self) -> str:
        return "hàng trên" if self.bank < 0 else "hàng dưới"

    @property
    def description(self) -> str:
        return (
            f"{self.name} tại {self.zone.name}, tầng {self.zone.floor}. "
            f"Từ cửa khu, theo hành lang nội bộ đến cụm cửa số {self.column + 1}, "
            f"tìm biển {self.code} ở {self.row_label} trên sơ đồ."
        )


def side_sign(zone: Zone) -> int:
    return -1 if zone.side == "west" else 1


def zone_y(zone: Zone) -> int:
    return 148 + 130 * zone.row


def room_slots(zone: Zone) -> tuple[RoomSlot, ...]:
    split = (len(zone.rooms) + 1) // 2
    return tuple(
        RoomSlot(zone, index + 1, name, index % split, -1 if index < split else 1)
        for index, name in enumerate(zone.rooms)
    )


def spine_code(y: int) -> str:
    return f"HALL-{y}"


def build_layout() -> Layout:
    layout = Layout()
    for floor in FLOORS:
        zones = [zone for zone in ZONES if zone.floor == floor]
        heights = sorted({zone_y(zone) for zone in zones} | {y for _, y, _, _ in LANDMARKS.values()})
        for y in heights:
            layout.nodes[floor, spine_code(y)] = Point(SPINE_X, y, "Hành lang chính")
        for a, b in zip(heights, heights[1:]):
            distance = round((b - a) * 0.12)
            layout.connect(
                (floor, spine_code(a)), (floor, spine_code(b)), "walk",
                f"Đi dọc hành lang chính khoảng {distance} m về phía cuối sơ đồ.",
                f"Đi dọc hành lang chính khoảng {distance} m về phía đầu sơ đồ.",
                forward_en=f"Follow the main corridor for about {distance} metres towards the bottom of the map.",
                backward_en=f"Follow the main corridor for about {distance} metres towards the top of the map.",
            )
        for code, (x, y, label, label_en) in LANDMARKS.items():
            layout.nodes[floor, code] = Point(x, y, label)
            side = "trái" if x < SPINE_X else "phải"
            side_en = "left" if x < SPINE_X else "right"
            layout.connect(
                (floor, spine_code(y)), (floor, code), "walk",
                f"Từ hành lang chính, đến {label} ở phía {side} trên sơ đồ.",
                f"Từ {label}, đi ra hành lang chính.",
                forward_en=f"From the main corridor, go to {label_en} on the {side_en} side of the map.",
                backward_en=f"From {label_en}, head back to the main corridor.",
            )
        for zone in zones:
            add_zone(layout, zone)
    for code in ("LIFT-A", "LIFT-B", "STAIRS"):
        kind = "stairs" if code == "STAIRS" else "elevator"
        _, _, label, label_en = LANDMARKS[code]
        layout.connect(
            (3, code), (4, code), kind,
            f"Dùng {label} lên tầng 4 và ra sảnh.",
            f"Dùng {label} xuống tầng 3 và ra sảnh.",
            forward_en=f"Take {label_en} up to floor 4 and exit into the lobby.",
            backward_en=f"Take {label_en} down to floor 3 and exit into the lobby.",
        )
    return layout


def add_zone(layout: Layout, zone: Zone) -> None:
    floor, y = zone.floor, zone_y(zone)
    entry = (floor, zone.entry_code)
    sign = side_sign(zone)
    side = "trái" if sign < 0 else "phải"
    side_en = "left" if sign < 0 else "right"
    name_en = ENGLISH_ZONE_NAMES[zone.code]
    layout.nodes[entry] = Point(SPINE_X + sign * 78, y, f"Lối vào {zone.name}")
    layout.connect(
        (floor, spine_code(y)), entry, "walk",
        f"Rời hành lang chính về phía {side} trên sơ đồ. Tìm biển số {zone.number} — {zone.name}.",
        f"Qua cửa {zone.name} để ra hành lang chính.",
        forward_en=f"Leave the main corridor on the {side_en} side of the map. Look for sign {zone.number}, {name_en}.",
        backward_en=f"Exit {name_en} to reach the main corridor.",
    )
    slots = room_slots(zone)
    previous = entry
    for slot in slots[:(len(slots) + 1) // 2]:
        junction = (floor, f"AISLE-{zone.code}-{slot.column + 1:02d}")
        layout.nodes[junction] = Point(slot.x, y, f"Cụm cửa {slot.column + 1} · {zone.name}")
        layout.connect(
            previous, junction, "walk",
            f"Đi sâu vào hành lang {zone.name} đến cụm cửa số {slot.column + 1}.",
            f"Đi về phía lối vào {zone.name}.",
            forward_en=f"Follow the corridor inside {name_en} to door group {slot.column + 1}.",
            backward_en=f"Head back towards the entrance to {name_en}.",
        )
        previous = junction
    for slot in slots:
        entrance = (floor, slot.code)
        junction = (floor, f"AISLE-{zone.code}-{slot.column + 1:02d}")
        layout.nodes[entrance] = Point(slot.x, slot.y, f"{slot.code} · {slot.name}")
        row_en = "upper row" if slot.bank < 0 else "lower row"
        layout.connect(
            junction, entrance, "walk",
            f"Tại cụm cửa số {slot.column + 1}, tìm biển {slot.code} ở {slot.row_label}: {slot.name}.",
            f"Rời phòng {slot.code}, trở lại hành lang nội bộ.",
            forward_en=f"At door group {slot.column + 1}, look for room {slot.code} in the {row_en} on the map.",
            backward_en=f"Leave room {slot.code} and return to the corridor.",
        )
