"""Match a kiosk utterance against destinations and service aliases in its site."""

import re
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import product

from app.crud import wayfinding as catalog
from app.schema.wayfinding import Destination
from app.services.wayfinding_language import normalize

DIGITS = ("khong", "mot", "hai", "ba", "bon", "nam", "sau", "bay", "tam", "chin")
EN_SMALL = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen",
)
EN_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
EN_ORDINALS = ("ground", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth")
FLOOR = re.compile(r"\btang (?:so )?(\d+|khong|mot|hai|ba|bon|tu|nam|sau|bay|tam|chin)\b")
EN_NUMBERS = "|".join((*EN_SMALL, *EN_ORDINALS))
FLOOR_EN = re.compile(
    rf"\b(?:floor|level) (?:number )?(\d+|{EN_NUMBERS})\b"
    rf"|\b(\d+(?:st|nd|rd|th)?|{EN_NUMBERS}) (?:floor|level)\b"
)
WRITTEN_CODE = re.compile(r"(?<![\w-])\d+(?:\s*[-–—]\s*\d+)+(?![\w-])")
DEPARTMENT_PREFIX = re.compile(r"^(?:trung tam|khoa|don vi|phong kham) ")
EN_DEPARTMENT_SUFFIX = re.compile(r" (?:center|centre|department|unit|clinic)$")
# Tách tên khoa nhiều vế ("Nội tiết – Đái tháo đường", "Thần kinh và Đột quỵ") trước khi normalize.
# Vế một chữ ("Mắt") bỏ qua vì dễ trùng chữ khác sau khi bỏ dấu ("mặt", "mát").
DEPARTMENT_PARTS = re.compile(r"\s+[–—-]\s+|\s+và\s+")
FLOOR_FILLER = {
    "o", "tren", "duoi", "a", "nhe", "nha", "vang", "dung", "roi",
    "on", "at", "the", "please", "yes", "it", "s", "is",
}
MAX_CANDIDATES = 40
# "bác sĩ" STT có thể ghi "bác sỹ"; tiếng Anh "doctor" / "Dr.".
DOCTOR_PREFIXES = ("bac si", "bac sy", "bs", "doctor", "dr")
# STT nghe gần đúng ("điện tim đồ" → "điện tâm đồ"): chỉ nhận cụm giống ≥ 80% và đủ dài để khỏi khớp bừa.
# Kết quả gần đúng luôn được hỏi lại xác nhận nên khớp nhầm chỉ tốn một câu hỏi, không dẫn sai đường.
FUZZY_MIN_RATIO = 0.8
FUZZY_MIN_LENGTH = 6


def spoken_group(group: str, english: bool) -> set[str]:
    unpadded = group.lstrip("0") or "0"
    digits = EN_SMALL if english else DIGITS
    spelled = " ".join(digits[int(char)] for char in group)
    forms = {group, spelled}
    # Số phòng 3 chữ số ("010") không bỏ số 0 đầu, để "4-10" vẫn là khu 4-10 chứ không phải phòng 4-010.
    if len(group) <= 2:
        forms.add(unpadded)
    if english and "0" in group:
        forms.add(spelled.replace("zero", "oh"))
    if len(group) != 2:
        return forms
    tens, units = map(int, group)
    if english:
        number = tens * 10 + units
        forms.add(EN_SMALL[number] if number < 20 else (
            f"{EN_TENS[tens]} {EN_SMALL[units]}" if units else EN_TENS[tens]
        ))
        return forms
    if not tens:
        forms.add(DIGITS[units])
        return forms
    prefix = "muoi" if tens == 1 else f"{DIGITS[tens]} muoi"
    forms.add(f"{prefix} {DIGITS[units]}" if units else prefix)
    if units in (1, 4, 5):
        alternate = {1: "mot", 4: "tu", 5: "lam"}[units]
        forms.add(f"{prefix} {alternate}")
    return forms


def code_forms(code: str) -> set[str]:
    normalized = normalize(code)
    groups = normalized.split()
    if not groups or not all(group.isascii() and group.isdigit() for group in groups):
        return {normalized}
    forms = {
        " ".join(parts)
        for english in (False, True)
        for parts in product(*(spoken_group(group, english) for group in groups))
    }
    # STT realtime hay viết liền "4053" thay cho "4-053"; dữ liệu hiện không có hai mã nào trùng khi viết liền.
    forms.add("".join(groups))
    return forms


def best_matches(query: str, phrases: dict[str, set[str]]) -> set[str]:
    matches: set[str] = set()
    length = 0
    padded = f" {query} "
    for phrase, codes in phrases.items():
        if phrase and len(phrase) >= length and f" {phrase} " in padded:
            if len(phrase) > length:
                matches.clear()
                length = len(phrase)
            matches.update(codes)
    return matches


def one_word_off(heard: list[str], expected: list[str]) -> bool:
    # STT nghe sai thường chỉ lệch một chữ và giữ âm đầu ("tâm"→"tim", "mạch"→"mặt", "thuốc"→"thuốt");
    # nhờ vậy "tôi đã đặt" không bị coi là "soi dạ dày", "tìm đâu" không thành "giảm đau".
    diff = [(a, b) for a, b in zip(heard, expected) if a != b]
    return len(diff) == 1 and diff[0][0][0] == diff[0][1][0]


def fuzzy_matches(query: str, phrases: dict[str, set[str]]) -> set[str]:
    """Tên/bí danh gần giống nhất với một đoạn cùng số chữ trong câu (chỉ dùng khi không khớp chính xác)."""
    words = query.split()
    best, matches = FUZZY_MIN_RATIO, set()
    for phrase, codes in phrases.items():
        expected = phrase.split()
        if len(phrase) < FUZZY_MIN_LENGTH or len(expected) > len(words):
            continue
        for start in range(len(words) - len(expected) + 1):
            heard = words[start:start + len(expected)]
            if not one_word_off(heard, expected):
                continue
            score = SequenceMatcher(None, " ".join(heard), phrase).ratio()
            if score > best:
                best, matches = score, set(codes)
            elif score == best:
                matches |= codes
    return matches


def load_destinations(db, site, nodes, floors):
    departments = {
        dept.code: dept for dept in catalog.site_departments(db, site)
    }
    department_names = {record.id: record.name for record in departments.values()}
    department_codes = {record.id: record.code for record in departments.values()}
    targets: dict[str, tuple[Destination, int]] = {}
    for node in nodes.values():
        department = departments.get(node.code.removeprefix("ENTRY-"))
        if department and node.code.startswith("ENTRY-"):
            targets[department.code] = (
                Destination(
                    code=department.code, name=department.name, kind="department",
                    floor=floors[node.floor_id].level,
                    name_en=department.name_en, department_code=department.code,
                ),
                node.id,
            )

    for room in catalog.active_rooms(db, site):
        entrance = nodes.get(room.entrance_node_id)
        if entrance:
            targets[room.code] = (
                Destination(
                    code=room.code, name=room.name, kind="room",
                    floor=floors[entrance.floor_id].level,
                    department=department_names.get(room.department_id),
                    description=room.description,
                    department_code=department_codes.get(room.department_id),
                ),
                entrance.id,
            )
    return targets


def service_phrases(db, site, room_codes):
    phrases: dict[str, set[str]] = defaultdict(set)
    by_service: dict[int, set[str]] = defaultdict(set)
    for service_id, name, room_code in catalog.active_service_rooms(db, site):
        if room_code in room_codes:
            phrases[normalize(name)].add(room_code)
            by_service[service_id].add(room_code)
    for service_id, alias in catalog.active_service_aliases(db, site):
        if service_id in by_service:
            phrases[normalize(alias)].update(by_service[service_id])
    return phrases


def spoken_floor(query: str) -> tuple[int | None, str]:
    """Tầng khách nói ("tầng bốn", "4th floor") và phần câu còn lại (query đã normalize)."""
    floor = None
    floor_match = FLOOR.search(query)
    if floor_match:
        label = floor_match.group(1)
        floor = int(label) if label.isdecimal() else DIGITS.index("bon" if label == "tu" else label)
        query = FLOOR.sub(" ", query)
    else:
        floor_match = FLOOR_EN.search(query)
        if floor_match:
            label = floor_match.group(1) or floor_match.group(2)
            number = re.match(r"\d+", label)
            if number:
                floor = int(number.group())
            else:
                floor = EN_SMALL.index(label) if label in EN_SMALL else EN_ORDINALS.index(label)
            query = FLOOR_EN.sub(" ", query)
    return floor, " ".join(query.split())


def match_doctors(utterance, doctors):
    """Bác sĩ khách nhắc tên: họ tên đầy đủ, hoặc "bác sĩ Hùng" / "bác sĩ Văn Hùng" (phải có chữ "bác sĩ"
    vì tên riêng như "An", "Nam", "Long" cũng là chữ thường gặp). Khớp cụm dài nhất nên tên đầy đủ thắng tên gọi."""
    phrases: dict[str, set[str]] = defaultdict(set)
    for doctor in doctors:
        words = doctor.normalized_name.split()
        phrases[doctor.normalized_name].add(doctor.code)
        for size in range(1, len(words)):
            for prefix in DOCTOR_PREFIXES:
                phrases[f"{prefix} {' '.join(words[-size:])}"].add(doctor.code)
    found = best_matches(normalize(utterance), phrases)
    return [doctor for doctor in doctors if doctor.code in found]


def resolve(db, site, utterance, targets, prior_codes, fuzzy=True):
    """Trả về (mã điểm đến, cách khớp): "code" | "name" | "prior" (chỉ nói tầng) | "fuzzy" (cần xác nhận)."""
    floor, query = spoken_floor(normalize(utterance))

    written_codes = {normalize(match.group()) for match in WRITTEN_CODE.finditer(utterance)}
    if written_codes:
        matched = set()
        for written_code in written_codes:
            exact = {code for code in targets if normalize(code) == written_code}
            exact = exact or {code for code in targets if written_code in code_forms(code)}
            matched.update(exact)
        return sorted(code for code in matched if floor is None or targets[code][0].floor == floor), "code"

    codes_by_phrase: dict[str, set[str]] = defaultdict(set)
    names_by_phrase = service_phrases(db, site, targets)
    for code, (destination, _) in targets.items():
        for form in code_forms(code):
            codes_by_phrase[form].add(code)
        name = normalize(destination.name)
        names_by_phrase[name].add(code)
        if destination.kind == "department":
            names_by_phrase[DEPARTMENT_PREFIX.sub("", name)].add(code)
            if destination.name_en:
                english_name = normalize(destination.name_en)
                names_by_phrase[english_name].add(code)
                names_by_phrase[EN_DEPARTMENT_SUFFIX.sub("", english_name)].add(code)

    # Khách gọi tắt: "khoa nội tiết", "ung bướu" thay cho tên đầy đủ nhiều vế. Thêm sau cùng và
    # chỉ khi cụm chưa là tên/bí danh khác ("quầy lễ tân" đã là bí danh của phòng lễ tân).
    short_names = defaultdict(set)
    for code, (destination, _) in targets.items():
        if destination.kind == "department":
            for raw in DEPARTMENT_PARTS.split(destination.name):
                part = DEPARTMENT_PREFIX.sub("", normalize(raw)).removesuffix(" vinmec")
                if len(part.split()) >= 2 and part not in names_by_phrase:
                    short_names[part].add(code)
    names_by_phrase.update(short_names)

    room_digits = "|".join((*DIGITS, *EN_SMALL))
    explicit_room_code = re.search(rf"\b(?:phong|room) (?:\d|(?:{room_digits})\b)", query)
    matched, how = best_matches(query, codes_by_phrase), "code"
    if explicit_room_code:
        matched = {code for code in matched if targets[code][0].kind == "room"}
    elif not matched:
        matched, how = best_matches(query, names_by_phrase), "name"
    # A new named destination can start a fresh turn. A floor-only answer narrows the pending choices.
    if not matched and prior_codes and floor is not None and set(query.split()) <= FLOOR_FILLER:
        matched, how = set(prior_codes).intersection(targets), "prior"
    if not matched and fuzzy and not explicit_room_code:
        matched, how = fuzzy_matches(query, names_by_phrase), "fuzzy"
    if floor is not None:
        matched = {code for code in matched if targets[code][0].floor == floor}
    return sorted(matched), how
