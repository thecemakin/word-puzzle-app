from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.rate_limit import enforce_auth_rate_limit
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.common import ErrorResponse
from app.schemas.user import UserResponse
from app.services.auth_service import (
    authenticate_user,
    refresh_user_tokens,
    register_user,
    revoke_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_auth_rate_limit)],
    summary="Register a new user account",
    description="Creates a new user with a unique case-insensitive username and email.",
    responses={
        400: {"model": ErrorResponse, "description": "Unsupported UI language"},
        409: {"model": ErrorResponse, "description": "Username or email already exists"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await register_user(db, payload)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_auth_rate_limit)],
    summary="Authenticate and obtain JWT tokens",
    description="Accepts username (case-insensitive) or email along with password.",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        403: {"model": ErrorResponse, "description": "Inactive user account"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    return await authenticate_user(db, payload)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_auth_rate_limit)],
    summary="Rotate refresh token and issue a new token pair",
    description="Revokes the submitted refresh token and returns fresh access/refresh tokens.",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid, expired, or revoked token"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def refresh(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    return await refresh_user_tokens(db, payload.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_auth_rate_limit)],
    summary="Revoke a refresh token",
    description="Invalidates the provided refresh token so it can no longer be used.",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid refresh token"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def logout(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    await revoke_refresh_token(db, payload.refresh_token)
