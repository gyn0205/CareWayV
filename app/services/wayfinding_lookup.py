"""Match a kiosk utterance against destinations and service aliases in its site."""

import re
from collections import defaultdict
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
FLOOR_FILLER = {
    "o", "tren", "duoi", "a", "nhe", "nha", "vang", "dung", "roi",
    "on", "at", "the", "please", "yes", "it", "s", "is",
}
MAX_CANDIDATES = 40


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


def load_destinations(db, site, nodes, floors):
    departments = {
        dept.code: dept for dept in catalog.site_departments(db, site)
    }
    department_names = {record.id: record.name for record in departments.values()}
    targets: dict[str, tuple[Destination, int]] = {}
    for node in nodes.values():
        department = departments.get(node.code.removeprefix("ENTRY-"))
        if department and node.code.startswith("ENTRY-"):
            targets[department.code] = (
                Destination(
                    code=department.code, name=department.name, kind="department",
                    floor=floors[node.floor_id].level,
                    name_en=department.name_en,
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


def resolve(db, site, utterance, targets, prior_codes):
    query = normalize(utterance)
    floor_match = FLOOR.search(query)
    floor = None
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
    query = " ".join(query.split())

    written_codes = {normalize(match.group()) for match in WRITTEN_CODE.finditer(utterance)}
    if written_codes:
        matched = set()
        for written_code in written_codes:
            exact = {code for code in targets if normalize(code) == written_code}
            exact = exact or {code for code in targets if written_code in code_forms(code)}
            matched.update(exact)
        return sorted(code for code in matched if floor is None or targets[code][0].floor == floor)

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

    room_digits = "|".join((*DIGITS, *EN_SMALL))
    explicit_room_code = re.search(rf"\b(?:phong|room) (?:\d|(?:{room_digits})\b)", query)
    matched = best_matches(query, codes_by_phrase)
    if explicit_room_code:
        matched = {code for code in matched if targets[code][0].kind == "room"}
    else:
        matched = matched or best_matches(query, names_by_phrase)
    # A new named destination can start a fresh turn. A floor-only answer narrows the pending choices.
    if not matched and prior_codes and floor is not None and set(query.split()) <= FLOOR_FILLER:
        matched = set(prior_codes).intersection(targets)
    if floor is not None:
        matched = {code for code in matched if targets[code][0].floor == floor}
    return sorted(matched)
