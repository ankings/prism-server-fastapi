# prism-server-fastapi

生产级 FastAPI API 脚手架，内置 JWT + Redis 认证，MySQL 数据库，systemd 部署。

## 技术栈

| 层级 | 选型 |
|------|------|
| Web 框架 | FastAPI |
| 数据验证 | Pydantic v2 |
| ORM | SQLAlchemy 2.x (async) |
| 数据库 | MySQL (aiomysql) |
| 缓存/黑名单 | Redis |
| 认证 | JWT (python-jose) + Redis 黑名单 |
| 日志 | loguru |
| 包管理 | uv |

## 快速开始

### 1. 安装依赖

```bash
uv venv
uv pip install -e ".[dev]"
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写以下关键配置：
# DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/prism_db
# REDIS_URL=redis://localhost:6379/0
# SECRET_KEY=$(openssl rand -hex 32)
```

### 3. 执行数据库迁移

```bash
.venv/bin/alembic upgrade head
```

### 4. 启动开发服务器

```bash
APP_ENV=development DEBUG=true .venv/bin/uvicorn app.main:app --reload
```

Swagger UI 访问：http://localhost:8000/docs

## API 接口

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | /api/v1/auth/login | 用户登录，返回 Access + Refresh Token | 否 |
| POST | /api/v1/auth/refresh | 刷新 Access Token | 否 |
| POST | /api/v1/auth/logout | 登出（Token 加入 Redis 黑名单） | 是 |
| GET | /api/v1/users/me | 获取当前用户信息 | 是 |
| PATCH | /api/v1/users/me | 修改当前用户 email / 密码 | 是 |
| GET | /health | 健康检查 | 否 |

## 运行测试

```bash
.venv/bin/pytest tests/ -v
```

## 生产部署（systemd）

```bash
# 1. 将项目部署到 /opt/prism-server-fastapi
sudo cp -r . /opt/prism-server-fastapi
cd /opt/prism-server-fastapi
uv venv && uv pip install -e .

# 2. 配置环境变量
sudo cp .env.example .env
sudo nano /opt/prism-server-fastapi/.env  # 填写生产配置

# 3. 执行数据库迁移
.venv/bin/alembic upgrade head

# 4. 安装并启动 systemd 服务
sudo cp deploy/prism-server-fastapi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now prism-server-fastapi
sudo systemctl status prism-server-fastapi
```

Worker 数量建议：`2 × CPU核心数 + 1`，修改 `.service` 文件中 `-w` 参数。

## Nginx 反向代理示例

```nginx
server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 错误响应格式

所有 API 错误统一格式：

```json
{
  "code": 40101,
  "message": "用户名或密码错误",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| HTTP 状态码 | code | 含义 |
|------------|------|------|
| 401 | 40100 | 未提供 Token |
| 401 | 40101 | 用户名或密码错误 |
| 401 | 40102 | Token 无效或已过期 |
| 401 | 40103 | Token 已被吊销 |
| 403 | 40300 | 账号已禁用 |
| 422 | 42200 | 请求参数校验失败 |
| 500 | 50000 | 服务器内部错误 |

## 添加初始管理员用户

通过 Alembic 数据迁移或直接 SQL 插入（密码需先用 bcrypt 哈希）：

```python
# 在 Python shell 中运行
from app.core.security import hash_password
print(hash_password("your_admin_password"))
```

```sql
INSERT INTO users (username, email, hashed_password, is_superuser)
VALUES ('admin', 'admin@example.com', '<bcrypt_hash>', TRUE);
```
