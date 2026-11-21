from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error_code": "INVALID_WORD",
                "message": "Invalid word(s): XYZ",
                "details": {"invalid_words": ["XYZ"]},
            }
        }
    )

    error_code: str = Field(
        description="Machine-readable error code for client-side localization",
    )
    message: str = Field(description="Human-readable English error description")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured context about the error",
    )
