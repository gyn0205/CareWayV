"""Resolve destinations and calculate directions using the active PostgreSQL graph."""

from collections import defaultdict
from heapq import heappop, heappush

from sqlalchemy.orm import Session

from app.core.errors import WayfindingError
from app.crud import wayfinding as catalog
from app.db.seeds.vinmec_floors_3_4.catalog import SITE_CODE
from app.db.seeds.vinmec_floors_3_4.floor_plan import demo_floor_plan
from app.models import Kiosk
from app.schema.wayfinding import Clarification, DirectionResult, Language, Point, Route, Step, TextTurn, Turn
from app.services.wayfinding_language import normalize, select_language
from app.services.wayfinding_lookup import MAX_CANDIDATES, load_destinations, resolve


def kiosk_context(turn: Turn) -> Clarification | None:
    if turn.context and turn.context.kiosk_code == turn.kiosk_code:
        return turn.context
    return None


def process_text_turn(db: Session, turn: TextTurn) -> DirectionResult:
    context = kiosk_context(turn)
    language = select_language(turn.language, turn.text, context.language if context else None)
    kiosk = kiosk_for(db, turn.kiosk_code, language)
    return find_route(db, kiosk, turn.text, turn.wheelchair, context, language)


def kiosk_for(db: Session, code: str, language: Language) -> Kiosk:
    kiosks = list(catalog.active_kiosks(db, code))
    if len(kiosks) > 1:
        message = "This kiosk code is used at multiple sites." if language == "en" else "Mã kiosk xuất hiện ở nhiều cơ sở."
        raise WayfindingError("kiosk_conflict", message)
    if not kiosks or catalog.active_site(db, kiosks[0].site_id) is None:
        message = "No active kiosk found." if language == "en" else "Không tìm thấy kiosk đang hoạt động."
        raise WayfindingError("kiosk_not_found", message)
    return kiosks[0]


# Phạt mỗi chặng thang bộ thật nặng: luôn ưu tiên thang máy khi đổi tầng,
# thang bộ chỉ được chọn khi không còn đường nào bằng thang máy.
STAIRS_PENALTY = 3600


def route_weight(edge) -> int:
    # Trọng số chỉ dùng để chọn đường; thời gian báo cho khách vẫn là cost_seconds thật.
    return edge.cost_seconds + (STAIRS_PENALTY if edge.kind == "stairs" else 0)


def shortest_path(origin, destination, edges):
    neighbors = defaultdict(list)
    for edge in edges:
        neighbors[edge.from_node_id].append(edge)
    frontier = [(0, origin)]
    distance = {origin: 0}
    previous = {}
    while frontier:
        cost, node = heappop(frontier)
        if cost != distance[node]:
            continue
        if node == destination:
            path = []
            while node != origin:
                edge = previous[node]
                path.append(edge)
                node = edge.from_node_id
            path.reverse()
            # Trả về tổng thời gian thật (không tính khoản phạt thang bộ).
            return sum(edge.cost_seconds for edge in path), path
        for edge in neighbors[node]:
            candidate = cost + route_weight(edge)
            target = edge.to_node_id
            if target not in distance or candidate < distance[target]:
                distance[target] = candidate
                previous[target] = edge
                heappush(frontier, (candidate, target))
    return None


def find_route(
    db: Session,
    kiosk: Kiosk,
    text: str,
    wheelchair: bool,
    context: Clarification | None,
    language: Language,
) -> DirectionResult:
    site = kiosk.site_id
    english = language == "en"
    query_text = f" {normalize(text)} "
    wheelchair = (
        wheelchair or bool(context and context.wheelchair)
        or any(phrase in query_text for phrase in (
            " xe lan ", " khong di cau thang ", " bang thang may ",
            " wheelchair ", " no stairs ", " avoid stairs ", " take the elevator ", " take the lift ",
        ))
    )
    floors = {floor.id: floor for floor in catalog.site_floors(db, site)}
    nodes = {node.id: node for node in catalog.floor_nodes(db, site, floors.keys())}
    if kiosk.origin_node_id not in nodes:
        message = "The kiosk location is unavailable." if english else "Vị trí kiosk hiện không khả dụng."
        raise WayfindingError("kiosk_conflict", message)
    targets = load_destinations(db, site, nodes, floors)
    prior = context.candidate_codes if context else []
    codes = resolve(db, site, text, targets, prior)
    if not codes:
        return DirectionResult(
            status="not_found", language=language,
            message=(
                "I could not find the destination. Please tell me the room code or department on your slip."
                if english else
                "Tôi chưa tìm được điểm đến. Anh chị vui lòng nói mã phòng hoặc tên khoa ghi trên phiếu."
            ),
            context=context.model_copy(update={"language": language}) if context else None,
        )
    if len(codes) > 1:
        question = (
            "Several destinations match. Please tell me the room code or floor."
            if english else "Có nhiều điểm đến phù hợp. Anh chị vui lòng cho biết tầng hoặc mã phòng."
        )
        if len(codes) > MAX_CANDIDATES:
            return DirectionResult(status="clarify", language=language, message=question)
        choices = [targets[code][0] for code in codes]
        floors_mentioned = sorted({choice.floor for choice in choices})
        if len(floors_mentioned) == len(choices) and len(choices) <= 4:
            if english:
                labels = " or ".join(f"floor {floor}" for floor in floors_mentioned)
                question = f"Which floor do you need, {labels}?"
            else:
                labels = " hoặc ".join(f"tầng {floor}" for floor in floors_mentioned)
                question = f"Anh chị cần đến {labels}?"
        elif len(choices) <= 4:
            if english:
                labels = "; ".join(f"{choice.code} on floor {choice.floor}" for choice in choices)
                question = f"Please choose a destination code: {labels}."
            else:
                labels = "; ".join(f"{choice.name}, mã {choice.code}" for choice in choices)
                question = f"Có các điểm đến sau: {labels}. Anh chị vui lòng đọc mã cần đến."
        return DirectionResult(
            status="clarify", language=language,
            message=question,
            candidates=choices,
            context=Clarification(
                kiosk_code=kiosk.code, candidate_codes=codes, wheelchair=wheelchair, language=language,
            ),
        )

    destination, target_id = targets[codes[0]]
    name_en = destination.name_en or f"{destination.kind} {destination.code}"
    edges = (
        edge for edge in catalog.active_edges(db, site, wheelchair)
        if edge.from_node_id in nodes and edge.to_node_id in nodes
    )
    result = shortest_path(kiosk.origin_node_id, target_id, edges)
    if result is None:
        return DirectionResult(
            status="no_route", language=language,
            message=(
                f"No suitable route to {name_en} is available. Please ask at the information desk."
                if english else
                f"Hiện chưa có lối đi phù hợp đến {destination.name}. Anh chị vui lòng liên hệ quầy hỗ trợ."
            ),
        )

    def point(node_id):
        node = nodes[node_id]
        floor = floors[node.floor_id]
        return Point(
            floor_id=floor.id, floor=floor.level, x=node.x, y=node.y,
            label=node.label, map_asset_url=floor.map_asset_url,
        )

    seconds, edges_on_route = result
    steps = []
    for edge in edges_on_route:
        start, end = point(edge.from_node_id), point(edge.to_node_id)
        if english:
            method = "the elevator" if edge.kind == "elevator" else "the stairs"
            fallback = (
                f"Follow the corridor to {end.label or 'the next waypoint'}."
                if edge.kind == "walk" else f"Take {method} to floor {end.floor}."
            )
            instruction = edge.instruction_en or fallback
        else:
            method = "thang máy" if edge.kind == "elevator" else "cầu thang bộ"
            landmark = end.label or f"điểm kế tiếp ở tầng {end.floor}"
            fallback = (
                f"Đi theo hành lang đến {landmark}."
                if edge.kind == "walk" else f"Dùng {method} để đến tầng {end.floor}."
            )
            instruction = edge.instruction or fallback
        # Một lối băng ngang bị chia thành nhiều cạnh (qua kiosk, sảnh giữa) → gộp thành một bước,
        # chỉ khi thẳng hàng để sơ đồ vẫn vẽ đúng đường.
        last = steps[-1] if steps else None
        if (
            last and last.kind == edge.kind == "walk" and last.instruction == instruction
            and last.start.floor_id == end.floor_id
            and None not in (last.start.x, last.start.y, last.end.x, last.end.y, end.x, end.y)
            and (last.start.x == last.end.x == end.x or last.start.y == last.end.y == end.y)
        ):
            steps[-1] = last.model_copy(update={"end": end, "seconds": last.seconds + edge.cost_seconds})
            continue
        steps.append(Step(
            kind=edge.kind, seconds=edge.cost_seconds, start=start, end=end,
            instruction=instruction,
        ))

    if english:
        label = f"{name_en} on floor {destination.floor}"
        message = f"To reach {label}, follow these directions." if steps else f"You are already at {label}."
    else:
        label = f"{destination.name}, mã {destination.code}, tầng {destination.floor}"
        message = (
            f"Để đến {label}, anh chị đi theo hướng dẫn sau."
            if steps else f"Anh chị đang ở điểm đến {label}."
        )
    if steps:
        message += " " + " ".join(step.instruction for step in steps)
    origin, arrival = point(kiosk.origin_node_id), point(target_id)
    site_record = catalog.active_site(db, site)
    floor_plans = []
    if site_record and site_record.code == SITE_CODE:
        route_floors = dict.fromkeys([origin.floor_id, *(step.end.floor_id for step in steps)])
        for floor_id in route_floors:
            plan = demo_floor_plan(floor_id, floors[floor_id].level)
            if plan and not floors[floor_id].map_asset_url:
                floor_plans.append(plan)
    return DirectionResult(
        status="route", language=language,
        message=message,
        route=Route(
            destination=destination, origin=origin, arrival=arrival,
            seconds=seconds, steps=steps, floor_plans=floor_plans,
        ),
    )
