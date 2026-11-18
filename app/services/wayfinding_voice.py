"""Process one spoken turn using OpenRouter and the shared routing service."""

import base64
import binascii
import re
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import WayfindingError
from app.schema.wayfinding import DirectionResult, Language, VoiceResult, VoiceTurn
from app.services.elevenlabs import ElevenLabsVoice
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


def voice_provider() -> ElevenLabsVoice | OpenRouterVoice | None:
    """Prefer a direct ElevenLabs key, then OpenRouter; None when neither is set."""
    if settings.ELEVENLABS_API_KEY is not None:
        return ElevenLabsVoice(settings.ELEVENLABS_API_KEY.get_secret_value())
    if settings.OPENROUTER_API_KEY is not None:
        return OpenRouterVoice(settings.OPENROUTER_API_KEY.get_secret_value())
    return None


def not_configured(language: Language) -> WayfindingError:
    return WayfindingError("voice_not_configured", (
        "Voice is not configured. Please use the text wayfinding API." if language == "en" else
        "Chưa cấu hình giọng nói. Anh chị có thể dùng API chỉ đường bằng văn bản."
    ))


def realtime_session(language: Language) -> dict[str, str]:
    """WebSocket URL (with a single-use token) for live speech recognition in the kiosk browser."""
    if settings.ELEVENLABS_API_KEY is None:
        # Chỉ ElevenLabs có STT realtime; kiosk tự lùi về chế độ bấm để nói.
        raise not_configured(language)
    try:
        url = ElevenLabsVoice(settings.ELEVENLABS_API_KEY.get_secret_value()).realtime_url(language)
    except VoiceUnavailable:
        message = (
            "Live speech recognition is unavailable. Please try again." if language == "en" else
            "Chưa kết nối được nhận dạng giọng nói. Anh chị vui lòng thử lại."
        )
        raise WayfindingError("transcription_failed", message) from None
    return {"url": url}


def speech_stream(text: str, language: Language, pcm: bool = False) -> Iterator[bytes]:
    """Spoken reply as a stream; OpenRouter has no stream (nor PCM), so it sends the whole MP3 at once."""
    provider = voice_provider()
    if provider is None:
        raise not_configured(language)
    spoken = read_room_codes(text, language)
    try:
        if isinstance(provider, ElevenLabsVoice):
            return provider.stream(spoken, language, pcm)
        if pcm:
            raise VoiceUnavailable
        return iter([provider.speak(spoken, language)])
    except VoiceUnavailable:
        message = "Speech is unavailable." if language == "en" else "Chưa đọc được câu trả lời."
        raise WayfindingError("speech_failed", message) from None


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

    provider = voice_provider()
    if provider is None:
        raise not_configured(language)
    kiosk = kiosk_for(db, turn.kiosk_code, language)
    # Release the read transaction during both upstream audio calls.
    kiosk_code = kiosk.code
    db.rollback()
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
