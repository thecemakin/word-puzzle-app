from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.user import UserResponse, UserUpdateRequest
from app.services.auth_service import update_user_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Returns the authenticated user's profile and UI language preference.",
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid bearer token"},
    },
)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update current user settings",
    description="Updates user preferences such as `ui_language` ('tr' or 'en').",
    responses={
        400: {"model": ErrorResponse, "description": "Unsupported UI language"},
        401: {"model": ErrorResponse, "description": "Missing or invalid bearer token"},
    },
)
async def update_me(
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    updated = await update_user_profile(db, current_user, payload)
    return UserResponse.model_validate(updated)
