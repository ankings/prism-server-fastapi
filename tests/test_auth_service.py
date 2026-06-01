import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.base import Base
from app.models.user import User  # noqa: F401 — registers model with Base
from app.crud.user import create_user
from app.core.exceptions import AppError
from app.services.auth_service import login, refresh_token, logout

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def user(db):
    return await create_user(db, "testuser", "test@example.com", "correct_password")


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.exists.return_value = 0
    r.setex.return_value = True
    return r


async def test_login_success(db, user):
    result = await login(db, "testuser", "correct_password")
    assert "access_token" in result
    assert "refresh_token" in result
    assert result["token_type"] == "bearer"


async def test_login_wrong_password(db, user):
    with pytest.raises(AppError) as exc:
        await login(db, "testuser", "wrong_password")
    assert exc.value.status_code == 401
    assert exc.value.code == 40101


async def test_login_unknown_user(db):
    with pytest.raises(AppError) as exc:
        await login(db, "nobody", "pass")
    assert exc.value.status_code == 401


async def test_login_inactive_user(db):
    user = await create_user(db, "inactive", "inactive@example.com", "pass")
    user.is_active = False
    await db.commit()
    with pytest.raises(AppError) as exc:
        await login(db, "inactive", "pass")
    assert exc.value.status_code == 403
    assert exc.value.code == 40300


async def test_refresh_token_success(db, user, mock_redis):
    tokens = await login(db, "testuser", "correct_password")
    result = await refresh_token(tokens["refresh_token"], db, mock_redis)
    assert "access_token" in result


async def test_refresh_with_access_token_fails(db, user, mock_redis):
    tokens = await login(db, "testuser", "correct_password")
    with pytest.raises(AppError) as exc:
        await refresh_token(tokens["access_token"], db, mock_redis)
    assert exc.value.status_code == 401


async def test_refresh_blacklisted_token(db, user, mock_redis):
    tokens = await login(db, "testuser", "correct_password")
    mock_redis.exists.return_value = 1
    with pytest.raises(AppError) as exc:
        await refresh_token(tokens["refresh_token"], db, mock_redis)
    assert exc.value.code == 40103


async def test_logout_adds_to_blacklist(mock_redis):
    from app.core.security import create_access_token
    token = create_access_token(1)
    await logout(token, mock_redis)
    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args[0]
    assert call_args[0].startswith("blacklist:")
    assert call_args[2] == "1"


async def test_logout_invalid_token_no_error(mock_redis):
    await logout("invalid.token.here", mock_redis)
    mock_redis.setex.assert_not_called()
