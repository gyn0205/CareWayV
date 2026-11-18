from fastapi import APIRouter, Response

from app.core.config import settings
from app.core.dependencies import DbSession
from app.core.errors import redact_validation_input
from app.schema.wayfinding import Code, DirectionResult, KioskMap, Language, TextTurn, VoiceResult, VoiceTurn
from app.services.wayfinding import kiosk_map, process_text_turn
from app.services.wayfinding_voice import process_voice_turn

router = APIRouter(prefix=settings.WAYFINDING_PREFIX, tags=[settings.WAYFINDING_TAG])


@router.get("/kiosks/{kiosk_code}", response_model=KioskMap)
def wayfinding_kiosk(kiosk_code: Code, db: DbSession, response: Response, language: Language = "vi"):
    # Màn hình chờ cần bản đồ tầng ngay, trước khi khách hỏi đường.
    response.headers["Cache-Control"] = settings.WAYFINDING_CACHE_CONTROL
    return kiosk_map(db, kiosk_code, language)


@router.post("/text", response_model=DirectionResult)
def wayfinding_text(turn: TextTurn, db: DbSession, response: Response):
    response.headers["Cache-Control"] = settings.WAYFINDING_CACHE_CONTROL
    return process_text_turn(db, turn)


@router.post("/voice", response_model=VoiceResult)
@redact_validation_input
def wayfinding_voice(turn: VoiceTurn, db: DbSession, response: Response):
    response.headers["Cache-Control"] = settings.WAYFINDING_CACHE_CONTROL
    return process_voice_turn(db, turn)
