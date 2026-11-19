"""Resolve destinations and calculate directions using the active PostgreSQL graph."""

from collections import defaultdict
from heapq import heappop, heappush

from sqlalchemy.orm import Session

from app.core.errors import WayfindingError
from app.crud import wayfinding as catalog
from app.db.seeds.vinmec_floors_3_4.catalog import BOOKING_DESK, SITE_CODE, WALK_IN_ROOMS, WALK_IN_ZONES
from app.db.seeds.vinmec_floors_3_4.floor_plan import demo_floor_plan
from app.models import Kiosk
from app.schema.wayfinding import (
    Clarification, DirectionResult, FloorPlan, KioskMap, Language, MapFloor, Point, Route, Step, TextTurn, Turn,
)
from app.services.wayfinding_language import (
    appointment_answer, has_phrase, normalize, select_language, stated_appointment, yes_no,
)
from app.services.wayfinding_lookup import (
    MAX_CANDIDATES, load_destinations, match_doctors, resolve, spoken_floor,
)


# Câu đáp khi được mời đến quầy tư vấn: "vẫn muốn đến" khoa, hay đi quầy. Xét "vẫn" trước vì "tư vấn" cũng có "van".
INSIST = ("van muon", "van den", "van di", "van can", "van cu", "cu chi", "cu di", "still", "anyway")
DESK_WORDS = ("tu van", "quay", "dat lich", "desk", "counter", "advice", "booking", "book")


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


def demo_floor_plans(db: Session, site_id: int, floors) -> list[FloorPlan]:
    # Chỉ cơ sở mô phỏng mới có mặt bằng dựng sẵn; tầng đã có ảnh thì dùng ảnh.
    site = catalog.active_site(db, site_id)
    if not site or site.code != SITE_CODE:
        return []
    plans = (demo_floor_plan(floor.id, floor.level) for floor in floors if not floor.map_asset_url)
    return [plan for plan in plans if plan]


def kiosk_map(db: Session, code: str, language: Language) -> KioskMap:
    """Bản đồ màn hình chờ: kiosk đứng ở đâu và mặt bằng các tầng (tầng cao trước như bảng thật)."""
    kiosk = kiosk_for(db, code, language)
    floors = sorted(catalog.site_floors(db, kiosk.site_id), key=lambda floor: -floor.level)
    by_id = {floor.id: floor for floor in floors}
    node = next(iter(catalog.floor_nodes(db, kiosk.site_id, by_id.keys(), [kiosk.origin_node_id])), None)
    if node is None:
        message = "The kiosk location is unavailable." if language == "en" else "Vị trí kiosk hiện không khả dụng."
        raise WayfindingError("kiosk_conflict", message)
    floor = by_id[node.floor_id]
    return KioskMap(
        kiosk_code=kiosk.code,
        origin=Point(
            floor_id=floor.id, floor=floor.level, x=node.x, y=node.y,
            label=node.label, map_asset_url=floor.map_asset_url,
        ),
        floors=[MapFloor(floor_id=item.id, floor=item.level, map_asset_url=item.map_asset_url) for item in floors],
        floor_plans=demo_floor_plans(db, kiosk.site_id, floors),
    )


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
    pending = context.pending if context else None
    prior = [code for code in context.candidate_codes if code in targets] if context else []
    # Đang chờ khách đáp thì chưa đoán gần đúng: "đúng rồi" không được hiểu thành tên một phòng.
    codes, how = resolve(db, site, text, targets, [] if pending else prior, fuzzy=not pending)
    if prior and not pending and codes and not set(codes) & set(prior):
        # Đáp câu "ở khoa nào?" bằng tên khoa → giữ các lựa chọn đang chờ thuộc khoa đó.
        departments = {targets[code][0].department_code for code in codes if targets[code][0].kind == "department"}
        narrowed = [code for code in prior if targets[code][0].department_code in departments]
        if narrowed:
            codes, how = narrowed, "prior"
    if pending == "confirm" and prior and set(codes) <= set(prior):
        # Khách đáp câu "Có phải anh chị muốn đến …?": đồng ý thì đi tiếp với điểm đến đã đoán.
        answer = yes_no(text)
        if answer:
            codes, how = prior, "prior"
        elif answer is False and not codes:
            return DirectionResult(
                status="not_found", language=language,
                message=(
                    "Sorry about that. Please tell me the department or the room code on your slip again."
                    if english else
                    "Xin lỗi anh chị. Anh chị vui lòng nói lại tên khoa hoặc mã phòng ghi trên phiếu."
                ),
            )
    # Lịch hẹn: khách đã cho biết ở lượt trước, hoặc tự nói trong câu này ("tôi có hẹn khám…").
    appointment = context.appointment if context else None
    stated = stated_appointment(text)
    if stated is not None:
        appointment = stated
    if pending == "appointment" and prior and set(codes) <= set(prior):
        answer = appointment_answer(text)
        if answer is not None:
            appointment, codes, how = answer, prior, "prior"
    if pending == "booking" and len(prior) == 2 and set(codes) <= set(prior):
        # Chưa có lịch: khách chọn quầy tư vấn, hay "vẫn muốn đến" khoa (bấm thẻ cũng gửi mã vào đây).
        desk_choice, wanted = prior
        if codes == [wanted] or has_phrase(text, INSIST):
            codes, how = [wanted], "insist"
        elif codes == [desk_choice] or has_phrase(text, DESK_WORDS):
            codes, how = [desk_choice], "prior"
    if pending and not codes:
        # Không phải câu trả lời → coi như khách hỏi điểm đến mới.
        codes, how = resolve(db, site, text, targets, [])
        if not codes and pending in ("appointment", "booking"):
            # Chưa hiểu câu đáp → hỏi lại đúng câu đang chờ thay vì báo không tìm thấy.
            codes, how = prior[-1:], "prior"

    # Bác sĩ: "tôi có hẹn với bác sĩ Hùng" → phòng bác sĩ khám (mã phòng khách tự đọc vẫn được ưu tiên).
    doctors = list(catalog.active_doctors(db, site))
    found = [doctor for doctor in match_doctors(text, doctors) if doctor.room_code in targets] if how != "code" else []
    if found:
        # Khách nói kèm tầng / khoa thì lọc luôn những người trùng tên.
        floor, _ = spoken_floor(normalize(text))
        departments = {targets[code][0].department_code for code in codes if targets[code][0].kind == "department"}
        found = [
            doctor for doctor in found
            if (floor is None or targets[doctor.room_code][0].floor == floor)
            and (not departments or targets[doctor.room_code][0].department_code in departments)
        ] or found
        codes, how = sorted({doctor.room_code for doctor in found}), "doctor"
    # Gắn tên bác sĩ vào phòng (lượt này, hoặc từ lượt hỏi lại trước) để thẻ và câu chỉ đường nêu đúng người.
    by_code = {doctor.code: doctor for doctor in doctors}
    named = found or [by_code[code] for code in (context.doctor_codes if context else []) if code in by_code]
    for doctor in named:
        if doctor.room_code in targets:
            target, node_id = targets[doctor.room_code]
            label = ", ".join(filter(None, (target.doctor, f"{doctor.title} {doctor.name}")))
            targets[doctor.room_code] = (target.model_copy(update={"doctor": label}), node_id)
    doctor_codes = [doctor.code for doctor in named if doctor.room_code in codes]

    if not codes:
        return DirectionResult(
            status="not_found", language=language,
            message=(
                "I could not find the destination. Please tell me the room code or department on your slip."
                if english else
                "Tôi chưa tìm được điểm đến. Anh chị vui lòng nói mã phòng hoặc tên khoa ghi trên phiếu."
            ),
            # Giữ lựa chọn đang chờ để khách vẫn có thể chỉ nói tầng; câu xác nhận thì không giữ.
            context=context.model_copy(update={"language": language}) if context and not pending else None,
        )
    if how == "fuzzy" and len(codes) <= MAX_CANDIDATES:
        # Nghe gần đúng → hỏi lại trước khi chỉ đường, không tự quyết.
        choices = [targets[code][0] for code in codes]
        names = list(dict.fromkeys(
            (choice.name_en or choice.name) if english else choice.name for choice in choices
        ))[:3]
        return DirectionResult(
            status="clarify", language=language,
            message=(
                f"Did you mean {' or '.join(names)}?" if english
                else f"Có phải anh chị muốn đến {' hoặc '.join(names)} không?"
            ),
            candidates=choices if len(choices) <= 4 else [],
            replies=["Yes", "No"] if english else ["Đúng rồi", "Không phải"],
            context=Clarification(
                kiosk_code=kiosk.code, candidate_codes=codes, wheelchair=wheelchair,
                language=language, pending="confirm", appointment=appointment,
            ),
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
        if all(choice.doctor for choice in choices):
            # Trùng tên bác sĩ: nêu từng người kèm khoa/tầng (cùng khoa thì kèm phòng) để khách chọn.
            same_department = len({choice.department_code for choice in choices}) == 1
            if len(choices) > 4:
                question = (
                    f"There are {len(choices)} matching doctors. Please tell me the doctor's full name or department."
                    if english else
                    f"Có {len(choices)} bác sĩ phù hợp. Anh chị vui lòng nói họ tên đầy đủ hoặc khoa của bác sĩ."
                )
            elif english:
                labels = "; ".join(f"{choice.doctor}, room {choice.code} on floor {choice.floor}" for choice in choices)
                question = f"There are {len(choices)} matching doctors: {labels}. Which one is yours?"
            else:
                labels = "; ".join(
                    f"{choice.doctor} ở phòng {choice.code}" if same_department
                    else f"{choice.doctor} ở {choice.department}, tầng {choice.floor}"
                    for choice in choices
                )
                question = f"Có {len(choices)} bác sĩ phù hợp: {labels}. " + (
                    "Anh chị vui lòng chọn trên màn hình hoặc đọc mã phòng."
                    if same_department else "Anh chị có lịch với bác sĩ ở khoa nào?"
                )
        elif len(floors_mentioned) == len(choices) and len(choices) <= 4:
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
                appointment=appointment, doctor_codes=doctor_codes,
            ),
        )

    destination, target_id = targets[codes[0]]
    name_en = destination.name_en or f"{destination.kind} {destination.code}"
    desk = next((
        code for code, (target, _) in targets.items() if target.kind == "room" and target.name == BOOKING_DESK
    ), None)
    # Khách tự đọc mã phòng (thường in trên phiếu) = đã đăng ký; bấm chọn trong danh sách kiosk đưa ra thì không tính.
    read_code = how == "code" and not set(codes) <= set(prior)
    if (
        desk and codes[0] != desk and how != "insist" and not read_code
        and destination.department_code not in WALK_IN_ZONES and destination.name not in WALK_IN_ROOMS
    ):
        label = (
            f"phòng của {destination.doctor}" if destination.doctor
            else f"{destination.name}, {destination.department}"
            if destination.kind == "room" and destination.department else destination.name
        )
        if appointment is None:
            return DirectionResult(
                status="clarify", language=language,
                message=(
                    f"Do you already have an appointment with {destination.doctor}?"
                    if english and destination.doctor else
                    f"Do you already have an appointment at {name_en}?" if english else
                    f"Anh chị đã đặt lịch hẹn với {destination.doctor} chưa ạ?" if destination.doctor else
                    f"Anh chị đã đặt lịch hẹn ở {label} chưa ạ?"
                ),
                replies=["Yes, I have one", "Not yet"] if english else ["Đã đặt lịch", "Chưa đặt lịch"],
                # Để bản đồ vẫn mở đúng tầng và tô điểm đến trong lúc hỏi.
                candidates=[destination],
                context=Clarification(
                    kiosk_code=kiosk.code, candidate_codes=[destination.code], wheelchair=wheelchair,
                    language=language, pending="appointment", doctor_codes=doctor_codes,
                ),
            )
        if appointment is False:
            booking = targets[desk][0]
            return DirectionResult(
                status="clarify", language=language,
                message=(
                    f"Without an appointment, please visit the service advice and booking desk on floor "
                    f"{booking.floor} first. Would you like to go to the advice desk, or still go to {name_en}?"
                    if english else
                    f"Anh chị chưa có lịch hẹn thì nên đến quầy {booking.name} ở tầng {booking.floor} trước. "
                    f"Anh chị muốn đến quầy tư vấn, hay vẫn muốn đến {label}?"
                ),
                candidates=[booking, destination],
                context=Clarification(
                    kiosk_code=kiosk.code, candidate_codes=[desk, destination.code], wheelchair=wheelchair,
                    language=language, pending="booking", appointment=False, doctor_codes=doctor_codes,
                ),
            )
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
        if steps and destination.doctor:
            message = f"To see {destination.doctor} in {label}, follow these directions."
    else:
        label = f"{destination.name}, mã {destination.code}, tầng {destination.floor}"
        message = (
            f"Để đến {label}, anh chị đi theo hướng dẫn sau."
            if steps else f"Anh chị đang ở điểm đến {label}."
        )
        if steps and destination.doctor:
            message = f"Để gặp {destination.doctor} tại {label}, anh chị đi theo hướng dẫn sau."
    if steps:
        message += " " + " ".join(step.instruction for step in steps)
    origin, arrival = point(kiosk.origin_node_id), point(target_id)
    route_floors = dict.fromkeys([origin.floor_id, *(step.end.floor_id for step in steps)])
    floor_plans = demo_floor_plans(db, site, [floors[floor_id] for floor_id in route_floors])
    return DirectionResult(
        status="route", language=language,
        message=message,
        route=Route(
            destination=destination, origin=origin, arrival=arrival,
            seconds=seconds, steps=steps, floor_plans=floor_plans,
        ),
    )
