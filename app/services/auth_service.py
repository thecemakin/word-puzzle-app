import uuid
from datetime import datetime, timezone

from fastapi import status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserUpdateRequest

SUPPORTED_UI_LANGUAGES = frozenset({"tr", "en"})


def _validate_ui_language(ui_language: str) -> str:
    normalized = ui_language.strip().lower()
    if normalized not in SUPPORTED_UI_LANGUAGES:
        raise AppError(
            error_code="UNSUPPORTED_UI_LANGUAGE",
            message=f"Unsupported UI language: '{ui_language}'",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"supported": sorted(SUPPORTED_UI_LANGUAGES)},
        )
    return normalized


async def _issue_token_pair(db: AsyncSession, user_id: uuid.UUID) -> TokenResponse:
    user_id_str = str(user_id)
    access_token = create_access_token(user_id_str)
    refresh_token, jti, expires_at = create_refresh_token(user_id_str)

    db.add(
        RefreshToken(
            user_id=user_id,
            jti=jti,
            expires_at=expires_at,
        )
    )
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


async def register_user(db: AsyncSession, payload: RegisterRequest) -> User:
    settings = get_settings()
    ui_lang = _validate_ui_language(payload.ui_language or settings.default_ui_language)

    existing = await db.scalar(
        select(User).where(
            or_(
                func.lower(User.username) == payload.username.lower(),
                User.email == payload.email,
            )
        )
    )
    if existing is not None:
        if existing.username.lower() == payload.username.lower():
            raise AppError(
                error_code="USERNAME_ALREADY_EXISTS",
                message="Username is already taken",
                status_code=status.HTTP_409_CONFLICT,
            )
        raise AppError(
            error_code="EMAIL_ALREADY_EXISTS",
            message="Email address is already registered",
            status_code=status.HTTP_409_CONFLICT,
        )

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        ui_language=ui_lang,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, payload: LoginRequest) -> TokenResponse:
    identifier = payload.identifier.strip()
    user = await db.scalar(
        select(User).where(
            or_(
                func.lower(User.username) == identifier.lower(),
                User.email == identifier.lower(),
            )
        )
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError(
            error_code="INVALID_CREDENTIALS",
            message="Invalid username/email or password",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if not user.is_active:
        raise AppError(
            error_code="USER_INACTIVE",
            message="User account is inactive",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    return await _issue_token_pair(db, user.id)


async def refresh_user_tokens(db: AsyncSession, refresh_token: str) -> TokenResponse:
    claims = decode_token(refresh_token, expected_type="refresh")
    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError as exc:
        raise AppError(
            error_code="INVALID_TOKEN",
            message="Invalid token subject",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc

    jti = claims.get("jti")
    if not jti:
        raise AppError(
            error_code="INVALID_TOKEN",
            message="Token identifier (jti) is missing",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    stored_token = await db.scalar(
        select(RefreshToken).where(RefreshToken.jti == jti).with_for_update()
    )
    if stored_token is None:
        raise AppError(
            error_code="TOKEN_REVOKED",
            message="Refresh token is invalid or revoked",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    now = datetime.now(timezone.utc)
    if stored_token.revoked_at is not None:
        # Possible refresh token reuse detected: revoke all active sessions for this user
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()
        raise AppError(
            error_code="TOKEN_REVOKED",
            message="Refresh token has already been used or revoked",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(
            error_code="USER_NOT_FOUND",
            message="User account not found or inactive",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # Rotate: revoke the used token and issue a fresh pair
    stored_token.revoked_at = now
    return await _issue_token_pair(db, user.id)


async def revoke_refresh_token(db: AsyncSession, refresh_token: str) -> None:
    claims = decode_token(refresh_token, expected_type="refresh")
    jti = claims.get("jti")
    if not jti:
        return
    stored_token = await db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    if stored_token is not None and stored_token.revoked_at is None:
        stored_token.revoked_at = datetime.now(timezone.utc)
        await db.commit()


async def update_user_profile(
    db: AsyncSession,
    user: User,
    payload: UserUpdateRequest,
) -> User:
    if payload.ui_language is not None:
        user.ui_language = _validate_ui_language(payload.ui_language)
    await db.commit()
    await db.refresh(user)
    return user
