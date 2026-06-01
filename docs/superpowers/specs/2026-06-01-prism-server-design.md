# prism-server 脚手架设计规格

**日期：** 2026-06-01  
**状态：** 待用户确认  

---

## 1. 项目定位

面向生产环境的 FastAPI 通用 API 后端脚手架，内置完整的用户认证功能（JWT + Redis 黑名单），作为新项目的起点，可直接在裸金属/VM 上部署。

---

## 2. 技术栈

| 层级 | 选型 | 版本要求 |
|------|------|---------|
| Web 框架 | FastAPI | >=0.111 |
| 数据验证 | Pydantic v2 | >=2.7 |
| 配置管理 | pydantic-settings | >=2.3 |
| ORM | SQLAlchemy (async) | >=2.0 |
| MySQL 驱动 | aiomysql | >=0.2 |
| 数据库迁移 | Alembic | >=1.13 |
| 缓存/黑名单 | Redis (aioredis via redis-py) | >=5.0 |
| 认证 | python-jose[cryptography] | >=3.3 |
| 密码哈希 | passlib[bcrypt] | >=1.7 |
| 日志 | loguru | >=0.7 |
| ASGI 服务器 | uvicorn + gunicorn | uvicorn>=0.29, gunicorn>=22 |
| 包管理 | uv | >=0.4 |
| 测试 | pytest + pytest-asyncio + httpx | latest |

---

## 3. 目录结构

```
prism-server/
├── app/
│   ├── main.py                  # FastAPI 实例、lifespan、路由挂载、全局中间件
│   ├── config.py                # pydantic-settings 配置类，读取 .env
│   ├── dependencies.py          # 公共依赖：get_db、get_current_user、get_current_active_user
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── router.py        # 聚合所有 v1 Router
│   │       └── endpoints/
│   │           ├── auth.py      # /login /refresh /logout
│   │           └── users.py     # /users/me (GET, PATCH)
│   │
│   ├── core/
│   │   ├── security.py          # JWT 签发/校验、bcrypt 密码哈希、Redis 黑名单操作
│   │   ├── exceptions.py        # 全局异常处理器、统一错误响应格式
│   │   └── logging.py           # loguru 初始化配置（JSON 格式输出到文件 + stderr）
│   │
│   ├── db/
│   │   ├── base.py              # async engine、async_session_factory、DeclarativeBase
│   │   └── redis.py             # Redis 连接池初始化与关闭
│   │
│   ├── models/
│   │   └── user.py              # User SQLAlchemy ORM 模型
│   │
│   ├── schemas/
│   │   ├── auth.py              # LoginRequest、TokenResponse、RefreshRequest
│   │   ├── user.py              # UserCreate、UserOut、UserUpdate
│   │   └── common.py            # ErrorResponse（统一错误体）
│   │
│   ├── crud/
│   │   └── user.py              # get_by_id、get_by_username、get_by_email、create、update
│   │
│   └── services/
│       └── auth_service.py      # login、refresh_token、logout 业务逻辑
│
├── alembic/
│   ├── env.py
│   └── versions/
├── alembic.ini
│
├── tests/
│   ├── conftest.py              # AsyncClient fixture、测试数据库 session
│   ├── test_auth.py             # 登录/刷新/登出集成测试
│   └── test_users.py            # /users/me 集成测试
│
├── deploy/
│   └── prism-server.service     # systemd unit 配置
│
├── .env.example                 # 环境变量模板
├── pyproject.toml               # uv 依赖管理
└── README.md
```

---

## 4. 数据模型

### users 表

```sql
CREATE TABLE users (
    id               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username         VARCHAR(64)  NOT NULL UNIQUE,
    email            VARCHAR(128) NOT NULL UNIQUE,
    hashed_password  VARCHAR(128) NOT NULL,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    is_superuser     BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

---

## 5. API 接口设计

### 5.1 认证接口

#### POST /api/v1/auth/login
- **请求体：** `{ "username": str, "password": str }`
- **响应：** `{ "access_token": str, "refresh_token": str, "token_type": "bearer" }`
- **错误：** 401 用户名或密码错误；403 账号已禁用

#### POST /api/v1/auth/refresh
- **请求体：** `{ "refresh_token": str }`
- **响应：** `{ "access_token": str, "token_type": "bearer" }`
- **错误：** 401 Token 无效或已过期或已在黑名单

#### POST /api/v1/auth/logout
- **Header：** `Authorization: Bearer <access_token>`
- **响应：** `{ "message": "登出成功" }`
- **行为：** 将当前 access_token 的 `jti` 写入 Redis，TTL = Token 剩余有效期

### 5.2 用户接口（需鉴权）

#### GET /api/v1/users/me
- **响应：** `UserOut`（id, username, email, is_active, created_at）

#### PATCH /api/v1/users/me
- **请求体：** `UserUpdate`（email 可选，password 可选）
- **响应：** 更新后的 `UserOut`

### 5.3 健康检查

#### GET /health
- **无鉴权**
- **响应：** `{ "status": "ok" }`

---

## 6. 认证流程

### Token 策略

| | Access Token | Refresh Token |
|-|---|---|
| 有效期 | 30 分钟（可配置） | 7 天（可配置） |
| 算法 | HS256 | HS256 |
| Payload | sub(user_id)、jti(uuid)、exp、type | sub(user_id)、jti(uuid)、exp、type |
| 吊销 | Redis 黑名单（jti） | Redis 黑名单（jti） |

### 登录流程
1. 按 username 查询用户，未找到则 401
2. bcrypt 校验密码，不匹配则 401（响应时间恒定，防时序攻击）
3. 校验 is_active，禁用则 403
4. 签发 access_token + refresh_token，各含唯一 jti
5. 返回两个 Token

### 每次请求鉴权（依赖注入）
1. 从 `Authorization: Bearer <token>` 提取 Token
2. 校验 JWT 签名与过期时间
3. 校验 type 字段（access）
4. 查 Redis 黑名单（key: `blacklist:{jti}`），命中则 401
5. 按 sub 查询 User，注入依赖

### 刷新 Token
1. 校验 refresh_token 签名、过期、type 字段
2. 查 Redis 黑名单
3. 签发新 access_token（新 jti，新过期时间）
4. 旧 refresh_token 继续有效直至过期

### 登出
1. 解析 access_token，提取 jti 和剩余 TTL
2. `SET blacklist:{jti} 1 EX {剩余秒数}` 写入 Redis
3. 如客户端同时传入 refresh_token，同样加入黑名单

---

## 7. 错误响应格式

所有错误统一返回：

```json
{
  "code": 40101,
  "message": "用户名或密码错误",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**业务错误码规范（示例）：**

| HTTP 状态码 | code | 含义 |
|------------|------|------|
| 401 | 40100 | 未提供 Token |
| 401 | 40101 | 用户名或密码错误 |
| 401 | 40102 | Token 无效或已过期 |
| 401 | 40103 | Token 已被吊销 |
| 403 | 40300 | 账号已禁用 |
| 422 | 42200 | 请求参数校验失败 |
| 500 | 50000 | 服务器内部错误 |

---

## 8. 配置管理

`.env.example`：

```ini
# 应用
APP_NAME=prism-server
APP_ENV=production          # development | production
DEBUG=false

# 数据库
DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/prism_db

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
SECRET_KEY=your-256-bit-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# 日志
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
```

---

## 9. 日志设计

使用 **loguru**，生产环境双输出：

- **stderr：** 纯文本，供 systemd journald 收集
- **文件：** JSON 格式，便于 ELK / Loki 采集，按天轮转，保留 30 天

每条请求日志包含：`request_id`、`method`、`path`、`status_code`、`duration_ms`、`client_ip`

---

## 10. 部署设计

### gunicorn + uvicorn 启动命令

```bash
gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w 4 \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

Worker 数量建议：`2 × CPU核心数 + 1`

### systemd 配置（`deploy/prism-server.service`）

```ini
[Unit]
Description=prism-server FastAPI application
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/prism-server
EnvironmentFile=/opt/prism-server/.env
ExecStart=/opt/prism-server/.venv/bin/gunicorn app.main:app \
    -k uvicorn.workers.UvicornWorker \
    -w 4 \
    --bind 0.0.0.0:8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 11. 测试策略

- **集成测试为主：** 通过 `httpx.AsyncClient` 直接调用 HTTP 接口
- **测试数据库：** 使用独立测试库，每次测试前通过 Alembic 建表，测试后回滚
- **测试覆盖场景：**
  - 登录成功 / 密码错误 / 用户不存在 / 账号禁用
  - 刷新 Token 成功 / Token 已过期 / Token 已吊销
  - 登出成功 / 登出后 Token 不可再用
  - 获取当前用户信息（鉴权通过 / 未携带 Token / Token 无效）

---

## 12. 不包含的内容（刻意排除）

以下内容超出脚手架范围，由使用者按需添加：

- 注册接口（脚手架通过 Alembic 直接插入初始超管账号）
- 第三方登录（OAuth2、SSO）
- 权限系统（RBAC）
- Docker / docker-compose
- 邮件发送、短信验证码
- 文件上传
