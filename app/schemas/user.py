import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "b3b8c9d0-1234-4a5b-8c9d-0123456789ab",
                "username": "cemakin",
                "email": "cem@example.com",
                "ui_language": "tr",
                "is_active": True,
                "created_at": "2026-11-21T10:00:00Z",
            }
        },
    )

    id: uuid.UUID = Field(description="Unique user identifier")
    username: str = Field(description="Public username")
    email: str = Field(description="User email address")
    ui_language: str = Field(description="Preferred application UI/notification language")
    is_active: bool = Field(description="Whether the account is active")
    created_at: datetime = Field(description="Account creation timestamp (UTC)")


class UserUpdateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"ui_language": "en"}},
    )

    ui_language: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=10,
        description="Preferred application UI and notification language ('tr' or 'en')",
    )

    @field_validator("ui_language")
    @classmethod
    def normalize_ui_language(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().lower() if value is not None else None
