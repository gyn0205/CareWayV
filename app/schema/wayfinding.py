from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Language = Literal["vi", "en"]
LanguagePreference = Literal["auto", "vi", "en"]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Utterance = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class Clarification(BaseModel):
    kiosk_code: Code
    candidate_codes: list[Code] = Field(min_length=1, max_length=40)
    wheelchair: bool = False
    language: Language | None = None


class Turn(BaseModel):
    kiosk_code: Code
    wheelchair: bool = False
    context: Clarification | None = None
    language: LanguagePreference = "auto"


class TextTurn(Turn):
    text: Utterance


class VoiceTurn(Turn):
    audio_base64: str = Field(min_length=4, max_length=2_796_204)
    format: Literal["wav", "mp3", "webm"] = "wav"
    speak: bool = True


class Point(BaseModel):
    floor_id: int
    floor: int
    x: float | None
    y: float | None
    label: str | None
    map_asset_url: str | None


class Destination(BaseModel):
    code: str
    name: str
    name_en: str | None = None
    kind: Literal["room", "department"]
    floor: int
    department: str | None = None
    description: str | None = None


class Step(BaseModel):
    kind: Literal["walk", "elevator", "stairs"]
    seconds: int
    instruction: str
    start: Point
    end: Point


class MapArea(BaseModel):
    code: str
    x: int
    y: int
    width: int
    height: int


class MapZone(MapArea):
    name: str
    name_en: str
    # Số khu, màu và đường viền giống bảng mặt bằng thật (tùy chọn cho bản cũ).
    number: int | None = None
    tone: Literal["orange", "green", "desk"] | None = None
    outline: list[tuple[int, int]] = Field(default_factory=list)
    label_x: int | None = None
    label_y: int | None = None


class MapRoom(MapArea):
    door_side: Literal["north", "south"]
    zone: str | None = None  # mã khu chứa phòng (mã phòng không còn chứa mã khu)


class MapLandmark(BaseModel):
    code: str
    x: int
    y: int
    kind: Literal["elevator", "stairs", "restroom", "kiosk"]


class MapBlock(BaseModel):
    """Khối chỉ để vẽ: giếng trời, lõi thang máy, WC, thang thoát hiểm, giếng sảnh, bảng sơ đồ."""

    kind: Literal["sunroom", "void", "lift", "restroom", "exit_stair", "escalator", "board"]
    x: int
    y: int
    width: int
    height: int


class MapSign(BaseModel):
    x: int
    y: int


class FloorPlan(BaseModel):
    floor_id: int
    width: int
    height: int
    zones: list[MapZone]
    rooms: list[MapRoom]
    landmarks: list[MapLandmark]
    corridors: list[tuple[int, int, int, int]]
    hall: list[tuple[int, int]] = Field(default_factory=list)
    blocks: list[MapBlock] = Field(default_factory=list)
    exits: list[MapSign] = Field(default_factory=list)


class Route(BaseModel):
    destination: Destination
    origin: Point
    arrival: Point
    seconds: int
    steps: list[Step]
    floor_plans: list[FloorPlan] = Field(default_factory=list)


class MapFloor(BaseModel):
    floor_id: int
    floor: int
    map_asset_url: str | None


class KioskMap(BaseModel):
    """Bản đồ cho màn hình chờ: vị trí kiosk và mặt bằng mọi tầng, chưa cần tuyến."""

    kiosk_code: str
    origin: Point
    floors: list[MapFloor]
    floor_plans: list[FloorPlan] = Field(default_factory=list)


class DirectionResult(BaseModel):
    language: Language
    status: Literal["route", "clarify", "not_found", "no_route"]
    message: str
    candidates: list[Destination] = Field(default_factory=list)
    context: Clarification | None = None
    route: Route | None = None


class VoiceResult(DirectionResult):
    transcript: str
    speech_status: Literal["ok", "skipped", "unavailable"]
    audio_base64: str | None = None
    audio_media_type: Literal["audio/mpeg"] | None = None
