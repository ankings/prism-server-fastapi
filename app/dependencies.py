from typing import AsyncGenerator
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import async_session_factory
from app.db.redis import get_redis
from app.core.security import decode_token
from app.core.exceptions import AppError
from app.crud import user as user_crud
from app.models.user import User

_bearer = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        raise AppError(status_code=401, code=40102, message="Token 无效或已过期")

    if payload.get("type") != "access":
        raise AppError(status_code=401, code=40102, message="Token 类型错误")

    jti = payload.get("jti")
    redis = get_redis()
    if await redis.exists(f"blacklist:{jti}"):
        raise AppError(status_code=401, code=40103, message="Token 已被吊销")

    user = await user_crud.get_by_id(db, int(payload["sub"]))
    if not user:
        raise AppError(status_code=401, code=40102, message="用户不存在")
    return user


async def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    if not user.is_active:
        raise AppError(status_code=403, code=40300, message="账号已禁用")
    return user
