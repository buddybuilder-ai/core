"""Collision detector tool for feng shui layout agent."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.modules.layout.domain.value_objects import BoundingBox, Position3D
from src.modules.layout.infrastructure.tools.base import BaseTool, ToolResult


class CollisionType(StrEnum):
    """Types of collisions that can occur."""

    FURNITURE_OVERLAP = "furniture_overlap"  # Two furniture items overlap
    WALL_COLLISION = "wall_collision"  # Furniture extends beyond room
    DOOR_BLOCKED = "door_blocked"  # Furniture blocks door swing
    WINDOW_BLOCKED = "window_blocked"  # Furniture blocks window access
    CLEARANCE_VIOLATION = "clearance_violation"  # Not enough space between items


@dataclass(frozen=True)
class PlacedItem:
    """A placed furniture item for collision detection.

    Attributes:
        id: Unique identifier for the item.
        name: Display name of the item.
        bounding_box: The item's bounding box in room coordinates.
        clearance_required: Required clearance around the item in meters.
    """

    id: str
    name: str
    bounding_box: BoundingBox
    clearance_required: float = 0.6

    @property
    def width(self) -> float:
        """Return width of the item (x-axis)."""
        return self.bounding_box.max_x - self.bounding_box.min_x

    @property
    def depth(self) -> float:
        """Return depth of the item (z-axis)."""
        return self.bounding_box.max_z - self.bounding_box.min_z

    @property
    def height(self) -> float:
        """Return height of the item (y-axis)."""
        return self.bounding_box.max_y - self.bounding_box.min_y

    @property
    def center(self) -> Position3D:
        """Return center position of the item."""
        return Position3D(
            x=(self.bounding_box.min_x + self.bounding_box.max_x) / 2,
            y=(self.bounding_box.min_y + self.bounding_box.max_y) / 2,
            z=(self.bounding_box.min_z + self.bounding_box.max_z) / 2,
        )

    def get_clearance_box(self) -> BoundingBox:
        """Get bounding box expanded by clearance requirement."""
        return BoundingBox(
            min_x=self.bounding_box.min_x - self.clearance_required,
            min_y=self.bounding_box.min_y,
            min_z=self.bounding_box.min_z - self.clearance_required,
            max_x=self.bounding_box.max_x + self.clearance_required,
            max_y=self.bounding_box.max_y,
            max_z=self.bounding_box.max_z + self.clearance_required,
        )


@dataclass(frozen=True)
class Collision:
    """A detected collision between items or boundaries.

    Attributes:
        collision_type: Type of collision detected.
        item1_id: ID of first item involved.
        item2_id: ID of second item involved (or boundary name).
        description: Human-readable description of the collision.
        severity: Severity level (error, warning, info).
        overlap_amount: Amount of overlap in meters (if applicable).
    """

    collision_type: CollisionType
    item1_id: str
    item2_id: str
    description: str
    severity: str = "error"
    overlap_amount: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "collision_type": self.collision_type.value,
            "item1_id": self.item1_id,
            "item2_id": self.item2_id,
            "description": self.description,
            "severity": self.severity,
            "overlap_amount": self.overlap_amount,
        }


@dataclass(frozen=True)
class CollisionDetectorInput:
    """Input for collision detection.

    Attributes:
        items: List of placed items to check.
        room_width: Room width in meters.
        room_depth: Room depth in meters.
        room_height: Room height in meters.
        door_swing_boxes: List of door swing bounding boxes.
        window_boxes: List of window access bounding boxes.
        min_clearance: Minimum clearance between items in meters.
    """

    items: list[PlacedItem]
    room_width: float
    room_depth: float
    room_height: float = 2.8
    door_swing_boxes: list[BoundingBox] = field(default_factory=list)
    window_boxes: list[BoundingBox] = field(default_factory=list)
    min_clearance: float = 0.6


@dataclass(frozen=True)
class CollisionDetectorOutput:
    """Output of collision detection.

    Attributes:
        has_collisions: Whether any collisions were detected.
        collisions: List of detected collisions.
        error_count: Number of error-level collisions.
        warning_count: Number of warning-level collisions.
    """

    has_collisions: bool
    collisions: list[Collision]
    error_count: int
    warning_count: int

    @property
    def is_valid_layout(self) -> bool:
        """Check if layout is valid (no error-level collisions)."""
        return self.error_count == 0

    def get_collisions_by_type(self, collision_type: CollisionType) -> list[Collision]:
        """Get collisions of a specific type."""
        return [c for c in self.collisions if c.collision_type == collision_type]

    def get_collisions_for_item(self, item_id: str) -> list[Collision]:
        """Get all collisions involving a specific item."""
        return [c for c in self.collisions if c.item1_id == item_id or c.item2_id == item_id]


class CollisionDetectorTool(BaseTool[CollisionDetectorInput, CollisionDetectorOutput]):
    """Tool for detecting collisions between furniture items.

    This tool checks for:
    - Furniture-to-furniture overlaps
    - Furniture extending beyond room boundaries
    - Furniture blocking door swings
    - Furniture blocking window access
    - Clearance violations between items
    """

    @property
    def name(self) -> str:
        return "COLLISION_DETECTOR"

    @property
    def description(self) -> str:
        return (
            "Detects collisions between furniture items, room boundaries, "
            "door swing areas, and window access zones. Reports overlap amounts "
            "and clearance violations."
        )

    def validate_input(self, input_data: CollisionDetectorInput) -> list[str]:
        """Validate the collision detection input."""
        errors = []
        if input_data.room_width <= 0:
            errors.append("Room width must be positive")
        if input_data.room_depth <= 0:
            errors.append("Room depth must be positive")
        if input_data.room_height <= 0:
            errors.append("Room height must be positive")
        if input_data.min_clearance < 0:
            errors.append("Minimum clearance must be non-negative")
        return errors

    async def execute(self, input_data: CollisionDetectorInput) -> ToolResult[CollisionDetectorOutput]:
        """Execute collision detection on placed items."""
        import time

        start_time = time.perf_counter()

        collisions: list[Collision] = []
        items = input_data.items

        # Check furniture-to-furniture collisions
        furniture_collisions = self._check_furniture_collisions(items)
        collisions.extend(furniture_collisions)

        # Check wall collisions
        wall_collisions = self._check_wall_collisions(
            items, input_data.room_width, input_data.room_depth, input_data.room_height
        )
        collisions.extend(wall_collisions)

        # Check door swing collisions
        door_collisions = self._check_door_collisions(items, input_data.door_swing_boxes)
        collisions.extend(door_collisions)

        # Check window access collisions
        window_collisions = self._check_window_collisions(items, input_data.window_boxes)
        collisions.extend(window_collisions)

        # Check clearance violations
        clearance_violations = self._check_clearance_violations(items, input_data.min_clearance)
        collisions.extend(clearance_violations)

        # Count by severity
        error_count = sum(1 for c in collisions if c.severity == "error")
        warning_count = sum(1 for c in collisions if c.severity == "warning")

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        output = CollisionDetectorOutput(
            has_collisions=len(collisions) > 0,
            collisions=collisions,
            error_count=error_count,
            warning_count=warning_count,
        )

        return ToolResult.ok(
            data=output,
            execution_time_ms=elapsed_ms,
            metadata={
                "items_checked": len(items),
                "collisions_found": len(collisions),
                "error_count": error_count,
                "warning_count": warning_count,
            },
        )

    def _check_furniture_collisions(self, items: list[PlacedItem]) -> list[Collision]:
        """Check for collisions between furniture items."""
        collisions = []

        for i, item1 in enumerate(items):
            for item2 in items[i + 1 :]:
                if self._boxes_overlap(item1.bounding_box, item2.bounding_box):
                    overlap = self._calculate_overlap(item1.bounding_box, item2.bounding_box)
                    collisions.append(
                        Collision(
                            collision_type=CollisionType.FURNITURE_OVERLAP,
                            item1_id=item1.id,
                            item2_id=item2.id,
                            description=f"'{item1.name}' overlaps with '{item2.name}' by {overlap:.2f}m",
                            severity="error",
                            overlap_amount=overlap,
                        )
                    )

        return collisions

    def _check_wall_collisions(
        self,
        items: list[PlacedItem],
        room_width: float,
        room_depth: float,
        room_height: float,
    ) -> list[Collision]:
        """Check for items extending beyond room boundaries."""
        collisions = []

        for item in items:
            box = item.bounding_box

            # Check each boundary
            if box.min_x < 0:
                collisions.append(
                    Collision(
                        collision_type=CollisionType.WALL_COLLISION,
                        item1_id=item.id,
                        item2_id="west_wall",
                        description=f"'{item.name}' extends {abs(box.min_x):.2f}m beyond west wall",
                        severity="error",
                        overlap_amount=abs(box.min_x),
                    )
                )

            if box.max_x > room_width:
                collisions.append(
                    Collision(
                        collision_type=CollisionType.WALL_COLLISION,
                        item1_id=item.id,
                        item2_id="east_wall",
                        description=f"'{item.name}' extends {box.max_x - room_width:.2f}m beyond east wall",
                        severity="error",
                        overlap_amount=box.max_x - room_width,
                    )
                )

            if box.min_z < 0:
                collisions.append(
                    Collision(
                        collision_type=CollisionType.WALL_COLLISION,
                        item1_id=item.id,
                        item2_id="north_wall",
                        description=f"'{item.name}' extends {abs(box.min_z):.2f}m beyond north wall",
                        severity="error",
                        overlap_amount=abs(box.min_z),
                    )
                )

            if box.max_z > room_depth:
                collisions.append(
                    Collision(
                        collision_type=CollisionType.WALL_COLLISION,
                        item1_id=item.id,
                        item2_id="south_wall",
                        description=f"'{item.name}' extends {box.max_z - room_depth:.2f}m beyond south wall",
                        severity="error",
                        overlap_amount=box.max_z - room_depth,
                    )
                )

            if box.max_y > room_height:
                collisions.append(
                    Collision(
                        collision_type=CollisionType.WALL_COLLISION,
                        item1_id=item.id,
                        item2_id="ceiling",
                        description=f"'{item.name}' extends {box.max_y - room_height:.2f}m beyond ceiling",
                        severity="error",
                        overlap_amount=box.max_y - room_height,
                    )
                )

        return collisions

    def _check_door_collisions(
        self, items: list[PlacedItem], door_swing_boxes: list[BoundingBox]
    ) -> list[Collision]:
        """Check for items blocking door swings."""
        collisions = []

        for i, door_box in enumerate(door_swing_boxes):
            for item in items:
                if self._boxes_overlap(item.bounding_box, door_box):
                    overlap = self._calculate_overlap(item.bounding_box, door_box)
                    collisions.append(
                        Collision(
                            collision_type=CollisionType.DOOR_BLOCKED,
                            item1_id=item.id,
                            item2_id=f"door_{i + 1}",
                            description=f"'{item.name}' blocks door swing area by {overlap:.2f}m",
                            severity="error",
                            overlap_amount=overlap,
                        )
                    )

        return collisions

    def _check_window_collisions(
        self, items: list[PlacedItem], window_boxes: list[BoundingBox]
    ) -> list[Collision]:
        """Check for items blocking window access."""
        collisions = []

        for i, window_box in enumerate(window_boxes):
            for item in items:
                if self._boxes_overlap(item.bounding_box, window_box):
                    overlap = self._calculate_overlap(item.bounding_box, window_box)
                    # Window blocking is a warning, not an error
                    collisions.append(
                        Collision(
                            collision_type=CollisionType.WINDOW_BLOCKED,
                            item1_id=item.id,
                            item2_id=f"window_{i + 1}",
                            description=f"'{item.name}' partially blocks window access by {overlap:.2f}m",
                            severity="warning",
                            overlap_amount=overlap,
                        )
                    )

        return collisions

    def _check_clearance_violations(
        self, items: list[PlacedItem], min_clearance: float
    ) -> list[Collision]:
        """Check for clearance violations between items."""
        collisions = []

        for i, item1 in enumerate(items):
            for item2 in items[i + 1 :]:
                # Skip if items already overlap (handled by furniture_collisions)
                if self._boxes_overlap(item1.bounding_box, item2.bounding_box):
                    continue

                # Use the maximum required clearance between the two items
                required_clearance = max(
                    item1.clearance_required, item2.clearance_required, min_clearance
                )

                # Calculate actual distance between items
                distance = self._calculate_distance(item1.bounding_box, item2.bounding_box)

                if distance < required_clearance:
                    violation_amount = required_clearance - distance
                    collisions.append(
                        Collision(
                            collision_type=CollisionType.CLEARANCE_VIOLATION,
                            item1_id=item1.id,
                            item2_id=item2.id,
                            description=(
                                f"'{item1.name}' and '{item2.name}' are {distance:.2f}m apart, "
                                f"need {required_clearance:.2f}m clearance"
                            ),
                            severity="warning",
                            overlap_amount=violation_amount,
                        )
                    )

        return collisions

    def _boxes_overlap(self, box1: BoundingBox, box2: BoundingBox) -> bool:
        """Check if two bounding boxes overlap."""
        return (
            box1.min_x < box2.max_x
            and box1.max_x > box2.min_x
            and box1.min_y < box2.max_y
            and box1.max_y > box2.min_y
            and box1.min_z < box2.max_z
            and box1.max_z > box2.min_z
        )

    def _calculate_overlap(self, box1: BoundingBox, box2: BoundingBox) -> float:
        """Calculate the overlap amount between two boxes."""
        # Calculate overlap in each dimension
        x_overlap = min(box1.max_x, box2.max_x) - max(box1.min_x, box2.min_x)
        y_overlap = min(box1.max_y, box2.max_y) - max(box1.min_y, box2.min_y)
        z_overlap = min(box1.max_z, box2.max_z) - max(box1.min_z, box2.min_z)

        # Return the minimum overlap as a measure of how much to move
        if x_overlap > 0 and y_overlap > 0 and z_overlap > 0:
            return min(x_overlap, z_overlap)  # Return horizontal overlap
        return 0.0

    def _calculate_distance(self, box1: BoundingBox, box2: BoundingBox) -> float:
        """Calculate the distance between two non-overlapping boxes."""
        # Calculate gaps in each horizontal dimension
        x_gap = max(0, max(box1.min_x, box2.min_x) - min(box1.max_x, box2.max_x))
        z_gap = max(0, max(box1.min_z, box2.min_z) - min(box1.max_z, box2.max_z))

        # Return the Euclidean distance
        return (x_gap**2 + z_gap**2) ** 0.5

    def to_langchain_tool_schema(self) -> dict[str, Any]:
        """Convert to LangChain tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "List of placed items with bounding boxes",
                    },
                    "room_width": {
                        "type": "number",
                        "description": "Room width in meters",
                    },
                    "room_depth": {
                        "type": "number",
                        "description": "Room depth in meters",
                    },
                },
                "required": ["items", "room_width", "room_depth"],
            },
        }
