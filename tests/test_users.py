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
    # FastAPI >= 0.136 HTTPBearer raises 401 (older versions raised 403)
    assert resp.status_code in (401, 403)


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
