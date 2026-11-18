"""Application configuration and typed environment settings."""

from http import HTTPStatus
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WAYFINDING_ERROR_STATUS = {
    "kiosk_not_found": HTTPStatus.NOT_FOUND,
    "kiosk_conflict": HTTPStatus.CONFLICT,
    "invalid_audio": HTTPStatus.UNPROCESSABLE_ENTITY,
    "voice_not_configured": HTTPStatus.SERVICE_UNAVAILABLE,
    "transcription_failed": HTTPStatus.BAD_GATEWAY,
    "speech_failed": HTTPStatus.BAD_GATEWAY,
}


class Settings(BaseSettings):
    DB_USER: str
    DB_PASSWORD: SecretStr
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str

    DATABASE_URL: SecretStr | None = None
    PROJECT_NAME: str = "CareWayV"
    API_V1_PREFIX: str = "/api/v1"
    WAYFINDING_PREFIX: str = "/wayfinding"
    WAYFINDING_TAG: str = "Wayfinding"
    WAYFINDING_CACHE_CONTROL: str = "no-store"
    WAYFINDING_ERROR_STATUS: dict[str, HTTPStatus] = Field(
        default_factory=DEFAULT_WAYFINDING_ERROR_STATUS.copy
    )
    OPENROUTER_API_KEY: SecretStr | None = None
    OPENROUTER_STT_MODEL: str = "openai/whisper-large-v3-turbo"
    OPENROUTER_TTS_MODEL: str = "elevenlabs/eleven-flash-v2.5"
    OPENROUTER_TTS_VOICE: str = "george"
    # When set, voice calls go straight to ElevenLabs instead of OpenRouter.
    ELEVENLABS_API_KEY: SecretStr | None = None
    ELEVENLABS_STT_MODEL: str = "scribe_v1"
    ELEVENLABS_TTS_MODEL: str = "eleven_flash_v2_5"
    ELEVENLABS_VOICE_ID: str = "JBFqnCBsd6RMkjVDRZzb"  # premade voice "George"
    # Hội thoại realtime: mic stream thẳng tới Scribe Realtime (cần ELEVENLABS_API_KEY).
    ELEVENLABS_REALTIME_MODEL: str = "scribe_v2_realtime"
    # Khách im lặng bao lâu thì coi là nói xong một đoạn; chỉnh theo độ ồn thực tế ở sảnh.
    VOICE_END_SILENCE_SECS: float = Field(default=0.5, ge=0.3, le=3.0)

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    @field_validator("WAYFINDING_ERROR_STATUS")
    @classmethod
    def merge_wayfinding_error_status(cls, overrides: dict[str, HTTPStatus]) -> dict[str, HTTPStatus]:
        return DEFAULT_WAYFINDING_ERROR_STATUS | overrides

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> URL:
        if self.DATABASE_URL is not None:
            return make_url(self.DATABASE_URL.get_secret_value())

        return URL.create(
            drivername="postgresql+psycopg",
            username=self.DB_USER,
            password=self.DB_PASSWORD.get_secret_value(),
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        )


settings = Settings()


def get_settings() -> Settings:
    return settings
