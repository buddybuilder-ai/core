"""Tests for chat message endpoints."""

import pytest
from httpx import AsyncClient

ROOM_SPEC = {"width": 4.0, "depth": 5.0, "height": 2.8, "doors": [], "windows": []}


async def _setup(
    client: AsyncClient, email: str = "chat@example.com"
) -> tuple[dict[str, str], str]:
    """Register user and create a project. Returns (cookies, project_id)."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": "Chat User"},
    )
    cookies = {"access_token": resp.json()["access_token"]}
    proj = await client.post(
        "/api/v1/projects",
        json={"name": "Chat Room", "room_spec": ROOM_SPEC},
        cookies=cookies,
    )
    return cookies, proj.json()["id"]


@pytest.mark.asyncio
async def test_save_and_retrieve_messages(client: AsyncClient) -> None:
    cookies, pid = await _setup(client)

    await client.post(
        f"/api/v1/projects/{pid}/messages",
        json={"role": "user", "content": "Hello", "intent": "question"},
        cookies=cookies,
    )
    await client.post(
        f"/api/v1/projects/{pid}/messages",
        json={"role": "assistant", "content": "Hi there!", "intent": None},
        cookies=cookies,
    )

    resp = await client.get(f"/api/v1/projects/{pid}/messages", cookies=cookies)
    assert resp.status_code == 200
    msgs = resp.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[0]["intent"] == "question"


@pytest.mark.asyncio
async def test_messages_require_auth(client: AsyncClient) -> None:
    cookies, pid = await _setup(client, "chatauth@example.com")
    resp = await client.get(f"/api/v1/projects/{pid}/messages")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_messages_wrong_project(client: AsyncClient) -> None:
    """Cannot post to another user's project."""
    cookies_a, pid = await _setup(client, "chatA@example.com")
    resp_b = await client.post(
        "/api/v1/auth/register",
        json={"email": "chatB@example.com", "password": "password123", "display_name": "B"},
    )
    cookies_b = {"access_token": resp_b.json()["access_token"]}

    resp = await client.post(
        f"/api/v1/projects/{pid}/messages",
        json={"role": "user", "content": "Hack!"},
        cookies=cookies_b,
    )
    assert resp.status_code == 404
