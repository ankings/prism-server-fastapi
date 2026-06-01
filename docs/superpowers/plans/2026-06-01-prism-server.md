# prism-server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个生产级 FastAPI 通用 API 脚手架，内置 JWT+Redis 认证，使用 MySQL，通过 systemd 部署在裸金属/VM 上。

**Architecture:** 分层架构（Router → Service → CRUD → DB），全程异步（SQLAlchemy 2.x + aiomysql），JWT Token 通过 Redis 黑名单支持主动吊销。异常统一格式，loguru 结构化日志，请求 ID 中间件贯穿全链路。

**Tech Stack:** FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2.x (async), aiomysql, Alembic, redis-py (asyncio), python-jose[cryptography], passlib[bcrypt], loguru, uvicorn, gunicorn, uv, pytest, pytest-asyncio, httpx, aiosqlite

---

## 文件职责表

| 文件 | 职责 |
|------|------|
| `pyproject.toml` | uv 依赖管理 |
| `app/config.py` | pydantic-settings 读取 .env |
| `app/main.py` | FastAPI 实例、lifespan、中间件、路由挂载 |
| `app/dependencies.py` | get_db、get_current_user、get_current_active_user |
| `app/db/base.py` | async engine、session factory、DeclarativeBase |
| `app/db/redis.py` | Redis 连接池 init/close/get |
| `app/core/security.py` | bcrypt 哈希/校验、JWT 签发/解析 |
| `app/core/exceptions.py` | AppError、全局异常 handler |
| `app/core/logging.py` | loguru 初始化 |
| `app/models/user.py` | User ORM 模型 |
| `app/schemas/common.py` | ErrorResponse |
| `app/schemas/auth.py` | LoginRequest、TokenResponse、RefreshRequest |
| `app/schemas/user.py` | UserOut、UserUpdate |
| `app/crud/user.py` | get_by_id、get_by_username、get_by_email、create、update |
| `app/services/auth_service.py` | login、refresh_token、logout 业务逻辑 |
| `app/api/v1/router.py` | 聚合 v1 路由 |
| `app/api/v1/endpoints/auth.py` | /login /refresh /logout |
| `app/api/v1/endpoints/users.py` | /users/me GET+PATCH |
| `tests/conftest.py` | 共享 fixtures：db_session、client、test_user |
| `tests/test_security.py` | 安全函数单元测试 |
| `tests/test_auth.py` | 认证接口集成测试 |
| `tests/test_users.py` | 用户接口集成测试 |
| `alembic/env.py` | Alembic 异步配置 |
| `alembic/versions/001_create_users.py` | 初始迁移：users 表 |
| `deploy/prism-server.service` | systemd unit 配置 |

---

## Task 1: 项目脚手架初始化

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: 所有 `__init__.py`（见步骤）

- [ ] **Step 1: 创建目录结构**

```bash
cd /Users/anliwen/sso/prism-server
mkdir -p app/api/v1/endpoints app/core app/db app/models app/schemas app/crud app/services
mkdir -p tests alembic/versions deploy docs/superpowers/plans logs
touch app/__init__.py app/api/__init__.py app/api/v1/__init__.py
touch app/api/v1/endpoints/__init__.py app/core/__init__.py app/db/__init__.py
touch app/models/__init__.py app/schemas/__init__.py app/crud/__init__.py
touch app/services/__init__.py tests/__init__.py
```

- [ ] **Step 2: 创建 pyproject.toml**

```toml
[project]
name = "prism-server"
version = "0.1.0"
description = "Production-ready FastAPI scaffold with JWT + Redis auth"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "gunicorn>=22.0.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "aiomysql>=0.2.0",
    "alembic>=1.13.0",
    "redis[asyncio]>=5.0.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "loguru>=0.7.0",
    "email-validator>=2.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
    "aiosqlite>=0.20.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

- [ ] **Step 3: 创建 .env.example**

```ini
# 应用
APP_NAME=prism-server
APP_ENV=production
DEBUG=false

# 数据库（MySQL）
DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/prism_db

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT（生产环境请用 openssl rand -hex 32 生成）
SECRET_KEY=change-me-use-openssl-rand-hex-32
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# 日志
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
```

- [ ] **Step 4: 安装依赖**

```bash
uv venv
uv pip install -e ".[dev]"
```

预期输出：最后一行出现 `Successfully installed prism-server`

- [ ] **Step 5: 验证 Python 环境**

```bash
.venv/bin/python -c "import fastapi, sqlalchemy, redis, jose, passlib, loguru; print('OK')"
```

预期输出：`OK`

- [ ] **Step 6: 提交**

```bash
git init
git add pyproject.toml .env.example
git commit -m "chore: initialize project with uv and dependency manifest"
```

---

## Task 2: 配置与日志

**Files:**
- Create: `app/config.py`
- Create: `app/core/logging.py`

- [ ] **Step 1: 创建 app/config.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    app_name: str = "prism-server"
    app_env: str = "development"
    debug: bool = False

    database_url: str = "mysql+aiomysql://root:root@localhost:3306/prism_dev"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "dev-secret-key-change-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    log_level: str = "INFO"
    log_file: str = "logs/app.log"


settings = Settings()
```

- [ ] **Step 2: 创建 app/core/logging.py**

```python
import sys
from pathlib import Path
from loguru import logger
from app.config import settings


def setup_logging() -> None:
    logger.remove()

    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    Path(settings.log_file).parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        settings.log_file,
        level=settings.log_level,
        serialize=True,
        rotation="00:00",
        retention="30 days",
        enqueue=True,
    )
```

- [ ] **Step 3: 验证配置可以导入**

```bash
.venv/bin/python -c "from app.config import settings; print(settings.app_name)"
```

预期输出：`prism-server`

- [ ] **Step 4: 提交**

```bash
git add app/config.py app/core/logging.py
git commit -m "feat: add settings and loguru logging setup"
```

---

## Task 3: 数据库与 Redis 基础层

**Files:**
- Create: `app/db/base.py`
- Create: `app/db/redis.py`

- [ ] **Step 1: 创建 app/db/base.py**

```python
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_recycle=3600,
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 2: 创建 app/db/redis.py**

```python
from redis.asyncio import Redis
from redis.asyncio import from_url
from app.config import settings

_redis_client: Redis | None = None


async def init_redis() -> None:
    global _redis_client
    _redis_client = from_url(settings.redis_url, decode_responses=True)
    await _redis_client.ping()


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


def get_redis() -> Redis:
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis_client
```

- [ ] **Step 3: 提交**

```bash
git add app/db/
git commit -m "feat: add async SQLAlchemy engine and Redis connection pool"
```

---

## Task 4: Pydantic Schemas

**Files:**
- Create: `app/schemas/common.py`
- Create: `app/schemas/auth.py`
- Create: `app/schemas/user.py`

- [ ] **Step 1: 创建 app/schemas/common.py**

```python
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: int
    message: str
    request_id: str
```

- [ ] **Step 2: 创建 app/schemas/auth.py**

```python
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
```

- [ ] **Step 3: 创建 app/schemas/user.py**

```python
from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    username: str
    email: str
    is_active: bool
    is_superuser: bool
    created_at: datetime


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = None
```

- [ ] **Step 4: 提交**

```bash
git add app/schemas/
git commit -m "feat: add Pydantic v2 request/response schemas"
```

---

## Task 5: User ORM 模型

**Files:**
- Create: `app/models/user.py`

- [ ] **Step 1: 创建 app/models/user.py**

```python
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)
```

- [ ] **Step 2: 验证模型可导入**

```bash
.venv/bin/python -c "from app.models.user import User; print(User.__tablename__)"
```

预期输出：`users`

- [ ] **Step 3: 提交**

```bash
git add app/models/
git commit -m "feat: add User SQLAlchemy ORM model"
```

---

## Task 6: 安全核心 (TDD)

**Files:**
- Create: `app/core/security.py`
- Create: `tests/test_security.py`

- [ ] **Step 1: 写失败测试 tests/test_security.py**

```python
import pytest
from datetime import timedelta
from jose import JWTError
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)


def test_hash_and_verify_password():
    hashed = hash_password("mysecret")
    assert hashed != "mysecret"
    assert verify_password("mysecret", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_access_token():
    token = create_access_token(user_id=42)
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert "jti" in payload
    assert "exp" in payload


def test_create_and_decode_refresh_token():
    token = create_refresh_token(user_id=99)
    payload = decode_token(token)
    assert payload["sub"] == "99"
    assert payload["type"] == "refresh"


def test_decode_invalid_token_raises():
    with pytest.raises(JWTError):
        decode_token("not.a.valid.token")


def test_decode_tampered_token_raises():
    token = create_access_token(user_id=1)
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(JWTError):
        decode_token(tampered)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/pytest tests/test_security.py -v
```

预期：`ImportError` 或 `ModuleNotFoundError`（security.py 尚未创建）

- [ ] **Step 3: 实现 app/core/security.py**

```python
import uuid
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError  # noqa: F401 — re-exported for callers
from passlib.context import CryptContext
from app.config import settings

ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(subject: int, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "type": token_type,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _create_token(
        user_id,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        user_id,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/pytest tests/test_security.py -v
```

预期：5 个测试全部 PASSED

- [ ] **Step 5: 提交**

```bash
git add app/core/security.py tests/test_security.py
git commit -m "feat: add bcrypt + JWT security core with unit tests"
```

---

## Task 7: User CRUD (TDD)

**Files:**
- Create: `app/crud/user.py`
- Modify: `tests/test_security.py` → 新增 `tests/test_crud.py`

- [ ] **Step 1: 写失败测试 tests/test_crud.py**

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.base import Base
from app.models.user import User  # noqa: F401 — registers model
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/pytest tests/test_crud.py -v
```

预期：`ImportError`（crud/user.py 尚未创建）

- [ ] **Step 3: 实现 app/crud/user.py**

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.user import UserUpdate
from app.core.security import hash_password


async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
    is_superuser: bool = False,
) -> User:
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        is_superuser=is_superuser,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user(db: AsyncSession, user: User, data: UserUpdate) -> User:
    if data.email is not None:
        user.email = data.email
    if data.password is not None:
        user.hashed_password = hash_password(data.password)
    await db.commit()
    await db.refresh(user)
    return user
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/pytest tests/test_crud.py -v
```

预期：6 个测试全部 PASSED

- [ ] **Step 5: 提交**

```bash
git add app/crud/user.py tests/test_crud.py
git commit -m "feat: add User CRUD with unit tests (SQLite in-memory)"
```

---

## Task 8: 全局异常处理

**Files:**
- Create: `app/core/exceptions.py`

- [ ] **Step 1: 创建 app/core/exceptions.py**

```python
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from loguru import logger


class AppError(Exception):
    def __init__(self, status_code: int, code: int, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "request_id": _request_id(request),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": 42200,
                "message": "请求参数校验失败",
                "request_id": _request_id(request),
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content={
                "code": 50000,
                "message": "服务器内部错误",
                "request_id": _request_id(request),
            },
        )
```

- [ ] **Step 2: 提交**

```bash
git add app/core/exceptions.py
git commit -m "feat: add AppError class and global exception handlers"
```

---

## Task 9: Auth Service (TDD)

**Files:**
- Create: `app/services/auth_service.py`
- Create: `tests/test_auth_service.py`

- [ ] **Step 1: 写失败测试 tests/test_auth_service.py**

```python
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.base import Base
from app.models.user import User  # noqa: F401
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/pytest tests/test_auth_service.py -v
```

预期：`ImportError`（auth_service.py 尚未创建）

- [ ] **Step 3: 实现 app/services/auth_service.py**

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/pytest tests/test_auth_service.py -v
```

预期：9 个测试全部 PASSED

- [ ] **Step 5: 提交**

```bash
git add app/services/auth_service.py tests/test_auth_service.py
git commit -m "feat: add auth service (login/refresh/logout) with unit tests"
```

---

## Task 10: 依赖注入

**Files:**
- Create: `app/dependencies.py`

- [ ] **Step 1: 创建 app/dependencies.py**

```python
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
```

- [ ] **Step 2: 提交**

```bash
git add app/dependencies.py
git commit -m "feat: add get_db and JWT-based auth dependency injection"
```

---

## Task 11: API 端点与路由

**Files:**
- Create: `app/api/v1/endpoints/auth.py`
- Create: `app/api/v1/endpoints/users.py`
- Create: `app/api/v1/router.py`

- [ ] **Step 1: 创建 app/api/v1/endpoints/auth.py**

```python
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
```

- [ ] **Step 2: 创建 app/api/v1/endpoints/users.py**

```python
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
```

- [ ] **Step 3: 创建 app/api/v1/router.py**

```python
from fastapi import APIRouter
from app.api.v1.endpoints import auth, users

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(users.router)
```

- [ ] **Step 4: 提交**

```bash
git add app/api/
git commit -m "feat: add auth and users API endpoints"
```

---

## Task 12: 主应用组装

**Files:**
- Create: `app/main.py`

- [ ] **Step 1: 创建 app/main.py**

```python
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from app.config import settings
from app.core.logging import setup_logging
from app.core.exceptions import register_exception_handlers
from app.db.base import engine
from app.db.redis import init_redis, close_redis
from app.api.v1.router import router as api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_redis()
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

register_exception_handlers(app)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}


app.include_router(api_v1_router)
```

- [ ] **Step 2: 验证应用可启动（开发模式）**

复制 .env.example 为 .env 并填入本地配置后运行（注意：此步骤需要 MySQL 和 Redis 可连接，CI 环境可跳过）：

```bash
cp .env.example .env
# 编辑 .env 填写 DATABASE_URL / REDIS_URL / SECRET_KEY
DEBUG=true .venv/bin/uvicorn app.main:app --reload --port 8000
```

在浏览器访问 http://localhost:8000/docs 应看到 Swagger UI。

- [ ] **Step 3: 提交**

```bash
git add app/main.py
git commit -m "feat: assemble FastAPI app with lifespan, middleware, and router"
```

---

## Task 13: 集成测试基础设施

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: 创建 tests/conftest.py**

```python
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
        patch("app.db.redis._redis_client", mock_redis),
        patch("app.db.redis.get_redis", return_value=mock_redis),
        patch("app.services.auth_service.get_redis", return_value=mock_redis),  # noqa: remove if unused
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
```

- [ ] **Step 2: 提交**

```bash
git add tests/conftest.py
git commit -m "test: add integration test fixtures with SQLite + mocked Redis"
```

---

## Task 14: 认证接口集成测试

**Files:**
- Create: `tests/test_auth.py`

- [ ] **Step 1: 写测试 tests/test_auth.py**

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_health(client):
    ac, _ = client
    resp = await ac.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_login_success(client, test_user):
    ac, _ = client
    resp = await ac.post("/api/v1/auth/login", json={"username": "testuser", "password": "secret123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(client, test_user):
    ac, _ = client
    resp = await ac.post("/api/v1/auth/login", json={"username": "testuser", "password": "wrong"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == 40101
    assert "request_id" in body


async def test_login_nonexistent_user(client):
    ac, _ = client
    resp = await ac.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
    assert resp.status_code == 401


async def test_refresh_success(client, test_user):
    ac, _ = client
    login_resp = await ac.post("/api/v1/auth/login", json={"username": "testuser", "password": "secret123"})
    refresh_tok = login_resp.json()["refresh_token"]
    resp = await ac.post("/api/v1/auth/refresh", json={"refresh_token": refresh_tok})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_refresh_with_access_token_fails(client, test_user):
    ac, _ = client
    login_resp = await ac.post("/api/v1/auth/login", json={"username": "testuser", "password": "secret123"})
    access_tok = login_resp.json()["access_token"]
    resp = await ac.post("/api/v1/auth/refresh", json={"refresh_token": access_tok})
    assert resp.status_code == 401


async def test_refresh_blacklisted_token(client, test_user):
    ac, mock_redis = client
    login_resp = await ac.post("/api/v1/auth/login", json={"username": "testuser", "password": "secret123"})
    refresh_tok = login_resp.json()["refresh_token"]
    mock_redis.exists.return_value = 1
    resp = await ac.post("/api/v1/auth/refresh", json={"refresh_token": refresh_tok})
    assert resp.status_code == 401
    assert resp.json()["code"] == 40103


async def test_logout_success(client, test_user):
    ac, mock_redis = client
    login_resp = await ac.post("/api/v1/auth/login", json={"username": "testuser", "password": "secret123"})
    access_tok = login_resp.json()["access_token"]
    resp = await ac.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {access_tok}"})
    assert resp.status_code == 200
    mock_redis.setex.assert_called_once()
    call_key = mock_redis.setex.call_args[0][0]
    assert call_key.startswith("blacklist:")


async def test_blacklisted_token_cannot_access(client, test_user):
    ac, mock_redis = client
    login_resp = await ac.post("/api/v1/auth/login", json={"username": "testuser", "password": "secret123"})
    access_tok = login_resp.json()["access_token"]
    await ac.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {access_tok}"})
    mock_redis.exists.return_value = 1
    resp = await ac.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access_tok}"})
    assert resp.status_code == 401
    assert resp.json()["code"] == 40103


async def test_login_invalid_body(client):
    ac, _ = client
    resp = await ac.post("/api/v1/auth/login", json={"username": "only"})
    assert resp.status_code == 422
    assert resp.json()["code"] == 42200
```

- [ ] **Step 2: 运行测试**

```bash
.venv/bin/pytest tests/test_auth.py -v
```

预期：9 个测试全部 PASSED

- [ ] **Step 3: 提交**

```bash
git add tests/test_auth.py
git commit -m "test: add auth endpoint integration tests"
```

---

## Task 15: 用户接口集成测试

**Files:**
- Create: `tests/test_users.py`

- [ ] **Step 1: 写测试 tests/test_users.py**

```python
import pytest

pytestmark = pytest.mark.asyncio


async def _login(ac, username="testuser", password="secret123") -> str:
    resp = await ac.post("/api/v1/auth/login", json={"username": username, "password": password})
    return resp.json()["access_token"]


async def test_get_me_success(client, test_user):
    ac, _ = client
    token = await _login(ac)
    resp = await ac.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert "hashed_password" not in data


async def test_get_me_no_token(client):
    ac, _ = client
    resp = await ac.get("/api/v1/users/me")
    assert resp.status_code == 403


async def test_get_me_invalid_token(client, test_user):
    ac, _ = client
    resp = await ac.get("/api/v1/users/me", headers={"Authorization": "Bearer not.a.valid.token"})
    assert resp.status_code == 401
    assert resp.json()["code"] == 40102


async def test_update_me_email(client, test_user):
    ac, _ = client
    token = await _login(ac)
    resp = await ac.patch(
        "/api/v1/users/me",
        json={"email": "updated@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "updated@example.com"


async def test_update_me_password(client, test_user):
    ac, _ = client
    token = await _login(ac)
    resp = await ac.patch(
        "/api/v1/users/me",
        json={"password": "newpassword456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    new_token = await _login(ac, password="newpassword456")
    assert new_token


async def test_update_me_invalid_email(client, test_user):
    ac, _ = client
    token = await _login(ac)
    resp = await ac.patch(
        "/api/v1/users/me",
        json={"email": "not-an-email"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 42200
```

- [ ] **Step 2: 运行所有测试**

```bash
.venv/bin/pytest tests/ -v --ignore=tests/test_security.py --ignore=tests/test_crud.py --ignore=tests/test_auth_service.py
```

预期：test_auth.py + test_users.py 共 15 个测试全部 PASSED

- [ ] **Step 3: 运行全部测试套件**

```bash
.venv/bin/pytest tests/ -v
```

预期：全部测试通过

- [ ] **Step 4: 提交**

```bash
git add tests/test_users.py
git commit -m "test: add users endpoint integration tests"
```

---

## Task 16: Alembic 数据库迁移

**Files:**
- Create: `alembic.ini`（由 alembic init 生成）
- Modify: `alembic/env.py`
- Create: `alembic/versions/001_create_users_table.py`

- [ ] **Step 1: 初始化 Alembic**

```bash
.venv/bin/alembic init alembic
```

- [ ] **Step 2: 替换 alembic/env.py**

```python
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from app.config import settings
from app.db.base import Base
from app.models import user  # noqa: F401 — registers model

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = settings.database_url
    engine = async_engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: 创建初始迁移 alembic/versions/001_create_users_table.py**

```python
"""create users table

Revision ID: 001
Revises:
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE users (
            id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(64) NOT NULL,
            email VARCHAR(128) NOT NULL,
            hashed_password VARCHAR(128) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_users_username (username),
            UNIQUE KEY uq_users_email (email),
            INDEX ix_users_username (username)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)


def downgrade() -> None:
    op.drop_table("users")
```

- [ ] **Step 4: 在 .env 配置好 MySQL 后执行迁移（需要真实 MySQL 连接）**

```bash
.venv/bin/alembic upgrade head
```

预期输出：`Running upgrade  -> 001, create users table`

- [ ] **Step 5: 提交**

```bash
git add alembic/ alembic.ini
git commit -m "feat: add Alembic async config and initial users table migration"
```

---

## Task 17: 部署配置与 README

**Files:**
- Create: `deploy/prism-server.service`
- Create: `README.md`

- [ ] **Step 1: 创建 deploy/prism-server.service**

```ini
[Unit]
Description=prism-server FastAPI application
After=network.target mysql.service redis.service
Wants=mysql.service redis.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/prism-server
EnvironmentFile=/opt/prism-server/.env
ExecStart=/opt/prism-server/.venv/bin/gunicorn app.main:app \
    -k uvicorn.workers.UvicornWorker \
    -w 4 \
    --bind 127.0.0.1:8000 \
    --access-logfile - \
    --error-logfile - \
    --timeout 30
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: 创建 README.md**

```markdown
# prism-server

生产级 FastAPI 脚手架，内置 JWT + Redis 认证。

## 技术栈

FastAPI · SQLAlchemy 2 (async) · MySQL · Redis · python-jose · loguru · uv

## 快速开始

```bash
# 1. 安装依赖
uv venv && uv pip install -e ".[dev]"

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填写 DATABASE_URL / REDIS_URL / SECRET_KEY

# 3. 执行数据库迁移
.venv/bin/alembic upgrade head

# 4. 启动开发服务器
DEBUG=true .venv/bin/uvicorn app.main:app --reload
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/auth/login | 用户登录，返回 Access + Refresh Token |
| POST | /api/v1/auth/refresh | 刷新 Access Token |
| POST | /api/v1/auth/logout | 登出（Token 加入 Redis 黑名单） |
| GET | /api/v1/users/me | 获取当前用户信息 |
| PATCH | /api/v1/users/me | 修改当前用户 email / 密码 |
| GET | /health | 健康检查 |

## 运行测试

```bash
.venv/bin/pytest tests/ -v
```

## 生产部署（systemd）

```bash
# 部署到 /opt/prism-server
sudo cp deploy/prism-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now prism-server
```

Worker 数量建议：`2 × CPU核心数 + 1`，在 .service 文件中修改 `-w` 参数。

## 错误响应格式

```json
{ "code": 40101, "message": "用户名或密码错误", "request_id": "uuid" }
```

| code | 含义 |
|------|------|
| 40100 | 未提供 Token |
| 40101 | 用户名或密码错误 |
| 40102 | Token 无效或已过期 |
| 40103 | Token 已被吊销 |
| 40300 | 账号已禁用 |
| 42200 | 请求参数校验失败 |
| 50000 | 服务器内部错误 |
```

- [ ] **Step 3: 提交**

```bash
git add deploy/ README.md
git commit -m "docs: add systemd service config and README"
```

---

## 最终验证

- [ ] 运行全部测试，确认全部通过：

```bash
.venv/bin/pytest tests/ -v
```

预期：所有测试 PASSED，无 WARNING

- [ ] 检查项目结构完整性：

```bash
find . -name "*.py" | grep -v __pycache__ | grep -v .venv | sort
```

预期：列出 app/ 和 tests/ 下所有 Python 文件，无缺失
