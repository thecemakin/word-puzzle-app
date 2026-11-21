import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import status
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.exceptions import AppError

password_hasher = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:
    return password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


def _create_token(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    jti: Optional[str] = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if jti is not None:
        payload["jti"] = jti
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    return _create_token(
        subject=user_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    settings = get_settings()
    jti = str(uuid.uuid4())
    expires_delta = timedelta(days=settings.refresh_token_expire_days)
    expires_at = datetime.now(timezone.utc) + expires_delta
    token = _create_token(
        subject=user_id,
        token_type="refresh",
        expires_delta=expires_delta,
        jti=jti,
    )
    return token, jti, expires_at


def decode_token(token: str, expected_type: Optional[str] = None) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError(
            error_code="TOKEN_EXPIRED",
            message="Authentication token has expired",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(
            error_code="INVALID_TOKEN",
            message="Invalid authentication token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc

    if expected_type is not None and payload.get("type") != expected_type:
        raise AppError(
            error_code="INVALID_TOKEN_TYPE",
            message=f"Expected '{expected_type}' token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if not payload.get("sub"):
        raise AppError(
            error_code="INVALID_TOKEN",
            message="Token subject is missing",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    return payload
