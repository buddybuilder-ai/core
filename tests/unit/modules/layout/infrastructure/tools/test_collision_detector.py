"""Tests for collision detector tool."""

import pytest

from src.modules.layout.domain.value_objects import BoundingBox
from src.modules.layout.infrastructure.tools.collision_detector_tool import (
    Collision,
    CollisionDetectorInput,
    CollisionDetectorTool,
    CollisionType,
    PlacedItem,
)


class TestPlacedItem:
    """Tests for PlacedItem dataclass."""

    def test_placed_item_creation(self) -> None:
        """Test creating a placed item."""
        item = PlacedItem(
            id="bed_001",
            name="Queen Bed",
            bounding_box=BoundingBox(
                min_x=1.0,
                min_y=0.0,
                min_z=2.0,
                max_x=2.6,
                max_y=0.5,
                max_z=4.0,
            ),
        )
        assert item.id == "bed_001"
        assert item.name == "Queen Bed"
        assert item.clearance_required == 0.6  # default

    def test_placed_item_dimensions(self) -> None:
        """Test item dimension calculations."""
        item = PlacedItem(
            id="test",
            name="Test",
            bounding_box=BoundingBox(
                min_x=0.0,
                min_y=0.0,
                min_z=0.0,
                max_x=2.0,
                max_y=1.0,
                max_z=3.0,
            ),
        )
        assert item.width == 2.0
        assert item.depth == 3.0
        assert item.height == 1.0

    def test_placed_item_center(self) -> None:
        """Test item center calculation."""
        item = PlacedItem(
            id="test",
            name="Test",
            bounding_box=BoundingBox(
                min_x=0.0,
                min_y=0.0,
                min_z=0.0,
                max_x=4.0,
                max_y=2.0,
                max_z=6.0,
            ),
        )
        center = item.center
        assert center.x == 2.0
        assert center.y == 1.0
        assert center.z == 3.0

    def test_placed_item_clearance_box(self) -> None:
        """Test clearance box calculation."""
        item = PlacedItem(
            id="test",
            name="Test",
            bounding_box=BoundingBox(
                min_x=1.0,
                min_y=0.0,
                min_z=1.0,
                max_x=3.0,
                max_y=1.0,
                max_z=3.0,
            ),
            clearance_required=0.5,
        )
        clearance_box = item.get_clearance_box()
        assert clearance_box.min_x == 0.5
        assert clearance_box.max_x == 3.5
        assert clearance_box.min_z == 0.5
        assert clearance_box.max_z == 3.5


class TestCollision:
    """Tests for Collision dataclass."""

    def test_collision_creation(self) -> None:
        """Test creating a collision."""
        collision = Collision(
            collision_type=CollisionType.FURNITURE_OVERLAP,
            item1_id="bed_001",
            item2_id="desk_001",
            description="Bed overlaps with desk by 0.3m",
            severity="error",
            overlap_amount=0.3,
        )
        assert collision.collision_type == CollisionType.FURNITURE_OVERLAP
        assert collision.item1_id == "bed_001"
        assert collision.severity == "error"

    def test_collision_to_dict(self) -> None:
        """Test collision serialization."""
        collision = Collision(
            collision_type=CollisionType.DOOR_BLOCKED,
            item1_id="sofa_001",
            item2_id="door_1",
            description="Sofa blocks door",
            severity="error",
            overlap_amount=0.5,
        )
        d = collision.to_dict()
        assert d["collision_type"] == "door_blocked"
        assert d["item1_id"] == "sofa_001"
        assert d["overlap_amount"] == 0.5


class TestCollisionType:
    """Tests for CollisionType enum."""

    def test_collision_types(self) -> None:
        """Test all collision types exist."""
        assert CollisionType.FURNITURE_OVERLAP.value == "furniture_overlap"
        assert CollisionType.WALL_COLLISION.value == "wall_collision"
        assert CollisionType.DOOR_BLOCKED.value == "door_blocked"
        assert CollisionType.WINDOW_BLOCKED.value == "window_blocked"
        assert CollisionType.CLEARANCE_VIOLATION.value == "clearance_violation"


class TestCollisionDetectorTool:
    """Tests for CollisionDetectorTool."""

    @pytest.fixture
    def tool(self) -> CollisionDetectorTool:
        """Create collision detector tool instance."""
        return CollisionDetectorTool()

    @pytest.fixture
    def non_overlapping_items(self) -> list[PlacedItem]:
        """Create non-overlapping items."""
        return [
            PlacedItem(
                id="bed_001",
                name="Bed",
                bounding_box=BoundingBox(
                    min_x=0.5,
                    min_y=0.0,
                    min_z=0.5,
                    max_x=2.5,
                    max_y=0.5,
                    max_z=2.5,
                ),
            ),
            PlacedItem(
                id="desk_001",
                name="Desk",
                bounding_box=BoundingBox(
                    min_x=3.5,
                    min_y=0.0,
                    min_z=0.5,
                    max_x=4.9,
                    max_y=0.75,
                    max_z=1.2,
                ),
            ),
        ]

    @pytest.fixture
    def overlapping_items(self) -> list[PlacedItem]:
        """Create overlapping items."""
        return [
            PlacedItem(
                id="bed_001",
                name="Bed",
                bounding_box=BoundingBox(
                    min_x=1.0,
                    min_y=0.0,
                    min_z=1.0,
                    max_x=3.0,
                    max_y=0.5,
                    max_z=3.0,
                ),
            ),
            PlacedItem(
                id="desk_001",
                name="Desk",
                bounding_box=BoundingBox(
                    min_x=2.5,
                    min_y=0.0,
                    min_z=2.5,
                    max_x=4.0,
                    max_y=0.75,
                    max_z=3.5,
                ),
            ),
        ]

    def test_tool_name(self, tool: CollisionDetectorTool) -> None:
        """Test tool name property."""
        assert tool.name == "COLLISION_DETECTOR"

    def test_tool_description(self, tool: CollisionDetectorTool) -> None:
        """Test tool description property."""
        assert "collision" in tool.description.lower()

    def test_validate_input_valid(
        self, tool: CollisionDetectorTool, non_overlapping_items: list[PlacedItem]
    ) -> None:
        """Test validation with valid input."""
        input_data = CollisionDetectorInput(
            items=non_overlapping_items,
            room_width=5.0,
            room_depth=4.0,
        )
        errors = tool.validate_input(input_data)
        assert errors == []

    def test_validate_input_invalid_room(self, tool: CollisionDetectorTool) -> None:
        """Test validation with invalid room dimensions."""
        input_data = CollisionDetectorInput(
            items=[],
            room_width=-5.0,
            room_depth=4.0,
        )
        errors = tool.validate_input(input_data)
        assert len(errors) > 0
        assert any("width" in e.lower() for e in errors)

    @pytest.mark.asyncio
    async def test_no_collisions(
        self, tool: CollisionDetectorTool, non_overlapping_items: list[PlacedItem]
    ) -> None:
        """Test detection with no collisions."""
        input_data = CollisionDetectorInput(
            items=non_overlapping_items,
            room_width=6.0,
            room_depth=4.0,
            min_clearance=0.3,  # Low clearance to avoid violations
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data.has_collisions is False
        assert result.data.is_valid_layout is True

    @pytest.mark.asyncio
    async def test_furniture_overlap_detection(
        self, tool: CollisionDetectorTool, overlapping_items: list[PlacedItem]
    ) -> None:
        """Test detection of furniture overlap."""
        input_data = CollisionDetectorInput(
            items=overlapping_items,
            room_width=6.0,
            room_depth=5.0,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data.has_collisions is True

        overlaps = result.data.get_collisions_by_type(CollisionType.FURNITURE_OVERLAP)
        assert len(overlaps) > 0
        assert overlaps[0].overlap_amount > 0

    @pytest.mark.asyncio
    async def test_wall_collision_detection(self, tool: CollisionDetectorTool) -> None:
        """Test detection of wall collisions."""
        # Item extending beyond east wall
        items = [
            PlacedItem(
                id="sofa_001",
                name="Sofa",
                bounding_box=BoundingBox(
                    min_x=4.0,
                    min_y=0.0,
                    min_z=1.0,
                    max_x=6.5,
                    max_y=0.85,
                    max_z=2.0,  # Extends 1.5m beyond 5.0m room
                ),
            ),
        ]
        input_data = CollisionDetectorInput(
            items=items,
            room_width=5.0,
            room_depth=4.0,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data.has_collisions is True

        wall_collisions = result.data.get_collisions_by_type(CollisionType.WALL_COLLISION)
        assert len(wall_collisions) > 0
        assert wall_collisions[0].item2_id == "east_wall"
        assert wall_collisions[0].overlap_amount == pytest.approx(1.5, rel=0.01)

    @pytest.mark.asyncio
    async def test_multiple_wall_collisions(self, tool: CollisionDetectorTool) -> None:
        """Test detection of multiple wall collisions."""
        # Item in corner extending beyond two walls
        items = [
            PlacedItem(
                id="wardrobe_001",
                name="Wardrobe",
                bounding_box=BoundingBox(
                    min_x=-0.5,
                    min_y=0.0,
                    min_z=-0.3,
                    max_x=1.0,
                    max_y=2.0,
                    max_z=1.0,
                ),
            ),
        ]
        input_data = CollisionDetectorInput(
            items=items,
            room_width=5.0,
            room_depth=4.0,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        wall_collisions = result.data.get_collisions_by_type(CollisionType.WALL_COLLISION)
        assert len(wall_collisions) == 2  # West and North walls

    @pytest.mark.asyncio
    async def test_door_blocked_detection(self, tool: CollisionDetectorTool) -> None:
        """Test detection of blocked doors."""
        items = [
            PlacedItem(
                id="cabinet_001",
                name="Cabinet",
                bounding_box=BoundingBox(
                    min_x=2.0,
                    min_y=0.0,
                    min_z=3.0,
                    max_x=3.0,
                    max_y=1.0,
                    max_z=4.0,
                ),
            ),
        ]
        door_swing_boxes = [
            BoundingBox(
                min_x=2.0,
                min_y=0.0,
                min_z=3.0,
                max_x=3.0,
                max_y=2.1,
                max_z=4.0,
            ),
        ]
        input_data = CollisionDetectorInput(
            items=items,
            room_width=5.0,
            room_depth=4.0,
            door_swing_boxes=door_swing_boxes,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data.has_collisions is True

        door_collisions = result.data.get_collisions_by_type(CollisionType.DOOR_BLOCKED)
        assert len(door_collisions) > 0
        assert door_collisions[0].severity == "error"

    @pytest.mark.asyncio
    async def test_window_blocked_detection(self, tool: CollisionDetectorTool) -> None:
        """Test detection of blocked windows."""
        items = [
            PlacedItem(
                id="bookshelf_001",
                name="Bookshelf",
                bounding_box=BoundingBox(
                    min_x=1.5,
                    min_y=0.0,
                    min_z=0.0,
                    max_x=3.0,
                    max_y=1.8,
                    max_z=0.5,
                ),
            ),
        ]
        window_boxes = [
            BoundingBox(
                min_x=1.0,
                min_y=0.0,
                min_z=0.0,
                max_x=3.5,
                max_y=2.0,
                max_z=0.5,
            ),
        ]
        input_data = CollisionDetectorInput(
            items=items,
            room_width=5.0,
            room_depth=4.0,
            window_boxes=window_boxes,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data.has_collisions is True

        window_collisions = result.data.get_collisions_by_type(CollisionType.WINDOW_BLOCKED)
        assert len(window_collisions) > 0
        assert window_collisions[0].severity == "warning"  # Window blocking is a warning

    @pytest.mark.asyncio
    async def test_clearance_violation_detection(self, tool: CollisionDetectorTool) -> None:
        """Test detection of clearance violations."""
        # Items too close together
        items = [
            PlacedItem(
                id="bed_001",
                name="Bed",
                bounding_box=BoundingBox(
                    min_x=0.5,
                    min_y=0.0,
                    min_z=0.5,
                    max_x=2.5,
                    max_y=0.5,
                    max_z=2.5,
                ),
                clearance_required=0.6,
            ),
            PlacedItem(
                id="nightstand_001",
                name="Nightstand",
                bounding_box=BoundingBox(
                    min_x=2.7,
                    min_y=0.0,
                    min_z=1.0,
                    max_x=3.2,
                    max_y=0.6,
                    max_z=1.5,
                ),
                clearance_required=0.3,
            ),
        ]
        input_data = CollisionDetectorInput(
            items=items,
            room_width=5.0,
            room_depth=4.0,
            min_clearance=0.6,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        clearance_violations = result.data.get_collisions_by_type(CollisionType.CLEARANCE_VIOLATION)
        assert len(clearance_violations) > 0
        assert clearance_violations[0].severity == "warning"

    @pytest.mark.asyncio
    async def test_is_valid_layout(self, tool: CollisionDetectorTool) -> None:
        """Test is_valid_layout property."""
        # Layout with only warnings
        items = [
            PlacedItem(
                id="desk_001",
                name="Desk",
                bounding_box=BoundingBox(
                    min_x=1.5,
                    min_y=0.0,
                    min_z=0.0,
                    max_x=3.0,
                    max_y=0.75,
                    max_z=0.5,
                ),
            ),
        ]
        window_boxes = [
            BoundingBox(
                min_x=1.0,
                min_y=0.0,
                min_z=0.0,
                max_x=3.5,
                max_y=2.0,
                max_z=0.5,
            ),
        ]
        input_data = CollisionDetectorInput(
            items=items,
            room_width=5.0,
            room_depth=4.0,
            window_boxes=window_boxes,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data.has_collisions is True
        assert result.data.is_valid_layout is True  # Only warnings, no errors

    @pytest.mark.asyncio
    async def test_get_collisions_for_item(self, tool: CollisionDetectorTool) -> None:
        """Test getting collisions for a specific item."""
        # Create an item that has multiple collisions
        items = [
            PlacedItem(
                id="problem_item",
                name="Problem Item",
                bounding_box=BoundingBox(
                    min_x=-0.5,
                    min_y=0.0,
                    min_z=0.5,  # Extends beyond west wall
                    max_x=1.5,
                    max_y=1.0,
                    max_z=2.5,
                ),
            ),
            PlacedItem(
                id="normal_item",
                name="Normal Item",
                bounding_box=BoundingBox(
                    min_x=3.0,
                    min_y=0.0,
                    min_z=0.5,
                    max_x=4.0,
                    max_y=1.0,
                    max_z=1.5,
                ),
            ),
        ]
        input_data = CollisionDetectorInput(
            items=items,
            room_width=5.0,
            room_depth=4.0,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        problem_collisions = result.data.get_collisions_for_item("problem_item")
        assert len(problem_collisions) > 0
        normal_collisions = result.data.get_collisions_for_item("normal_item")
        assert len(normal_collisions) == 0

    @pytest.mark.asyncio
    async def test_empty_items_list(self, tool: CollisionDetectorTool) -> None:
        """Test with empty items list."""
        input_data = CollisionDetectorInput(
            items=[],
            room_width=5.0,
            room_depth=4.0,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data.has_collisions is False
        assert result.data.is_valid_layout is True

    @pytest.mark.asyncio
    async def test_returns_metadata(
        self, tool: CollisionDetectorTool, overlapping_items: list[PlacedItem]
    ) -> None:
        """Test that execution returns metadata."""
        input_data = CollisionDetectorInput(
            items=overlapping_items,
            room_width=6.0,
            room_depth=5.0,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert "items_checked" in result.metadata
        assert "collisions_found" in result.metadata
        assert result.metadata["items_checked"] == 2

    @pytest.mark.asyncio
    async def test_measures_execution_time(
        self, tool: CollisionDetectorTool, non_overlapping_items: list[PlacedItem]
    ) -> None:
        """Test that execution time is measured."""
        input_data = CollisionDetectorInput(
            items=non_overlapping_items,
            room_width=5.0,
            room_depth=4.0,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.execution_time_ms >= 0

    def test_to_langchain_tool_schema(self, tool: CollisionDetectorTool) -> None:
        """Test LangChain tool schema conversion."""
        schema = tool.to_langchain_tool_schema()

        assert schema["name"] == "COLLISION_DETECTOR"
        assert "parameters" in schema
        assert "items" in schema["parameters"]["properties"]
        assert "room_width" in schema["parameters"]["properties"]


class TestCollisionDetectorOutput:
    """Tests for CollisionDetectorOutput."""

    @pytest.fixture
    def tool(self) -> CollisionDetectorTool:
        """Create tool instance."""
        return CollisionDetectorTool()

    @pytest.mark.asyncio
    async def test_error_and_warning_counts(self, tool: CollisionDetectorTool) -> None:
        """Test error and warning count tracking."""
        items = [
            PlacedItem(
                id="item1",
                name="Item 1",
                bounding_box=BoundingBox(
                    min_x=-0.5,
                    min_y=0.0,
                    min_z=0.5,  # Wall collision (error)
                    max_x=1.5,
                    max_y=1.0,
                    max_z=2.5,
                ),
            ),
        ]
        window_boxes = [
            BoundingBox(
                min_x=0.0,
                min_y=0.0,
                min_z=0.0,
                max_x=2.0,
                max_y=2.0,
                max_z=1.0,  # Window blocked (warning)
            ),
        ]
        input_data = CollisionDetectorInput(
            items=items,
            room_width=5.0,
            room_depth=4.0,
            window_boxes=window_boxes,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data.error_count >= 1  # Wall collision
        assert result.data.warning_count >= 1  # Window blocked
