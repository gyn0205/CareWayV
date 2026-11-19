"""Select the language for a wayfinding response."""

import re
import unicodedata

from app.schema.wayfinding import Language, LanguagePreference

ENGLISH_HINTS = {
    "at", "bill", "can", "cardiovascular", "cashier", "center", "clinic", "department",
    "directions", "elevator", "endoscopy", "find", "floor", "go", "help", "how", "i",
    "is", "lift", "me", "need", "on", "pay", "pharmacy", "please", "room", "sample",
    "take", "the", "to", "want", "wheelchair", "where",
}
VIETNAMESE_HINTS = {
    "anh", "ben", "benh", "can", "chi", "den", "di", "duong", "kham", "khoa",
    "muon", "nha", "phong", "tang", "tim", "toi", "vien",
}


YES = {"co", "dung", "vang", "da", "u", "phai", "roi", "ok", "oke", "okay", "yes", "yeah", "yep", "sure", "correct", "right"}
NO = {"khong", "chua", "sai", "no", "nope", "not", "wrong"}


def yes_no(text: str) -> bool | None:
    """Khách đồng ý (True), từ chối (False) hay nói điều khác (None). Có chữ phủ định thì coi là từ chối."""
    words = set(normalize(text).split())
    if words & NO:
        return False
    return True if words & YES else None


# Khách tự nói về lịch hẹn ngay trong câu hỏi. Xét phủ định trước vì "chưa có lịch" chứa "có lịch".
NO_APPOINTMENT = (
    "chua dat lich", "chua co lich", "chua co hen", "khong co lich", "khong co hen", "chua hen",
    "no appointment", "not booked", "haven t booked", "don t have an appointment",
    "do not have an appointment", "without an appointment",
)
HAS_APPOINTMENT = (
    "da dat lich", "dat lich roi", "co lich", "co hen", "da hen", "bac si hen",
    "have an appointment", "got an appointment", "my appointment", "already booked", "i booked", "i have booked",
)


def has_phrase(text: str, phrases) -> bool:
    padded = f" {normalize(text)} "
    return any(f" {phrase} " in padded for phrase in phrases)


def stated_appointment(text: str) -> bool | None:
    """Câu có nói rõ đã/chưa có lịch hẹn không ("tôi có hẹn khám ở khoa tim")."""
    if has_phrase(text, NO_APPOINTMENT):
        return False
    return True if has_phrase(text, HAS_APPOINTMENT) else None


def appointment_answer(text: str) -> bool | None:
    """Câu đáp cho "Anh chị đã đặt lịch chưa?": "rồi" / "chưa" / "có" / "không"…"""
    stated = stated_appointment(text)
    if stated is not None:
        return stated
    # "chưa" chắc chắn là chưa; "rồi" thắng "không" ("không, tôi đặt rồi"); còn lại như có/không thường.
    if has_phrase(text, ("chua", "not yet", "haven t", "have not", "don t", "do not", "didn t", "did not")):
        return False
    if has_phrase(text, ("roi", "da dat", "i have", "i do", "i did", "already")):
        return True
    return yes_no(text)


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    without_marks = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(re.findall(r"[^\W_]+", without_marks))


def select_language(
    preference: LanguagePreference,
    text: str = "",
    previous: Language | None = None,
    detected: str | None = None,
) -> Language:
    if preference != "auto":
        return preference
    if detected:
        tag = detected.casefold().split("-")[0].strip()
        if tag in {"en", "eng", "english"}:
            return "en"
        if tag in {"vi", "vie", "vietnamese"}:
            return "vi"
    decomposed = unicodedata.normalize("NFD", text)
    if any(unicodedata.combining(char) or char in "đĐ" for char in decomposed):
        return "vi"
    words = set(normalize(text).split())
    if len(words & VIETNAMESE_HINTS) > len(words & ENGLISH_HINTS):
        return "vi"
    if words & ENGLISH_HINTS:
        return "en"
    return previous or "vi"
