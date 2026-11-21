import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import ws
from app.api.routes import auth, games, users
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, request_id_ctx
from app.db.session import AsyncSessionLocal, check_database_connection, engine
from app.engine.dictionary import DictionaryManager
from app.realtime.broadcaster import InMemoryBroadcaster
from app.services.notification_service import LoggingNotificationHook
from app.services.timeout_service import run_timeout_worker

settings = get_settings()
configure_logging(is_production=settings.is_production, debug=settings.debug)
logger = logging.getLogger("app.http")


@asynccontextmanager
async def lifespan(application: FastAPI):
    dict_manager = DictionaryManager(Path(settings.dictionaries_dir))
    dict_manager.load_languages(settings.game_languages)
    broadcaster = InMemoryBroadcaster()
    notifier = LoggingNotificationHook()

    application.state.dictionaries = dict_manager
    application.state.broadcaster = broadcaster
    application.state.notifier = notifier

    timeout_task = None
    if settings.timeout_check_interval_seconds > 0:
        timeout_task = asyncio.create_task(
            run_timeout_worker(
                session_factory=AsyncSessionLocal,
                broadcaster=broadcaster,
                notifier=notifier,
                interval_seconds=settings.timeout_check_interval_seconds,
            )
        )

    try:
        yield
    finally:
        if timeout_task is not None:
            timeout_task.cancel()
            with suppress(asyncio.CancelledError):
                await timeout_task
        await engine.dispose()


OPENAPI_TAGS = [
    {"name": "system", "description": "Service status and database health checks"},
    {"name": "auth", "description": "Registration, JWT login, token rotation, and logout"},
    {"name": "users", "description": "Authenticated user profile and UI language settings"},
    {"name": "games", "description": "Turn-based word games, matchmaking, and move submission"},
]


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Multiplayer, turn-based, multilingual word puzzle backend API. "
            "All errors follow a standard machine-readable `error_code` contract."
        ),
        openapi_tags=OPENAPI_TAGS,
        debug=settings.debug,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=lifespan,
    )
    register_exception_handlers(application)

    if settings.cors_origins_list:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @application.middleware("http")
    async def add_security_and_request_id_headers(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_ctx.set(req_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers.setdefault("X-Request-ID", req_id)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()",
        )
        logger.info(
            "%s %s -> %d (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    application.include_router(auth.router, prefix=settings.api_v1_prefix)
    application.include_router(users.router, prefix=settings.api_v1_prefix)
    application.include_router(games.router, prefix=settings.api_v1_prefix)
    application.include_router(ws.router, prefix=settings.api_v1_prefix)

    @application.get("/", tags=["system"])
    async def read_root() -> dict[str, Any]:
        return {
            "app": settings.app_name,
            "env": settings.app_env,
            "status": "running",
        }

    @application.get("/health", tags=["system"])
    async def health_check() -> JSONResponse:
        db_ok = await check_database_connection()
        if not db_ok:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "degraded", "database": "disconnected"},
            )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "database": "connected"},
        )

    return application


app = create_app()
