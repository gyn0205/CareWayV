"""Mặt bằng tầng 3–4, vẽ lại theo bảng "Mặt bằng tầng" treo ở sảnh thang máy.

Tọa độ là đơn vị mô phỏng (không phải mét). Hai tầng dùng chung lõi hành lang
để thang máy thẳng hàng giữa các tầng. Thang bộ nằm ở cuối giếng sảnh (cả hai tầng),
ngay phía trên kiosk "Bạn đang ở đây".
"""

from dataclasses import dataclass

WIDTH, HEIGHT = 1000, 1080
FLOORS = (3, 4)

# Hành lang chính (màu vàng trên bảng): hình chữ nhật dọc giữa tầng.
HALL = (420, 190, 580, 932)
HALL_TOP, HALL_BOTTOM = HALL[1], HALL[3]
WEST_LANE, EAST_LANE, CENTER_X = 438, 562, 500

# Các lối băng ngang giữa hai làn đi bộ, nằm giữa các khối lõi.
CROSSINGS = (305, 410, 740, 840)

# Lõi giữa hành lang, từ trên xuống: WC, thang thoát hiểm, thang máy A,
# giếng sảnh có thang bộ, thang máy B, thang thoát hiểm, WC.
CORE_BLOCKS = (
    ("restroom", 462, 198, 76, 46),
    ("exit_stair", 462, 252, 76, 32),
    ("lift", 462, 326, 76, 64),
    ("void", 456, 428, 88, 292),
    ("lift", 462, 760, 76, 62),
    ("exit_stair", 462, 850, 76, 28),
    ("restroom", 462, 886, 76, 42),
    # Bảng sơ đồ tầng: 2 bảng mỗi tầng (4 bảng cả hai tầng), sát mép trên và mép dưới
    # giếng sảnh (giếng 428–720); mỗi bảng là một vị trí kiosk. Sau thang máy không có bảng.
    ("board", 482, 418, 36, 8),
    ("board", 482, 722, 36, 8),
)

# Thang bộ ở cuối giếng sảnh (tách theo tầng để dễ chỉnh riêng từng tầng).
ESCALATORS = {
    3: ("escalator", 482, 632, 36, 70),
    4: ("escalator", 482, 632, 36, 70),
}


def core_blocks(floor: int) -> tuple[tuple[str, int, int, int, int], ...]:
    """Khối lõi hành lang của một tầng (kèm thang bộ đúng vị trí tầng đó)."""
    return (*CORE_BLOCKS, ESCALATORS[floor])

# Mốc có thể đi tới: (x, y, loại, tên VI, tên EN, nối từ đâu).
# "west" = nối từ làn trái; "mid-<y>" = nối từ giữa lối băng ngang ở tung độ y.
LANDMARKS = {
    "WC-A": (500, 221, "restroom", "WC đầu hành lang", "the restroom at the top of the corridor", "west"),
    "LIFT-A": (500, 358, "elevator", "Thang máy A", "elevator A", "mid-410"),
    "STAIRS": (500, 680, "stairs", "Cầu thang bộ giữa sảnh", "the stairs in the atrium", "mid-740"),
    # Hai kiosk mỗi tầng, đứng ở lối băng ngang ngay trước bảng sơ đồ cạnh thang máy A / B.
    "KIOSK-A": (470, 410, "kiosk", "Kiosk chỉ đường cạnh thang máy A", "the wayfinding kiosk by elevator A", "crossing-410"),
    "KIOSK": (470, 740, "kiosk", "Kiosk chỉ đường cạnh thang máy B", "the wayfinding kiosk by elevator B", "crossing-740"),
    "LIFT-B": (500, 791, "elevator", "Thang máy B", "elevator B", "mid-740"),
    "WC-B": (500, 907, "restroom", "WC cuối hành lang", "the restroom at the bottom of the corridor", "west"),
}

# Mốc khác vị trí theo tầng (để trống: hai tầng hiện dùng chung vị trí mốc).
FLOOR_LANDMARKS: dict[int, dict[str, tuple]] = {}


def landmarks(floor: int) -> dict[str, tuple]:
    """Các mốc của một tầng: mốc chung + mốc riêng của tầng đó."""
    return {**LANDMARKS, **FLOOR_LANDMARKS.get(floor, {})}

Pt = tuple[int, int]


@dataclass(frozen=True)
class Shape:
    """Hình một khu: đường viền, vùng đặt phòng và lối từ cửa khu vào."""

    tone: str                      # "orange" | "green" (màu khu trên bảng thật) | "desk" (quầy lễ tân)
    outline: tuple[Pt, ...]        # đa giác vuông góc
    rooms: tuple[int, int, int, int]  # x, y, rộng, cao của vùng xếp phòng
    path: tuple[Pt, ...]           # điểm đầu là cửa khu (nút ENTRY), điểm cuối chạm hành lang nội bộ
    aisles: int = 1                # số hành lang nội bộ (mỗi hành lang có 2 dãy phòng)
    side_door: tuple[Pt, ...] = ()  # lối vào thứ hai: điểm đầu là cửa, nối tới điểm cuối của `path`

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        xs = [x for x, _ in self.outline]
        ys = [y for _, y in self.outline]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def rect(x1: int, y1: int, x2: int, y2: int) -> tuple[Pt, ...]:
    return ((x1, y1), (x2, y1), (x2, y2), (x1, y2))


def box(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int, int]:
    return (x1, y1, x2 - x1, y2 - y1)


O, G = "orange", "green"

SHAPES: dict[str, Shape] = {
    # ---------- Tầng 3: bên trái màu cam, bên phải màu xanh ----------
    "3-06": Shape(O, rect(60, 45, 500, 190), box(70, 55, 425, 181), ((438, 186), (438, 118))),
    "3-05": Shape(
        O, ((90, 190), (320, 190), (320, 265), (420, 265), (420, 300), (90, 300)),
        box(100, 196, 312, 294), ((420, 283), (318, 283), (318, 245)),
    ),
    "3-04": Shape(O, rect(95, 300, 420, 440), box(105, 310, 410, 430), ((420, 370),)),
    "3-03": Shape(
        O, ((115, 440), (320, 440), (320, 525), (420, 525), (420, 655), (45, 655), (45, 570), (115, 570)),
        box(125, 532, 410, 648), ((420, 590),),
    ),
    "3-02": Shape(O, rect(160, 735, 420, 855), box(170, 742, 410, 848), ((420, 795),)),
    "3-01": Shape(O, rect(100, 932, 500, 1045), box(110, 942, 425, 1038), ((438, 936), (438, 990))),
    "3-07": Shape(
        G, ((500, 45), (850, 45), (850, 280), (730, 280), (730, 190), (500, 190)),
        box(575, 55, 840, 181), ((562, 186), (562, 118)),
    ),
    "3-08": Shape(
        G, ((640, 190), (730, 190), (730, 280), (955, 280), (955, 415), (580, 415), (580, 280), (640, 280)),
        box(590, 288, 945, 408), ((580, 348),),
    ),
    "3-09": Shape(
        G, ((653, 415), (860, 415), (860, 710), (653, 710), (653, 550), (580, 550), (580, 515), (653, 515)),
        box(665, 421, 852, 705), ((580, 532), (659, 532)), aisles=2,
    ),
    "3-10": Shape(G, rect(580, 550, 653, 640), box(590, 556, 648, 634), ((580, 595),)),
    "3-11": Shape(G, rect(580, 710, 960, 840), box(590, 716, 950, 834), ((580, 775),)),
    "3-12": Shape(
        G, ((675, 840), (875, 840), (875, 1020), (500, 1020), (500, 932), (580, 932), (580, 915), (675, 915)),
        box(585, 924, 866, 1012), ((562, 936), (562, 968)),
    ),
    # ---------- Tầng 4: bên trái màu xanh, bên phải màu cam ----------
    "4-13": Shape(G, rect(145, 45, 470, 190), box(155, 55, 425, 181), ((438, 186), (438, 118))),
    "4-12": Shape(
        G, ((110, 190), (330, 190), (330, 268), (420, 268), (420, 300), (110, 300)),
        box(120, 196, 322, 294), ((420, 284), (328, 284), (328, 245)),
    ),
    "4-11": Shape(G, rect(45, 300, 420, 405), box(55, 306, 410, 398), ((420, 352),)),
    "4-10": Shape(
        G, ((145, 405), (330, 405), (330, 490), (420, 490), (420, 535), (145, 535)),
        box(155, 411, 322, 529), ((420, 512), (328, 512), (328, 470)),
    ),
    "4-09": Shape(
        G, ((145, 535), (420, 535), (420, 630), (330, 630), (330, 720), (175, 720), (175, 630), (145, 630)),
        box(155, 541, 410, 623), ((420, 582),),
    ),
    # KSK Tổng quát: quầy lễ tân chiếm giữa mặt tiền, hai lối vào ở hai bên quầy.
    "4-08": Shape(
        G, ((40, 720), (420, 720), (420, 745), (350, 745), (350, 835), (420, 835), (420, 860), (40, 860)),
        box(50, 727, 340, 853), ((420, 732), (345, 732), (345, 790)),
        side_door=((420, 848), (345, 848)),
    ),
    # Quầy lễ tân – tư vấn dịch vụ (hơn nửa mặt tiền cửa khu 8, quay ra hành lang chính).
    "4-14": Shape("desk", rect(350, 745, 420, 835), box(358, 752, 412, 828), ((420, 790),)),
    "4-07": Shape(
        G, ((140, 860), (330, 860), (330, 932), (500, 932), (500, 1075), (140, 1075)),
        box(150, 942, 425, 1066), ((438, 936), (438, 1004)),
    ),
    "4-01": Shape(O, rect(470, 45, 610, 190), box(480, 55, 550, 181), ((562, 186), (562, 118))),
    "4-02": Shape(O, rect(610, 45, 945, 190), box(622, 55, 935, 181), ((562, 186), (562, 118))),
    "4-03": Shape(O, rect(580, 275, 850, 405), box(590, 281, 840, 399), ((580, 340),)),
    "4-04": Shape(
        O, ((580, 495), (945, 495), (945, 715), (660, 715), (660, 625), (580, 625)),
        box(590, 501, 935, 619), ((580, 560),),
    ),
    "4-05": Shape(
        O, ((580, 715), (855, 715), (855, 900), (660, 900), (660, 855), (580, 855)),
        box(590, 721, 845, 849), ((580, 785),),
    ),
    "4-06": Shape(
        O, ((660, 900), (855, 900), (855, 1075), (500, 1075), (500, 932), (660, 932)),
        box(575, 940, 845, 1068), ((562, 936), (562, 1004)),
    ),
}

# Giếng trời (ô xám trên bảng) — chỉ để vẽ.
SUNROOMS = {
    3: (box(320, 190, 420, 265), box(320, 440, 420, 525), box(580, 190, 640, 280),
        box(580, 415, 653, 515), box(580, 640, 653, 710), box(580, 840, 675, 915)),
    4: (box(330, 190, 420, 268), box(330, 405, 420, 490), box(330, 630, 420, 720),
        box(330, 860, 420, 932), box(580, 625, 660, 715), box(580, 855, 660, 932)),
}

# Biển EXIT gắn ở mép tường ngoài các khu (thang thoát hiểm) — chỉ để vẽ, không đè dãy phòng.
EXITS = {
    3: ((112, 34), (808, 34), (976, 398), (24, 612), (386, 724), (981, 822), (138, 1056)),
    4: ((196, 34), (966, 172), (24, 318), (628, 416), (966, 600), (19, 738), (196, 1086), (812, 1086)),
}
