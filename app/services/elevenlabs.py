"""Call ElevenLabs directly for speech-to-text (Scribe) and text-to-speech."""

import base64
import json
import logging
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings
from app.schema.wayfinding import Language, LanguagePreference
from app.services.openrouter import TIMEOUT_SECONDS, VoiceUnavailable

BASE_URL = "https://api.elevenlabs.io/v1"
AUDIO_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg", "webm": "audio/webm"}
logger = logging.getLogger(__name__)


def multipart(fields: dict[str, str], filename: str, content_type: str, data: bytes) -> tuple[bytes, str]:
    """Encode text fields plus one file as multipart/form-data."""
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in fields.items()
    ]
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n".encode() + data + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class ElevenLabsVoice:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def post(self, path: str, body: bytes, content_type: str, max_bytes: int) -> bytes:
        request = Request(
            f"{BASE_URL}/{path}",
            data=body,
            headers={"xi-api-key": self.api_key, "Content-Type": content_type},
            method="POST",
        )
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                data = response.read(max_bytes + 1)
        except HTTPError as error:
            # ElevenLabs puts the reason (quota, invalid key, voice not allowed) in the body.
            detail = error.read(500).decode(errors="replace")
            logger.warning("ElevenLabs %s returned HTTP %s: %s", path.split("/")[0], error.code, detail)
            error.close()
            raise VoiceUnavailable from None
        except (URLError, OSError) as error:
            logger.warning("ElevenLabs %s connection failed (%s)", path.split("/")[0], type(error).__name__)
            raise VoiceUnavailable from None
        if not data or len(data) > max_bytes:
            raise VoiceUnavailable
        return data

    def transcribe(
        self, encoded_audio: str, audio_format: str, language: LanguagePreference,
    ) -> tuple[str, str | None]:
        fields = {"model_id": settings.ELEVENLABS_STT_MODEL, "tag_audio_events": "false"}
        if language != "auto":
            fields["language_code"] = language
        body, content_type = multipart(
            fields, f"speech.{audio_format}", AUDIO_TYPES[audio_format], base64.b64decode(encoded_audio),
        )
        data = self.post("speech-to-text", body, content_type, 256_000)
        try:
            result = json.loads(data)
        except (ValueError, UnicodeError):
            raise VoiceUnavailable from None
        if not isinstance(result, dict) or not isinstance(result.get("text"), str):
            raise VoiceUnavailable
        # Scribe returns ISO 639-3 codes such as "vie" or "eng"; select_language understands both.
        detected = result.get("language_code")
        return result["text"].strip(), detected if isinstance(detected, str) else None

    def speak(self, text: str, language: Language) -> bytes:
        payload = {
            "text": text,
            "model_id": settings.ELEVENLABS_TTS_MODEL,
            "language_code": language,
        }
        audio = self.post(
            f"text-to-speech/{settings.ELEVENLABS_VOICE_ID}?output_format=mp3_44100_128",
            json.dumps(payload).encode(), "application/json", 4_000_000,
        )
        if not (audio.startswith(b"ID3") or (len(audio) > 2 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0)):
            raise VoiceUnavailable
        return audio
