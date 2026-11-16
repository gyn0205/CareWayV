"""Use OpenRouter's dedicated audio endpoints with no conversation history."""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings
from app.schema.wayfinding import Language, LanguagePreference

BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT_SECONDS = 20
logger = logging.getLogger(__name__)


class VoiceUnavailable(Exception):
    pass


class OpenRouterVoice:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def post(self, path: str, payload: dict, max_bytes: int) -> bytes:
        request = Request(
            f"{BASE_URL}/audio/{path}",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                data = response.read(max_bytes + 1)
        except HTTPError as error:
            logger.warning("OpenRouter audio/%s returned HTTP %s", path, error.code)
            error.close()
            raise VoiceUnavailable from None
        except (URLError, OSError) as error:
            logger.warning("OpenRouter audio/%s connection failed (%s)", path, type(error).__name__)
            raise VoiceUnavailable from None
        if not data or len(data) > max_bytes:
            raise VoiceUnavailable
        return data

    def transcribe(
        self, encoded_audio: str, audio_format: str, language: LanguagePreference,
    ) -> tuple[str, str | None]:
        model = settings.OPENROUTER_STT_MODEL
        payload = {
            "model": model,
            "input_audio": {"data": encoded_audio, "format": audio_format},
        }
        if language != "auto":
            payload["language"] = language
        if model.startswith("openai/whisper"):
            payload["temperature"] = 0
            if language == "auto":
                payload["response_format"] = "verbose_json"
        data = self.post("transcriptions", payload, 256_000)
        try:
            result = json.loads(data)
        except (ValueError, UnicodeError):
            raise VoiceUnavailable from None
        if not isinstance(result, dict) or not isinstance(result.get("text"), str):
            raise VoiceUnavailable
        detected = result.get("language")
        return result["text"].strip(), detected if isinstance(detected, str) else None

    def speak(self, text: str, language: Language) -> bytes:
        model = settings.OPENROUTER_TTS_MODEL
        payload = {
            "model": model, "input": text, "voice": settings.OPENROUTER_TTS_VOICE,
            "response_format": "mp3",
        }
        if model.startswith("elevenlabs/"):
            payload["provider"] = {"options": {"elevenlabs": {"language_code": language}}}
        audio = self.post("speech", payload, 4_000_000)
        if not (audio.startswith(b"ID3") or (len(audio) > 2 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0)):
            raise VoiceUnavailable
        return audio
