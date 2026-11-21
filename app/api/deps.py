import uuid
from collections.abc import AsyncGenerator
from typing import Optional

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import decode_token
from app.db.session import get_db_session
from app.engine.dictionary import DictionaryManager
from app.models.user import User
from app.realtime.broadcaster import EventBroadcaster
from app.services.notification_service import NotificationHook

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            error_code="AUTHENTICATION_REQUIRED",
            message="Bearer authentication token is required",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    claims = decode_token(credentials.credentials, expected_type="access")
    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError as exc:
        raise AppError(
            error_code="INVALID_TOKEN",
            message="Invalid token subject",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(
            error_code="USER_NOT_FOUND",
            message="User not found or inactive",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return user


def get_dictionary_manager(request: Request) -> DictionaryManager:
    return request.app.state.dictionaries


def get_broadcaster(request: Request) -> EventBroadcaster:
    return request.app.state.broadcaster


def get_notification_hook(request: Request) -> NotificationHook:
    return request.app.state.notifier
