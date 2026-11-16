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
