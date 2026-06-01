import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.main import app
from app.db.base import Base
from app.dependencies import get_db
from app.crud.user import create_user
from app.models.user import User  # noqa: F401 — registers model with Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session():
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
async def mock_redis():
    r = AsyncMock()
    r.exists.return_value = 0
    r.setex.return_value = True
    r.ping.return_value = True
    return r


@pytest_asyncio.fixture
async def client(db_session, mock_redis):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with (
        patch("app.db.redis.init_redis", AsyncMock()),
        patch("app.db.redis.close_redis", AsyncMock()),
        patch("app.db.redis._redis_client", mock_redis),
        patch("app.db.redis.get_redis", return_value=mock_redis),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, mock_redis

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session):
    return await create_user(
        db_session,
        username="testuser",
        email="test@example.com",
        password="secret123",
    )
