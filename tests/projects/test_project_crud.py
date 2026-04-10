"""Tests for project CRUD endpoints."""

import pytest
from httpx import AsyncClient

ROOM_SPEC = {"width": 4.0, "depth": 5.0, "height": 2.8, "doors": [], "windows": []}


async def _auth_headers(client: AsyncClient, email: str = "proj@example.com") -> dict[str, str]:
    """Register user and return cookie dict."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": "Proj User"},
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return {"access_token": token}


async def _create_project(
    client: AsyncClient, cookies: dict[str, str], name: str = "My Room"
) -> dict:  # type: ignore[type-arg]
    resp = await client.post(
        "/api/v1/projects",
        json={"name": name, "room_spec": ROOM_SPEC},
        cookies=cookies,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient) -> None:
    cookies = await _auth_headers(client)
    data = await _create_project(client, cookies)
    assert data["name"] == "My Room"
    assert data["room_spec"] == ROOM_SPEC
    assert data["latest_layout"] is None


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient) -> None:
    cookies = await _auth_headers(client, "list@example.com")
    await _create_project(client, cookies, "Room A")
    await _create_project(client, cookies, "Room B")

    resp = await client.get("/api/v1/projects", cookies=cookies)
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert "Room A" in names
    assert "Room B" in names


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient) -> None:
    cookies = await _auth_headers(client, "get@example.com")
    created = await _create_project(client, cookies)
    project_id = created["id"]

    resp = await client.get(f"/api/v1/projects/{project_id}", cookies=cookies)
    assert resp.status_code == 200
    assert resp.json()["id"] == project_id


@pytest.mark.asyncio
async def test_update_project_name_and_layout(client: AsyncClient) -> None:
    cookies = await _auth_headers(client, "upd@example.com")
    created = await _create_project(client, cookies)
    project_id = created["id"]

    layout = [{"id": "bed-1", "pos_x": 0.5, "pos_z": 0.5}]
    resp = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Renamed Room", "latest_layout": layout},
        cookies=cookies,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Renamed Room"
    assert data["latest_layout"] == layout


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient) -> None:
    cookies = await _auth_headers(client, "del@example.com")
    created = await _create_project(client, cookies)
    project_id = created["id"]

    resp = await client.delete(f"/api/v1/projects/{project_id}", cookies=cookies)
    assert resp.status_code == 204

    # Should be gone
    resp = await client.get(f"/api/v1/projects/{project_id}", cookies=cookies)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_project_isolation(client: AsyncClient) -> None:
    """User A cannot see User B's projects."""
    cookies_a = await _auth_headers(client, "usera@example.com")
    cookies_b = await _auth_headers(client, "userb@example.com")

    created = await _create_project(client, cookies_a)
    project_id = created["id"]

    resp = await client.get(f"/api/v1/projects/{project_id}", cookies=cookies_b)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_projects_require_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 401
