import logging
import uuid
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class NotificationHook(Protocol):
    """Hook interface for sending turn and game-end push notifications (FCM/APNs in Phase 7)."""

    async def notify_turn_started(
        self,
        user_id: uuid.UUID,
        ui_language: str,
        game_id: uuid.UUID,
    ) -> None: ...

    async def notify_game_finished(
        self,
        user_id: uuid.UUID,
        ui_language: str,
        game_id: uuid.UUID,
        reason: str,
        winner_id: Optional[uuid.UUID],
    ) -> None: ...


class LoggingNotificationHook:
    """Default MVP notification hook that logs structured events."""

    async def notify_turn_started(
        self,
        user_id: uuid.UUID,
        ui_language: str,
        game_id: uuid.UUID,
    ) -> None:
        logger.info(
            "notify_turn_started user_id=%s ui_language=%s game_id=%s",
            user_id,
            ui_language,
            game_id,
        )

    async def notify_game_finished(
        self,
        user_id: uuid.UUID,
        ui_language: str,
        game_id: uuid.UUID,
        reason: str,
        winner_id: Optional[uuid.UUID],
    ) -> None:
        logger.info(
            "notify_game_finished user_id=%s ui_language=%s game_id=%s reason=%s winner_id=%s",
            user_id,
            ui_language,
            game_id,
            reason,
            winner_id,
        )
