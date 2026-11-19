"""Ghép các cạnh của tuyến thành câu chỉ đường kiểu lễ tân: rẽ trái/phải theo hướng người đang đi, kèm mốc.

Mỗi cạnh trong seed chỉ mang một cụm "đi qua đâu / đến đâu" (vd. "qua Thang máy A", "đến phòng 4-005 — …");
hướng rẽ và quãng đường do đây tính từ tọa độ, nên câu luôn đúng với chiều người đi.
"""

from math import hypot

from app.schema.wayfinding import FloorPlan, Point, Step

Vector = tuple[float, float]

# Cụm của cạnh nằm trong khoảng này tính từ đầu chặng thì nói trước quãng đường ("rẽ trái vào cửa…, đi thẳng…").
LEAD_METRES = 10

WORDS = {
    "vi": {
        "first": {
            "straight": "Từ đây, anh chị đi thẳng", "right": "Từ đây, anh chị rẽ phải",
            "left": "Từ đây, anh chị rẽ trái", "back": "Từ đây, anh chị quay người lại", None: "Từ đây, anh chị đi",
        },
        "next": {"straight": "Đi thẳng tiếp", "right": "Rẽ phải", "left": "Rẽ trái", "back": "Quay lại", None: "Đi tiếp"},
        "elevator": "Ra khỏi thang máy, đi thẳng", "stairs": "Hết cầu thang, đi thẳng",
        "distance": " khoảng {} m", "walk": "đi thẳng khoảng {} m", "arrive": " là ", "around": ", đi ",
    },
    "en": {
        "first": {
            "straight": "From here, go straight", "right": "From here, turn right",
            "left": "From here, turn left", "back": "From here, turn around", None: "From here, walk",
        },
        "next": {"straight": "Keep going straight", "right": "Turn right", "left": "Turn left", "back": "Turn around", None: "Continue"},
        "elevator": "Leave the elevator and go straight", "stairs": "Step off the stairs and go straight",
        "distance": " for about {} metres", "walk": "then walk about {} metres", "arrive": " ", "around": " and walk ",
    },
}


def direction(start: Point, end: Point) -> Vector | None:
    if start.floor_id != end.floor_id or None in (start.x, start.y, end.x, end.y):
        return None
    dx, dy = end.x - start.x, end.y - start.y
    length = hypot(dx, dy)
    return (dx / length, dy / length) if length > 1e-9 else None


def turn(before: Vector | None, after: Vector | None) -> str | None:
    if before is None or after is None:
        return None
    dot = before[0] * after[0] + before[1] * after[1]
    if dot > 0.7:
        return "straight"
    if dot < -0.7:
        return "back"
    # Trục y bản đồ hướng xuống → tích có hướng dương là rẽ phải.
    return "right" if before[0] * after[1] - before[1] * after[0] > 0 else "left"


def kiosk_facing(plan: FloorPlan | None, origin: Point) -> Vector | None:
    """Khách đứng trước kiosk, mặt nhìn vào bảng sơ đồ gần nhất."""
    boards = [block for block in plan.blocks if block.kind == "board"] if plan else []
    if not boards or origin.x is None or origin.y is None:
        return None
    x, y = origin.x * plan.width, origin.y * plan.height
    board = min(boards, key=lambda b: hypot(b.x + b.width / 2 - x, b.y + b.height / 2 - y))
    # Đổi về tọa độ chuẩn hóa (0–1) như tọa độ nút.
    dx, dy = (board.x + board.width / 2 - x) / plan.width, (board.y + board.height / 2 - y) / plan.height
    length = hypot(dx, dy)
    return (dx / length, dy / length) if length > 1e-9 else None


def rounded(metres: int) -> int:
    return max(5, round(metres / 5) * 5)


def compose_steps(edges, point, english: bool, facing: Vector | None) -> list[Step]:
    """Mỗi bước là một đoạn thẳng (để sơ đồ vẽ đúng); các cạnh đi bộ thẳng hàng cùng chiều gộp làm một."""
    words = WORDS["en" if english else "vi"]
    legs = []
    for edge in edges:
        start, end = point(edge.from_node_id), point(edge.to_node_id)
        heading = direction(start, end) if edge.kind == "walk" else None
        phrase = edge.instruction_en if english else edge.instruction
        last = legs[-1] if legs else None
        if (
            last and edge.kind == last["kind"] == "walk" and last["end"].floor_id == end.floor_id
            and (heading is None or last["heading"] is None or turn(last["heading"], heading) == "straight"
                 and abs(last["heading"][0] * heading[1] - last["heading"][1] * heading[0]) < 1e-3)
        ):
            last["heading"] = last["heading"] or heading
        else:
            last = {"kind": edge.kind, "start": start, "heading": heading, "seconds": 0, "lead": [], "tail": [], "edge": edge}
            legs.append(last)
        last["end"] = end
        last["seconds"] += edge.cost_seconds
        if edge.kind == "walk":
            if phrase is None and end.label:
                phrase = f"to {end.label}" if english else f"đến {end.label}"
            if phrase:
                # Mét ≈ giây đi bộ (seed tính 0,12 m và 0,12 giây cho mỗi đơn vị bản đồ).
                bucket = last["lead"] if last["seconds"] < LEAD_METRES else last["tail"]
                if phrase not in last["lead"] + last["tail"]:
                    bucket.append(phrase)

    steps = []
    previous = facing
    after = None  # loại thang vừa đi (để nói "ra khỏi thang máy")
    for index, leg in enumerate(legs):
        if leg["kind"] != "walk":
            edge, end = leg["edge"], leg["end"]
            method = ("the elevator" if edge.kind == "elevator" else "the stairs") if english else (
                "thang máy" if edge.kind == "elevator" else "cầu thang bộ")
            fallback = f"Take {method} to floor {end.floor}." if english else f"Dùng {method} để đến tầng {end.floor}."
            text = (edge.instruction_en if english else edge.instruction) or fallback
            after, previous = edge.kind, None
        else:
            turned = turn(previous, leg["heading"])
            if after:
                head, straight = words[after], True
            else:
                head = words["first" if index == 0 else "next"][turned]
                straight = turned == "straight"
            metres = leg["seconds"]
            # "quay người lại, đi đến Thang máy B" — sau "quay lại" cần thêm động từ đi.
            joiner = words["around"] if turned == "back" and not after else " "
            parts = [head + (joiner + ", ".join(leg["lead"]) if leg["lead"] else "")]
            if metres >= LEAD_METRES:
                if straight and not leg["lead"]:
                    parts[0] += words["distance"].format(rounded(metres))
                else:
                    parts.append(words["walk"].format(rounded(metres)))
            final = index == len(legs) - 1
            if final and leg["lead"] and len(parts) == 1 and not leg["tail"]:
                # Chặng cuối ngắn: "Rẽ trái là đến phòng …".
                parts = [head + words["arrive"] + ", ".join(leg["lead"])]
            text = ", ".join(parts + leg["tail"]) + "."
            after, previous = None, leg["heading"] or previous
        steps.append(Step(kind=leg["kind"], seconds=leg["seconds"], start=leg["start"], end=leg["end"], instruction=text))
    return steps
