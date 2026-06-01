import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.base import Base
from app.models.user import User  # noqa: F401 — registers model with Base
from app.crud.user import (
    get_by_id,
    get_by_username,
    get_by_email,
    create_user,
    update_user,
)
from app.schemas.user import UserUpdate

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_create_and_get_user(db):
    user = await create_user(db, "alice", "alice@example.com", "pass123")
    assert user.id is not None
    assert user.username == "alice"
    assert user.is_active is True

    fetched = await get_by_id(db, user.id)
    assert fetched is not None
    assert fetched.username == "alice"


async def test_get_by_username(db):
    await create_user(db, "bob", "bob@example.com", "pass")
    user = await get_by_username(db, "bob")
    assert user is not None
    assert user.email == "bob@example.com"

    missing = await get_by_username(db, "nobody")
    assert missing is None


async def test_get_by_email(db):
    await create_user(db, "carol", "carol@example.com", "pass")
    user = await get_by_email(db, "carol@example.com")
    assert user is not None


async def test_password_is_hashed(db):
    user = await create_user(db, "dave", "dave@example.com", "mypassword")
    assert user.hashed_password != "mypassword"
    assert len(user.hashed_password) > 20


async def test_update_user_email(db):
    user = await create_user(db, "eve", "eve@example.com", "pass")
    updated = await update_user(db, user, UserUpdate(email="newemail@example.com"))
    assert updated.email == "newemail@example.com"


async def test_update_user_password(db):
    from app.core.security import verify_password
    user = await create_user(db, "frank", "frank@example.com", "oldpass")
    await update_user(db, user, UserUpdate(password="newpass"))
    assert verify_password("newpass", user.hashed_password)
