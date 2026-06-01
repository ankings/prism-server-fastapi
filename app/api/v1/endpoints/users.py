from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_db, get_current_active_user
from app.schemas.user import UserOut, UserUpdate
from app.models.user import User
from app.crud import user as user_crud

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut, summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.patch("/me", response_model=UserOut, summary="更新当前用户信息")
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await user_crud.update_user(db, current_user, body)
