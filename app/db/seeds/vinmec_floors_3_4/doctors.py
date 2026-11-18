"""Danh sách bác sĩ mô phỏng (~80 bác sĩ mỗi tầng), cố ý có tên trùng để thử hỏi lại."""

from dataclasses import dataclass
from random import Random

from .catalog import ZONES
from .layout import FLOORS, room_slots

PER_FLOOR = 80
TITLES = ("BS.", "BS.", "BS.CKI", "BS.CKII", "ThS.BS.", "ThS.BS.", "TS.BS.", "PGS.TS.BS.")
SURNAMES = (
    "Nguyễn", "Nguyễn", "Nguyễn", "Trần", "Trần", "Lê", "Lê", "Phạm", "Hoàng", "Huỳnh",
    "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý",
)
MALE = (
    ("Văn", "Đức", "Minh", "Quốc", "Hữu", "Thành", "Công", "Anh"),
    ("An", "Bình", "Cường", "Dũng", "Hùng", "Hải", "Huy", "Khánh", "Long", "Nam",
     "Phúc", "Quang", "Sơn", "Thắng", "Tuấn", "Việt"),
)
FEMALE = (
    ("Thị", "Thu", "Ngọc", "Thanh", "Minh", "Hồng", "Phương", "Bích"),
    ("Anh", "Hà", "Hằng", "Hoa", "Hương", "Lan", "Linh", "Mai", "Ngân", "Nhung",
     "Oanh", "Phương", "Quỳnh", "Thảo", "Trang", "Yến"),
)
# Trùng họ tên đầy đủ, ghi rõ (tầng, số khu) để biết trước từng kiểu trùng:
# khác khoa cùng tầng, khác tầng, và cả hai người cùng tên trong một khoa.
DUPLICATES = (
    ("Nguyễn Văn Hùng", ((3, 1), (3, 7), (4, 6))),
    ("Trần Thị Lan", ((3, 5), (4, 2), (4, 9))),
    ("Lê Minh Tuấn", ((3, 1), (3, 1))),
    ("Phạm Thu Hà", ((4, 4), (4, 5))),
    ("Nguyễn Thị Mai", ((3, 6), (3, 11), (4, 8), (4, 13))),
    ("Hoàng Quốc Việt", ((3, 8), (4, 10))),
    ("Đỗ Thị Hương", ((3, 9), (4, 7))),
    ("Vũ Đức Anh", ((3, 12), (4, 12))),
)
# Phòng có bác sĩ ngồi khám/đọc kết quả; khu không có phòng như vậy thì dùng mọi phòng.
CLINICAL = ("Khám", "Tư vấn", "Siêu âm", "Nội soi", "Đọc", "Chọc", "Đánh giá", "Theo dõi")


@dataclass(frozen=True)
class DoctorSlot:
    code: str
    title: str
    name: str
    room_code: str


def doctor_slots() -> tuple[DoctorSlot, ...]:
    rng = Random(34)  # cố định để chạy seed lại vẫn ra đúng danh sách cũ
    used = {name for name, _ in DUPLICATES}

    def fresh_name() -> str:
        while True:
            middles, givens = rng.choice((MALE, FEMALE))
            name = f"{rng.choice(SURNAMES)} {rng.choice(middles)} {rng.choice(givens)}"
            if name not in used:
                used.add(name)
                return name

    slots = []
    for floor in FLOORS:
        # Nhà thuốc và quầy thanh toán/lễ tân không có bác sĩ.
        zones = [z for z in ZONES if z.floor == floor and not z.name.startswith(("Nhà thuốc", "Quầy"))]
        base, extra = divmod(PER_FLOOR, len(zones))
        for index, zone in enumerate(zones):
            names = [name for name, places in DUPLICATES for place in places if place == (floor, zone.number)]
            names += [fresh_name() for _ in range(base + (index < extra) - len(names))]
            rooms = [slot for slot in room_slots(zone) if slot.name.startswith(CLINICAL)] or list(room_slots(zone))
            for offset, name in enumerate(names):
                slots.append(DoctorSlot(
                    code=f"BS-{floor}-{len(slots) % PER_FLOOR + 1:03d}",
                    # Người trùng tên trong cùng khoa vẫn khác học hàm để phân biệt.
                    title=TITLES[(offset + len(slots)) % len(TITLES)],
                    name=name,
                    room_code=rooms[offset % len(rooms)].code,
                ))
    return tuple(slots)
