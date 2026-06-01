from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_db
from app.db.redis import get_redis
from app.schemas.auth import LoginRequest, TokenResponse, AccessTokenResponse, RefreshRequest
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer()


@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.login(db, body.username, body.password)


@router.post("/refresh", response_model=AccessTokenResponse, summary="刷新 Access Token")
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.refresh_token(body.refresh_token, db, get_redis())


@router.post("/logout", summary="登出（加入黑名单）")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(_bearer)):
    await auth_service.logout(credentials.credentials, get_redis())
    return {"message": "登出成功"}
