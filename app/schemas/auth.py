from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "cemakin",
                "email": "cem@example.com",
                "password": "StrongPassword123",
                "ui_language": "tr",
            }
        }
    )

    username: str = Field(
        min_length=3,
        max_length=32,
        pattern=r"^[a-zA-Z0-9_]+$",
        description="Unique username (case-insensitive, alphanumeric and underscore)",
    )
    email: str = Field(
        min_length=5,
        max_length=255,
        description="Unique email address",
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Account password (minimum 8 characters)",
    )
    ui_language: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=10,
        description="Preferred UI and notification language ('tr' or 'en')",
    )

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or "." not in cleaned.split("@")[-1]:
            raise ValueError("Invalid email address")
        return cleaned

    @field_validator("ui_language")
    @classmethod
    def normalize_ui_language(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().lower() if value is not None else None


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "identifier": "cemakin",
                "password": "StrongPassword123",
            }
        }
    )

    identifier: str = Field(
        min_length=3,
        max_length=255,
        description="Username or email address",
    )
    password: str = Field(min_length=1, max_length=128, description="Account password")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1, description="Active JWT refresh token")


class TokenResponse(BaseModel):
    access_token: str = Field(description="Short-lived JWT access token")
    refresh_token: str = Field(description="Long-lived rotating JWT refresh token")
    token_type: str = Field(default="bearer", description="Authorization scheme")
