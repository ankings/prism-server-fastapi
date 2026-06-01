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
