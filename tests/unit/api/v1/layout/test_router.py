"""Tests for layout API router."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.layout.router import router


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI application."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check(self, client: TestClient) -> None:
        """Test health check returns healthy status."""
        response = client.get("/api/v1/layout/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "layout"


class TestGenerateLayoutStream:
    """Tests for the SSE streaming endpoint /layout/generate/stream."""

    def test_stream_endpoint_returns_streaming_response(self, client: TestClient) -> None:
        """Verify the endpoint returns an SSE stream (not a JSON body)."""
        with client.stream(
            "POST",
            "/api/v1/layout/generate/stream",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "budget_level": "medium",
            },
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

    def test_stream_endpoint_with_mode_param(self, client: TestClient) -> None:
        """Verify the mode query param is accepted without error."""
        with client.stream(
            "POST",
            "/api/v1/layout/generate/stream?mode=mentor",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "budget_level": "medium",
            },
        ) as response:
            assert response.status_code == 200

    def test_stream_endpoint_invalid_room_type(self, client: TestClient) -> None:
        """Verify validation error on invalid room_type."""
        response = client.post(
            "/api/v1/layout/generate/stream",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "invalid_room",
                "budget_level": "medium",
            },
        )
        assert response.status_code == 422

    def test_stream_endpoint_invalid_budget(self, client: TestClient) -> None:
        """Verify validation error on invalid budget_level."""
        response = client.post(
            "/api/v1/layout/generate/stream",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "budget_level": "super_high",
            },
        )
        assert response.status_code == 422

    def test_removed_generate_endpoint_is_gone(self, client: TestClient) -> None:
        """Confirm /layout/generate (the old mock) no longer exists."""
        response = client.post(
            "/api/v1/layout/generate",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "style": "modern",
                "requirements": "test",
            },
        )
        assert response.status_code == 404 or response.status_code == 405

    def test_removed_feng_shui_endpoint_is_gone(self, client: TestClient) -> None:
        """Confirm /layout/feng-shui no longer exists."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "budget_level": "medium",
            },
        )
        assert response.status_code == 404 or response.status_code == 405
