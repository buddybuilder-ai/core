"""Tests for GET /api/v1/auth/me and POST /api/v1/auth/logout."""

import pytest
from httpx import AsyncClient


async def _register_and_get_token(client: AsyncClient, email: str = "me@example.com") -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": "Me User"},
    )
    assert resp.status_code == 201
    return str(resp.json()["access_token"])


@pytest.mark.asyncio
async def test_me_with_valid_cookie(client: AsyncClient) -> None:
    token = await _register_and_get_token(client)
    resp = await client.get("/api/v1/auth/me", cookies={"access_token": token})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_me_without_cookie(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_invalid_token(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me", cookies={"access_token": "bad.token.here"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout(client: AsyncClient) -> None:
    token = await _register_and_get_token(client, email="logout@example.com")
    resp = await client.post("/api/v1/auth/logout", cookies={"access_token": token})
    assert resp.status_code == 204
