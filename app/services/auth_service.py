from datetime import datetime, timezone
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.core.exceptions import AppError
from app.crud import user as user_crud


async def login(db: AsyncSession, username: str, password: str) -> dict:
    user = await user_crud.get_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        raise AppError(status_code=401, code=40101, message="用户名或密码错误")
    if not user.is_active:
        raise AppError(status_code=403, code=40300, message="账号已禁用")
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
    }


async def refresh_token(token: str, db: AsyncSession, redis: Redis) -> dict:
    try:
        payload = decode_token(token)
    except JWTError:
        raise AppError(status_code=401, code=40102, message="Token 无效或已过期")

    if payload.get("type") != "refresh":
        raise AppError(status_code=401, code=40102, message="Token 类型错误")

    jti = payload.get("jti")
    if await redis.exists(f"blacklist:{jti}"):
        raise AppError(status_code=401, code=40103, message="Token 已被吊销")

    user = await user_crud.get_by_id(db, int(payload["sub"]))
    if not user:
        raise AppError(status_code=401, code=40102, message="用户不存在")
    if not user.is_active:
        raise AppError(status_code=403, code=40300, message="账号已禁用")

    return {"access_token": create_access_token(user.id), "token_type": "bearer"}


async def logout(token: str, redis: Redis) -> None:
    try:
        payload = decode_token(token)
    except JWTError:
        return

    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp:
        remaining = int(exp) - int(datetime.now(timezone.utc).timestamp())
        if remaining > 0:
            await redis.setex(f"blacklist:{jti}", remaining, "1")
