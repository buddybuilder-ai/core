"""Tests for layout API router."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.layout.router import router
from src.schemas.layout import RoomType, WallSide


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


class TestGenerateLayout:
    """Tests for original generate endpoint."""

    def test_generate_layout_mock(self, client: TestClient) -> None:
        """Test mock layout generation."""
        response = client.post(
            "/api/v1/layout/generate",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "style": "modern",
                "requirements": "comfortable seating",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert "modern" in data["reasoning"]

    def test_generate_layout_validation_error(self, client: TestClient) -> None:
        """Test generate endpoint with invalid data."""
        response = client.post(
            "/api/v1/layout/generate",
            json={
                "dimensions": {"width": -1.0, "depth": 4.0},  # Invalid negative width
                "style": "modern",
                "requirements": "test",
            },
        )

        assert response.status_code == 422  # Validation error


class TestFengShuiLayout:
    """Tests for feng shui layout endpoint."""

    def test_feng_shui_layout_bedroom(self, client: TestClient) -> None:
        """Test feng shui layout for bedroom."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "budget_level": "medium",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "feng_shui_score" in data
        assert "reasoning" in data
        assert "metadata" in data

        # Check score breakdown
        score = data["feng_shui_score"]
        assert "command_position" in score
        assert "five_elements_balance" in score
        assert "chi_flow" in score
        assert "sha_chi_avoidance" in score

    def test_feng_shui_layout_office(self, client: TestClient) -> None:
        """Test feng shui layout for office."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 4.0, "depth": 3.0, "height": 2.8},
                "room_type": "office",
                "budget_level": "high",
                "style": "minimalist",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "office" in data["reasoning"].lower()

    def test_feng_shui_layout_with_doors_and_windows(
        self,
        client: TestClient,
    ) -> None:
        """Test feng shui layout with doors and windows."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "doors": [
                    {"wall": "south", "offset": 2.0, "width": 0.9},
                ],
                "windows": [
                    {"wall": "east", "offset": 1.5, "width": 1.5, "height": 1.2},
                ],
                "budget_level": "medium",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) > 0

    def test_feng_shui_layout_living_room(self, client: TestClient) -> None:
        """Test feng shui layout for living room."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 6.0, "depth": 5.0, "height": 2.8},
                "room_type": "living_room",
                "budget_level": "low",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "living_room" in data["reasoning"].lower()

    def test_feng_shui_layout_has_furniture_items(self, client: TestClient) -> None:
        """Test that feng shui layout includes furniture items."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "budget_level": "medium",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Should have at least one furniture item
        assert len(data["items"]) > 0

        # Check furniture item structure
        item = data["items"][0]
        assert "id" in item
        assert "name" in item
        assert "category" in item
        assert "pos_x" in item
        assert "pos_z" in item
        assert "dimensions" in item
        assert "is_essential" in item

    def test_feng_shui_layout_metadata(self, client: TestClient) -> None:
        """Test feng shui layout metadata."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "budget_level": "medium",
            },
        )

        assert response.status_code == 200
        data = response.json()

        metadata = data["metadata"]
        assert "layout_id" in metadata
        assert "generated_at" in metadata
        assert "generation_time_ms" in metadata

    def test_feng_shui_layout_invalid_room_type(self, client: TestClient) -> None:
        """Test feng shui layout with invalid room type."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "invalid_room",  # Invalid room type
                "budget_level": "medium",
            },
        )

        assert response.status_code == 422  # Validation error

    def test_feng_shui_layout_invalid_budget(self, client: TestClient) -> None:
        """Test feng shui layout with invalid budget level."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "budget_level": "super_high",  # Invalid budget
            },
        )

        assert response.status_code == 422  # Validation error

    def test_feng_shui_layout_small_room(self, client: TestClient) -> None:
        """Test feng shui layout for small room."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 2.5, "depth": 2.5, "height": 2.4},
                "room_type": "bedroom",
                "budget_level": "low",
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Should still succeed but may have fewer items
        assert "items" in data


class TestFengShuiLayoutScoring:
    """Tests for feng shui scoring in layout response."""

    def test_score_breakdown_values(self, client: TestClient) -> None:
        """Test score breakdown has valid values."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "budget_level": "medium",
            },
        )

        assert response.status_code == 200
        score = response.json()["feng_shui_score"]

        # Check individual scores are within valid ranges
        assert 0 <= score["command_position"] <= 30
        assert 0 <= score["five_elements_balance"] <= 20
        assert 0 <= score["chi_flow"] <= 25
        assert 0 <= score["sha_chi_avoidance"] <= 25

    def test_reasoning_includes_score(self, client: TestClient) -> None:
        """Test reasoning mentions feng shui score."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "budget_level": "medium",
            },
        )

        assert response.status_code == 200
        reasoning = response.json()["reasoning"]

        assert "feng shui" in reasoning.lower()
        assert "/100" in reasoning  # Score format


class TestFengShuiLayoutUserPreferences:
    """Tests for user preferences in feng shui layout."""

    def test_layout_with_user_preferences(self, client: TestClient) -> None:
        """Test feng shui layout with custom preferences."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "budget_level": "high",
                "style": "zen",
                "user_preferences": {
                    "prefer_natural_materials": True,
                    "maximize_open_space": True,
                },
            },
        )

        assert response.status_code == 200

    def test_layout_with_direction(self, client: TestClient) -> None:
        """Test feng shui layout with facing direction."""
        response = client.post(
            "/api/v1/layout/feng-shui",
            json={
                "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
                "room_type": "bedroom",
                "budget_level": "medium",
                "direction": "south",
            },
        )

        assert response.status_code == 200
