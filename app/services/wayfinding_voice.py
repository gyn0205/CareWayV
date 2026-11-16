"""Process one spoken turn using OpenRouter and the shared routing service."""

import base64
import binascii
import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import WayfindingError
from app.schema.wayfinding import DirectionResult, Language, VoiceResult, VoiceTurn
from app.services.openrouter import OpenRouterVoice, VoiceUnavailable
from app.services.wayfinding import find_route, kiosk_context, kiosk_for
from app.services.wayfinding_language import select_language

DIGITS = {
    "vi": ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"),
    "en": ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"),
}
ROOM_CODE = re.compile(r"\b\d+(?:-\d+)+\b")


def read_room_codes(text: str, language: Language) -> str:
    digits = DIGITS[language]
    return ROOM_CODE.sub(
        lambda match: ", ".join(
            " ".join(digits[int(digit)] for digit in group) for group in match.group().split("-")
        ),
        text,
    )


def process_voice_turn(db: Session, turn: VoiceTurn) -> VoiceResult:
    context = kiosk_context(turn)
    previous = context.language if context else None
    language = select_language(turn.language, previous=previous)
    try:
        decoded = base64.b64decode(turn.audio_base64, validate=True)
    except (binascii.Error, ValueError):
        message = "Invalid base64 audio." if language == "en" else "Audio base64 không hợp lệ."
        raise WayfindingError("invalid_audio", message) from None
    if not decoded or len(decoded) > 2_097_152:
        message = (
            "Audio must contain between 1 byte and 2 MiB." if language == "en" else
            "Audio cần có kích thước từ 1 byte đến 2 MiB."
        )
        raise WayfindingError("invalid_audio", message)

    key = settings.OPENROUTER_API_KEY
    if key is None:
        message = (
            "OpenRouter is not configured. Please use the text wayfinding API." if language == "en" else
            "Chưa cấu hình OpenRouter. Anh chị có thể dùng API chỉ đường bằng văn bản."
        )
        raise WayfindingError("voice_not_configured", message)
    kiosk = kiosk_for(db, turn.kiosk_code, language)
    # Release the read transaction during both upstream audio calls.
    kiosk_code = kiosk.code
    db.rollback()
    provider = OpenRouterVoice(key.get_secret_value())
    try:
        transcript, detected = provider.transcribe(turn.audio_base64, turn.format, turn.language)
    except VoiceUnavailable:
        message = (
            "Speech recognition failed. Please try again or enter the room code." if language == "en" else
            "Không nhận dạng được giọng nói. Anh chị vui lòng thử lại hoặc nhập mã phòng."
        )
        raise WayfindingError("transcription_failed", message) from None

    language = select_language(turn.language, transcript, previous, detected)
    if transcript:
        kiosk = kiosk_for(db, kiosk_code, language)
        result = find_route(db, kiosk, transcript, turn.wheelchair, context, language)
        db.rollback()
    else:
        result = DirectionResult(
            status="not_found", language=language,
            message=(
                "I did not catch that. Please repeat the department or room code." if language == "en" else
                "Tôi chưa nghe rõ. Anh chị vui lòng nói lại tên khoa hoặc mã phòng."
            ),
            context=context.model_copy(update={"language": language}) if context else None,
        )
    voice = VoiceResult(**result.model_dump(), transcript=transcript, speech_status="skipped")
    if turn.speak:
        try:
            audio = provider.speak(read_room_codes(result.message, language), language)
        except VoiceUnavailable:
            voice.speech_status = "unavailable"
        else:
            voice.speech_status = "ok"
            voice.audio_base64 = base64.b64encode(audio).decode("ascii")
            voice.audio_media_type = "audio/mpeg"
    return voice
