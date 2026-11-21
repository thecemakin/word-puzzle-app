import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import BOARD_SIZE, RACK_SIZE


class LanguageOption(BaseModel):
    code: str = Field(description="ISO-like game language code (e.g. 'tr', 'en')")
    name: str = Field(description="Display name of the game language")


class GameOptionsResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "languages": [
                    {"code": "tr", "name": "Türkçe"},
                    {"code": "en", "name": "English"},
                ],
                "turn_duration_hours": [12, 24, 48, 72],
            }
        }
    )

    languages: list[LanguageOption] = Field(description="Supported game dictionary languages")
    turn_duration_hours: list[int] = Field(
        description="Allowed per-turn time limits in hours"
    )


class CreateGameRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "language": "tr",
                "turn_duration_hours": 24,
                "opponent_username": None,
            }
        }
    )

    language: str = Field(
        min_length=2,
        max_length=10,
        description="Immutable dictionary & tile-set language for this game",
    )
    turn_duration_hours: int = Field(
        description="Per-turn timeout in hours (must be in /games/options)",
    )
    opponent_username: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=32,
        description="Optional opponent username for a private invite; omit for an open game",
    )


class MatchmakingRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"language": "tr", "turn_duration_hours": 24}},
    )

    language: str = Field(min_length=2, max_length=10, description="Desired game language")
    turn_duration_hours: int = Field(description="Desired per-turn timeout in hours")


class TilePlacementInput(BaseModel):
    row: int = Field(ge=0, lt=BOARD_SIZE, description="0-based board row index (0..14)")
    col: int = Field(ge=0, lt=BOARD_SIZE, description="0-based board column index (0..14)")
    letter: str = Field(
        min_length=1,
        max_length=2,
        description="Placed letter (if is_blank=True, the letter assigned to the blank tile)",
    )
    is_blank: bool = Field(
        default=False,
        description="True if this placement uses a blank ('*') wildcard tile",
    )


class SubmitMoveRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "move_type": "PLAY",
                "placements": [
                    {"row": 7, "col": 6, "letter": "E", "is_blank": False},
                    {"row": 7, "col": 7, "letter": "L", "is_blank": False},
                    {"row": 7, "col": 8, "letter": "M", "is_blank": False},
                    {"row": 7, "col": 9, "letter": "A", "is_blank": False},
                ],
                "tiles_to_swap": [],
                "expected_version": 2,
            }
        }
    )

    move_type: Literal["PLAY", "PASS", "SWAP", "RESIGN"] = Field(
        description="Action type for the turn",
    )
    placements: list[TilePlacementInput] = Field(
        default_factory=list,
        max_length=RACK_SIZE,
        description="Board tile placements (required when move_type='PLAY')",
    )
    tiles_to_swap: list[str] = Field(
        default_factory=list,
        max_length=RACK_SIZE,
        description="Rack tiles to exchange with the bag (required when move_type='SWAP')",
    )
    expected_version: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional optimistic locking version from the latest game state",
    )

    @field_validator("tiles_to_swap")
    @classmethod
    def validate_tiles_to_swap(cls, tiles: list[str]) -> list[str]:
        for tile in tiles:
            if not tile or len(tile) > 2:
                raise ValueError("Each tile in tiles_to_swap must be 1 or 2 characters")
        return tiles


class GamePlayerResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    seat_order: int
    score: int
    rack_count: int
    is_me: bool
    rack: Optional[list[str]] = Field(
        default=None,
        description="Player's rack tiles; null for opponents (anti-cheat)",
    )


class GameSummaryResponse(BaseModel):
    id: uuid.UUID
    language: str
    turn_duration_hours: int
    status: str
    current_turn_user_id: Optional[uuid.UUID]
    invited_user_id: Optional[uuid.UUID]
    turn_expires_at: Optional[datetime]
    move_count: int
    version: int
    winner_id: Optional[uuid.UUID]
    finish_reason: Optional[str]
    created_at: datetime
    finished_at: Optional[datetime]
    players: list[GamePlayerResponse]


class GameDetailResponse(GameSummaryResponse):
    board_state: list[list[Optional[dict[str, Any]]]]
    bag_remaining: int = Field(description="Number of tiles remaining in the bag")
    consecutive_passes: int


class MoveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    game_id: uuid.UUID
    user_id: Optional[uuid.UUID]
    move_number: int
    move_type: str
    placements: list[dict[str, Any]]
    words_formed: list[dict[str, Any]]
    score_gained: int
    created_at: datetime


class MatchmakingResponse(BaseModel):
    matched: bool = Field(
        description="True if joined an existing open game; False if waiting in queue",
    )
    game: GameDetailResponse
