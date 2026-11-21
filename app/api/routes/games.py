import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_broadcaster,
    get_current_user,
    get_db,
    get_dictionary_manager,
    get_notification_hook,
)
from app.engine.dictionary import DictionaryManager
from app.models.user import User
from app.realtime.broadcaster import EventBroadcaster
from app.schemas.common import ErrorResponse
from app.schemas.game import (
    CreateGameRequest,
    GameDetailResponse,
    GameOptionsResponse,
    GameSummaryResponse,
    MatchmakingRequest,
    MatchmakingResponse,
    MoveResponse,
    SubmitMoveRequest,
)
from app.services import game_service
from app.services.notification_service import NotificationHook

router = APIRouter(prefix="/games", tags=["games"])


@router.get(
    "/options",
    response_model=GameOptionsResponse,
    summary="Get supported game languages and turn durations",
    description="Returns enabled game dictionary languages and allowed per-turn hour options.",
)
async def get_options() -> GameOptionsResponse:
    return game_service.get_game_options()


@router.post(
    "",
    response_model=GameDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new game",
    description=(
        "Creates a waiting game with an immutable `language` and `turn_duration_hours`. "
        "Optionally invite a specific user via `opponent_username`."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Unsupported language or turn duration"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Invited opponent not found"},
    },
)
async def create_game(
    payload: CreateGameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GameDetailResponse:
    return await game_service.create_game(db, current_user, payload)


@router.post(
    "/matchmaking",
    response_model=MatchmakingResponse,
    summary="Find or create an open game",
    description=(
        "Matches the user with the oldest open waiting game matching `language` and "
        "`turn_duration_hours`, or creates/returns a waiting game if none is available."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Unsupported language or turn duration"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
    },
)
async def matchmake(
    payload: MatchmakingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    broadcaster: EventBroadcaster = Depends(get_broadcaster),
    notifier: NotificationHook = Depends(get_notification_hook),
) -> MatchmakingResponse:
    return await game_service.matchmake_game(
        db=db,
        user=current_user,
        payload=payload,
        broadcaster=broadcaster,
        notifier=notifier,
    )


@router.get(
    "",
    response_model=list[GameSummaryResponse],
    summary="List current user's games",
    description="Returns paginated games where the user is a participant or invited opponent.",
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
    },
)
async def list_games(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GameSummaryResponse]:
    return await game_service.list_user_games(
        db=db,
        user=current_user,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{game_id}",
    response_model=GameDetailResponse,
    summary="Get game state",
    description=(
        "Returns full board and player state filtered for the authenticated viewer "
        "(opponent rack tiles are hidden)."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not a game participant"},
        404: {"model": ErrorResponse, "description": "Game not found"},
    },
)
async def get_game(
    game_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GameDetailResponse:
    return await game_service.get_game_detail(db, current_user, game_id)


@router.post(
    "/{game_id}/join",
    response_model=GameDetailResponse,
    summary="Join a waiting game",
    description="Joins a waiting game, deals initial 7-tile racks, and starts the turn timer.",
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Invite-only game reserved for another user"},
        404: {"model": ErrorResponse, "description": "Game not found"},
        409: {"model": ErrorResponse, "description": "Game is not joinable or already full"},
    },
)
async def join_game(
    game_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    broadcaster: EventBroadcaster = Depends(get_broadcaster),
    notifier: NotificationHook = Depends(get_notification_hook),
) -> GameDetailResponse:
    return await game_service.join_game(
        db=db,
        user=current_user,
        game_id=game_id,
        broadcaster=broadcaster,
        notifier=notifier,
    )


@router.post(
    "/{game_id}/moves",
    response_model=GameDetailResponse,
    summary="Submit a game move",
    description="Submits a PLAY, PASS, SWAP, or RESIGN action on an active game.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid placement or dictionary word"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not a game participant"},
        404: {"model": ErrorResponse, "description": "Game not found"},
        409: {
            "model": ErrorResponse,
            "description": "Not your turn, version conflict, game not active, or turn expired",
        },
    },
)
async def submit_move(
    game_id: uuid.UUID,
    payload: SubmitMoveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    dictionary_manager: DictionaryManager = Depends(get_dictionary_manager),
    broadcaster: EventBroadcaster = Depends(get_broadcaster),
    notifier: NotificationHook = Depends(get_notification_hook),
) -> GameDetailResponse:
    return await game_service.submit_move(
        db=db,
        user=current_user,
        game_id=game_id,
        payload=payload,
        dictionary_manager=dictionary_manager,
        broadcaster=broadcaster,
        notifier=notifier,
    )


@router.get(
    "/{game_id}/moves",
    response_model=list[MoveResponse],
    summary="List game move history",
    description="Returns ordered moves; supports `since_move_number` for reconnect sync.",
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not a game participant"},
        404: {"model": ErrorResponse, "description": "Game not found"},
    },
)
async def list_moves(
    game_id: uuid.UUID,
    since_move_number: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MoveResponse]:
    moves = await game_service.get_game_moves(
        db=db,
        user=current_user,
        game_id=game_id,
        since_move_number=since_move_number,
        limit=limit,
    )
    return [MoveResponse.model_validate(m) for m in moves]
