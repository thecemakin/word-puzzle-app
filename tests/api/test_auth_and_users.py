import uuid
from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_db
from app.core.config import Settings, get_settings
from app.core.rate_limit import auth_rate_limiter
from app.main import app
from app.models.user import User
from tests.api.conftest import get_test_database_url


@pytest.fixture
def db_client() -> TestClient:
    auth_rate_limiter.reset()
    test_engine = create_async_engine(get_test_database_url(), poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    created_usernames: list[str] = []

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            client.created_usernames = created_usernames  # type: ignore[attr-defined]
            yield client
    finally:
        app.dependency_overrides.clear()
        if created_usernames:
            import asyncio

            async def _cleanup() -> None:
                async with session_factory() as session:
                    await session.execute(
                        delete(User).where(User.username.in_(created_usernames))
                    )
                    await session.commit()
                await test_engine.dispose()

            asyncio.run(_cleanup())


def test_register_login_refresh_and_profile_flow(db_client: TestClient) -> None:
    suffix = uuid.uuid4().hex[:8]
    username = f"user_{suffix}"
    email = f"{username}@example.com"
    db_client.created_usernames.append(username)  # type: ignore[attr-defined]

    # Register
    reg_res = db_client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": "StrongPassword123",
            "ui_language": "en",
        },
    )
    assert reg_res.status_code == 201
    user_data = reg_res.json()
    assert user_data["username"] == username
    assert user_data["email"] == email
    assert user_data["ui_language"] == "en"
    assert "password_hash" not in user_data

    # Duplicate username returns standardized error_code
    dup_res = db_client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"other_{suffix}@example.com",
            "password": "StrongPassword123",
        },
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["error_code"] == "USERNAME_ALREADY_EXISTS"

    # Login via email
    login_res = db_client.post(
        "/api/v1/auth/login",
        json={"identifier": email, "password": "StrongPassword123"},
    )
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert tokens["token_type"] == "bearer"
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Get /users/me
    me_res = db_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["username"] == username

    # Update ui_language via PATCH /users/me
    patch_res = db_client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"ui_language": "tr"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["ui_language"] == "tr"

    # Unsupported ui_language returns standardized error_code
    bad_lang_res = db_client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"ui_language": "xx"},
    )
    assert bad_lang_res.status_code == 400
    assert bad_lang_res.json()["error_code"] == "UNSUPPORTED_UI_LANGUAGE"

    # Refresh token rotation flow
    refresh_res = db_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 200
    new_tokens = refresh_res.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"]
    assert new_tokens["refresh_token"] != refresh_token

    # Reusing the old refresh token fails and revokes active sessions
    reuse_res = db_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert reuse_res.status_code == 401
    assert reuse_res.json()["error_code"] == "TOKEN_REVOKED"

    revoked_new_res = db_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_tokens["refresh_token"]},
    )
    assert revoked_new_res.status_code == 401
    assert revoked_new_res.json()["error_code"] == "TOKEN_REVOKED"

    # Access token cannot be used on refresh endpoint
    wrong_type_res = db_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert wrong_type_res.status_code == 401
    assert wrong_type_res.json()["error_code"] == "INVALID_TOKEN_TYPE"


def test_logout_case_insensitive_username_and_security_headers(db_client: TestClient) -> None:
    suffix = uuid.uuid4().hex[:8]
    username = f"CaseUser_{suffix}"
    email = f"case_{suffix}@example.com"
    db_client.created_usernames.append(username)  # type: ignore[attr-defined]

    reg = db_client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": "StrongPassword123"},
    )
    assert reg.status_code == 201
    assert reg.headers.get("X-Content-Type-Options") == "nosniff"
    assert reg.headers.get("X-Frame-Options") == "DENY"

    # Case-insensitive duplicate username rejected
    dup_case = db_client.post(
        "/api/v1/auth/register",
        json={
            "username": username.lower(),
            "email": f"other_{suffix}@example.com",
            "password": "StrongPassword123",
        },
    )
    assert dup_case.status_code == 409
    assert dup_case.json()["error_code"] == "USERNAME_ALREADY_EXISTS"

    login = db_client.post(
        "/api/v1/auth/login",
        json={"identifier": username.upper(), "password": "StrongPassword123"},
    )
    assert login.status_code == 200
    rt = login.json()["refresh_token"]

    logout_res = db_client.post("/api/v1/auth/logout", json={"refresh_token": rt})
    assert logout_res.status_code == 204

    after_logout = db_client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
    assert after_logout.status_code == 401
    assert after_logout.json()["error_code"] == "TOKEN_REVOKED"


def test_rate_limit_and_production_config_guard(db_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_auth_requests", 2)
    monkeypatch.setattr(get_settings(), "rate_limit_auth_window_seconds", 60)
    auth_rate_limiter.reset()

    for _ in range(2):
        res = db_client.post(
            "/api/v1/auth/login",
            json={"identifier": "nobody", "password": "wrong"},
        )
        assert res.status_code == 401

    limited = db_client.post(
        "/api/v1/auth/login",
        json={"identifier": "nobody", "password": "wrong"},
    )
    assert limited.status_code == 429
    assert limited.json()["error_code"] == "RATE_LIMIT_EXCEEDED"
    auth_rate_limiter.reset()

    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(app_env="production", debug=False)

    with pytest.raises(ValueError, match="DEBUG"):
        Settings(
            app_env="production",
            debug=True,
            jwt_secret_key="a-very-long-random-production-secret-key-12345",
        )


def test_auth_error_codes_and_validation_format(db_client: TestClient) -> None:
    unauth_res = db_client.get("/api/v1/users/me")
    assert unauth_res.status_code == 401
    assert unauth_res.json()["error_code"] == "AUTHENTICATION_REQUIRED"

    bad_token_res = db_client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert bad_token_res.status_code == 401
    assert bad_token_res.json()["error_code"] == "INVALID_TOKEN"

    bad_login_res = db_client.post(
        "/api/v1/auth/login",
        json={"identifier": "nobody_here", "password": "wrong"},
    )
    assert bad_login_res.status_code == 401
    assert bad_login_res.json()["error_code"] == "INVALID_CREDENTIALS"

    validation_res = db_client.post(
        "/api/v1/auth/register",
        json={"username": "a", "email": "bad", "password": "123"},
    )
    assert validation_res.status_code == 422
    assert validation_res.json()["error_code"] == "VALIDATION_ERROR"
