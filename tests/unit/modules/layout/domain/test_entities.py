"""Tests for domain entities."""

import pytest

from src.modules.layout.domain.entities.furniture import (
    FiveElement,
    Furniture,
    FurnitureCategory,
    FurnitureDimensions,
)
from src.modules.layout.domain.entities.placement import Placement
from src.modules.layout.domain.entities.room import (
    DoorPosition,
    Room,
    RoomType,
    WallSide,
    WindowPosition,
)
from src.modules.layout.domain.value_objects.coordinates import Position3D, Rotation


class TestRoomType:
    """Tests for RoomType enum."""

    def test_room_type_values(self) -> None:
        """Test room type enum values."""
        assert RoomType.BEDROOM == "bedroom"
        assert RoomType.LIVING_ROOM == "living_room"
        assert RoomType.OFFICE == "office"

    def test_essential_furniture(self) -> None:
        """Test essential furniture for each room type."""
        assert "bed" in RoomType.BEDROOM.essential_furniture
        assert "sofa" in RoomType.LIVING_ROOM.essential_furniture
        assert "desk" in RoomType.OFFICE.essential_furniture


class TestWallSide:
    """Tests for WallSide enum."""

    def test_opposite_walls(self) -> None:
        """Test opposite wall calculation."""
        assert WallSide.NORTH.opposite == WallSide.SOUTH
        assert WallSide.SOUTH.opposite == WallSide.NORTH
        assert WallSide.EAST.opposite == WallSide.WEST
        assert WallSide.WEST.opposite == WallSide.EAST

    def test_is_horizontal(self) -> None:
        """Test horizontal wall check."""
        assert WallSide.NORTH.is_horizontal is True
        assert WallSide.SOUTH.is_horizontal is True
        assert WallSide.EAST.is_horizontal is False
        assert WallSide.WEST.is_horizontal is False


class TestDoorPosition:
    """Tests for DoorPosition dataclass."""

    def test_create_door(self) -> None:
        """Test creating a door position."""
        door = DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)
        assert door.wall == WallSide.SOUTH
        assert door.offset == 2.0
        assert door.width == 0.9
        assert door.swing_inward is True

    def test_invalid_offset_raises_error(self) -> None:
        """Test that negative offset raises ValueError."""
        with pytest.raises(ValueError, match="offset"):
            DoorPosition(wall=WallSide.SOUTH, offset=-1.0)

    def test_invalid_width_raises_error(self) -> None:
        """Test that non-positive width raises ValueError."""
        with pytest.raises(ValueError, match="width"):
            DoorPosition(wall=WallSide.SOUTH, offset=1.0, width=0)

    def test_get_swing_area_south_wall(self) -> None:
        """Test door swing area calculation for south wall."""
        door = DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)
        swing = door.get_swing_area(5.0, 4.0)

        assert swing.min_x == 2.0
        assert swing.max_x == 2.9
        assert swing.min_z == 0
        assert swing.max_z == 0.9


class TestWindowPosition:
    """Tests for WindowPosition dataclass."""

    def test_create_window(self) -> None:
        """Test creating a window position."""
        window = WindowPosition(wall=WallSide.EAST, offset=1.5, width=1.5)
        assert window.wall == WallSide.EAST
        assert window.offset == 1.5
        assert window.width == 1.5
        assert window.height == 1.2
        assert window.sill_height == 0.9

    def test_get_natural_light_zone(self) -> None:
        """Test natural light zone calculation."""
        window = WindowPosition(wall=WallSide.EAST, offset=1.5, width=1.5)
        light_zone = window.get_natural_light_zone(5.0, 4.0)

        assert light_zone.min_x == 3.0  # 5.0 - 2.0 (depth)
        assert light_zone.max_x == 5.0


class TestRoom:
    """Tests for Room entity."""

    def test_create_room(self) -> None:
        """Test creating a room."""
        room = Room(width=5.0, depth=4.0, room_type=RoomType.BEDROOM)
        assert room.width == 5.0
        assert room.depth == 4.0
        assert room.height == 2.8
        assert room.room_type == RoomType.BEDROOM

    def test_invalid_dimensions_raises_error(self) -> None:
        """Test that invalid dimensions raise ValueError."""
        with pytest.raises(ValueError, match="width"):
            Room(width=0, depth=4.0)
        with pytest.raises(ValueError, match="depth"):
            Room(width=5.0, depth=-1.0)

    def test_floor_area(self) -> None:
        """Test floor area calculation."""
        room = Room(width=5.0, depth=4.0)
        assert room.floor_area == 20.0

    def test_volume(self) -> None:
        """Test volume calculation."""
        room = Room(width=5.0, depth=4.0, height=3.0)
        assert room.volume == 60.0

    def test_bounding_box(self) -> None:
        """Test room bounding box."""
        room = Room(width=5.0, depth=4.0, height=2.8)
        bbox = room.bounding_box
        assert bbox.min_x == 0
        assert bbox.max_x == 5.0
        assert bbox.max_z == 4.0
        assert bbox.max_y == 2.8

    def test_center(self) -> None:
        """Test room center calculation."""
        room = Room(width=6.0, depth=4.0, height=3.0)
        center = room.center
        assert center.x == 3.0
        assert center.y == 1.5
        assert center.z == 2.0

    def test_floor_center(self) -> None:
        """Test floor center calculation."""
        room = Room(width=6.0, depth=4.0)
        floor_center = room.floor_center
        assert floor_center.x == 3.0
        assert floor_center.y == 0
        assert floor_center.z == 2.0

    def test_command_position_with_south_door(self) -> None:
        """Test command position with door on south wall."""
        door = DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)
        room = Room(width=5.0, depth=4.0, doors=[door])

        cmd_pos = room.get_command_position()
        # Should be in back of room (high z), opposite from door
        assert cmd_pos.z == pytest.approx(4.0 * 0.85)
        assert cmd_pos.y == 0

    def test_command_position_without_doors(self) -> None:
        """Test command position when no doors specified."""
        room = Room(width=5.0, depth=4.0)
        cmd_pos = room.get_command_position()

        # Default to far corner
        assert cmd_pos.x == pytest.approx(5.0 * 0.85)
        assert cmd_pos.z == pytest.approx(4.0 * 0.85)

    def test_wealth_corner(self) -> None:
        """Test wealth corner calculation."""
        door = DoorPosition(wall=WallSide.SOUTH, offset=1.0, width=0.9)
        room = Room(width=5.0, depth=4.0, doors=[door])

        wealth = room.get_wealth_corner()
        # Door on left side of south wall, wealth corner in far right
        assert wealth.x == pytest.approx(5.0 * 0.9)
        assert wealth.z == pytest.approx(4.0 * 0.9)

    def test_is_position_valid(self) -> None:
        """Test position validity check."""
        room = Room(width=5.0, depth=4.0)

        assert room.is_position_valid(Position3D(2.5, 1.0, 2.0)) is True
        assert room.is_position_valid(Position3D(6.0, 1.0, 2.0)) is False
        assert room.is_position_valid(Position3D(-1.0, 1.0, 2.0)) is False

    def test_get_wall_length(self) -> None:
        """Test wall length calculation."""
        room = Room(width=5.0, depth=4.0)

        assert room.get_wall_length(WallSide.NORTH) == 5.0
        assert room.get_wall_length(WallSide.SOUTH) == 5.0
        assert room.get_wall_length(WallSide.EAST) == 4.0
        assert room.get_wall_length(WallSide.WEST) == 4.0


class TestFurnitureCategory:
    """Tests for FurnitureCategory enum."""

    def test_is_seating(self) -> None:
        """Test seating category check."""
        assert FurnitureCategory.SOFA.is_seating is True
        assert FurnitureCategory.ARMCHAIR.is_seating is True
        assert FurnitureCategory.BED.is_seating is False
        assert FurnitureCategory.DESK.is_seating is False

    def test_is_surface(self) -> None:
        """Test surface/table category check."""
        assert FurnitureCategory.DESK.is_surface is True
        assert FurnitureCategory.COFFEE_TABLE.is_surface is True
        assert FurnitureCategory.SOFA.is_surface is False

    def test_needs_wall(self) -> None:
        """Test wall-backing requirement check."""
        assert FurnitureCategory.BED.needs_wall is True
        assert FurnitureCategory.WARDROBE.needs_wall is True
        assert FurnitureCategory.SOFA.needs_wall is False
        assert FurnitureCategory.COFFEE_TABLE.needs_wall is False


class TestFiveElement:
    """Tests for FiveElement enum."""

    def test_generative_cycle(self) -> None:
        """Test element produces relationship."""
        assert FiveElement.WOOD.produces == FiveElement.FIRE
        assert FiveElement.FIRE.produces == FiveElement.EARTH
        assert FiveElement.EARTH.produces == FiveElement.METAL
        assert FiveElement.METAL.produces == FiveElement.WATER
        assert FiveElement.WATER.produces == FiveElement.WOOD

    def test_exhaustive_cycle(self) -> None:
        """Test element weakens relationship."""
        assert FiveElement.WOOD.weakens == FiveElement.WATER
        assert FiveElement.FIRE.weakens == FiveElement.WOOD


class TestFurnitureDimensions:
    """Tests for FurnitureDimensions dataclass."""

    def test_create_dimensions(self) -> None:
        """Test creating furniture dimensions."""
        dims = FurnitureDimensions(width=2.0, depth=1.0, height=0.8)
        assert dims.width == 2.0
        assert dims.depth == 1.0
        assert dims.height == 0.8

    def test_invalid_dimensions_raises_error(self) -> None:
        """Test that invalid dimensions raise ValueError."""
        with pytest.raises(ValueError, match="Width"):
            FurnitureDimensions(width=0, depth=1.0, height=0.8)

    def test_floor_area(self) -> None:
        """Test floor area calculation."""
        dims = FurnitureDimensions(width=2.0, depth=1.5, height=0.8)
        assert dims.floor_area == 3.0

    def test_volume(self) -> None:
        """Test volume calculation."""
        dims = FurnitureDimensions(width=2.0, depth=1.0, height=0.5)
        assert dims.volume == 1.0

    def test_scale(self) -> None:
        """Test dimension scaling."""
        dims = FurnitureDimensions(width=2.0, depth=1.0, height=0.8)
        scaled = dims.scale(0.5)
        assert scaled.width == 1.0
        assert scaled.depth == 0.5
        assert scaled.height == 0.4

    def test_fits_in(self) -> None:
        """Test fit checking."""
        dims = FurnitureDimensions(width=2.0, depth=1.0, height=0.8)

        # Fits normally
        assert dims.fits_in(3.0, 2.0) is True
        # Fits rotated
        assert dims.fits_in(1.5, 2.5) is True
        # Doesn't fit
        assert dims.fits_in(1.5, 0.5) is False


class TestFurniture:
    """Tests for Furniture entity."""

    @pytest.fixture
    def sample_furniture(self) -> Furniture:
        """Create sample furniture for testing."""
        return Furniture(
            id="bed_001",
            name="Queen Bed",
            category=FurnitureCategory.BED,
            dimensions=FurnitureDimensions(width=1.6, depth=2.0, height=0.5),
            min_clearance=0.6,
            element=FiveElement.WOOD,
            is_essential=True,
        )

    def test_create_furniture(self, sample_furniture: Furniture) -> None:
        """Test creating furniture."""
        assert sample_furniture.id == "bed_001"
        assert sample_furniture.name == "Queen Bed"
        assert sample_furniture.category == FurnitureCategory.BED
        assert sample_furniture.is_essential is True

    def test_empty_id_raises_error(self) -> None:
        """Test that empty id raises ValueError."""
        with pytest.raises(ValueError, match="id"):
            Furniture(
                id="",
                name="Test",
                category=FurnitureCategory.BED,
                dimensions=FurnitureDimensions(1.0, 1.0, 1.0),
            )

    def test_get_bounding_box(self, sample_furniture: Furniture) -> None:
        """Test bounding box at position."""
        pos = Position3D(x=2.0, y=0, z=2.0)
        bbox = sample_furniture.get_bounding_box(pos)

        # Centered at position
        assert bbox.min_x == pytest.approx(2.0 - 0.8)  # half width
        assert bbox.max_x == pytest.approx(2.0 + 0.8)
        assert bbox.min_z == pytest.approx(2.0 - 1.0)  # half depth
        assert bbox.max_z == pytest.approx(2.0 + 1.0)

    def test_get_clearance_box(self, sample_furniture: Furniture) -> None:
        """Test clearance box at position."""
        pos = Position3D(x=2.0, y=0, z=2.0)
        clearance = sample_furniture.get_clearance_box(pos)
        bbox = sample_furniture.get_bounding_box(pos)

        # Should be expanded by min_clearance (0.6)
        assert clearance.min_x == pytest.approx(bbox.min_x - 0.6)
        assert clearance.max_x == pytest.approx(bbox.max_x + 0.6)

    def test_fits_in_room(self, sample_furniture: Furniture) -> None:
        """Test room fit checking."""
        assert sample_furniture.fits_in_room(5.0, 4.0) is True
        assert sample_furniture.fits_in_room(1.0, 1.0) is False

    def test_needs_wall_backing(self, sample_furniture: Furniture) -> None:
        """Test wall backing check."""
        assert sample_furniture.needs_wall_backing is True


class TestPlacement:
    """Tests for Placement entity."""

    @pytest.fixture
    def sample_furniture(self) -> Furniture:
        """Create sample furniture for testing."""
        return Furniture(
            id="sofa_001",
            name="3-Seater Sofa",
            category=FurnitureCategory.SOFA,
            dimensions=FurnitureDimensions(width=2.0, depth=0.9, height=0.85),
        )

    @pytest.fixture
    def sample_placement(self, sample_furniture: Furniture) -> Placement:
        """Create sample placement for testing."""
        return Placement(
            furniture=sample_furniture,
            position=Position3D(x=2.5, y=0, z=2.0),
            rotation=Rotation.DEG_0,
        )

    def test_create_placement(self, sample_placement: Placement) -> None:
        """Test creating a placement."""
        assert sample_placement.furniture.id == "sofa_001"
        assert sample_placement.position.x == 2.5
        assert sample_placement.rotation == Rotation.DEG_0
        assert sample_placement.scale == 1.0

    def test_invalid_scale_raises_error(self, sample_furniture: Furniture) -> None:
        """Test that invalid scale raises ValueError."""
        with pytest.raises(ValueError, match="scale"):
            Placement(
                furniture=sample_furniture,
                position=Position3D(0, 0, 0),
                scale=1.5,  # > 1.0
            )

    def test_effective_dimensions_no_rotation(self, sample_placement: Placement) -> None:
        """Test effective dimensions without rotation."""
        assert sample_placement.effective_width == 2.0
        assert sample_placement.effective_depth == 0.9

    def test_effective_dimensions_with_rotation(self, sample_furniture: Furniture) -> None:
        """Test effective dimensions with 90 degree rotation."""
        placement = Placement(
            furniture=sample_furniture,
            position=Position3D(0, 0, 0),
            rotation=Rotation.DEG_90,
        )
        # Width and depth swap when rotated 90 degrees
        assert placement.effective_width == 0.9
        assert placement.effective_depth == 2.0

    def test_effective_dimensions_with_scale(self, sample_furniture: Furniture) -> None:
        """Test effective dimensions with scale."""
        placement = Placement(
            furniture=sample_furniture,
            position=Position3D(0, 0, 0),
            scale=0.8,
        )
        assert placement.effective_width == pytest.approx(2.0 * 0.8)
        assert placement.effective_depth == pytest.approx(0.9 * 0.8)

    def test_get_bounding_box(self, sample_placement: Placement) -> None:
        """Test bounding box calculation."""
        bbox = sample_placement.get_bounding_box()

        assert bbox.min_x == pytest.approx(2.5 - 1.0)
        assert bbox.max_x == pytest.approx(2.5 + 1.0)
        assert bbox.min_z == pytest.approx(2.0 - 0.45)
        assert bbox.max_z == pytest.approx(2.0 + 0.45)

    def test_collides_with(self, sample_furniture: Furniture) -> None:
        """Test collision detection between placements."""
        placement1 = Placement(
            furniture=sample_furniture,
            position=Position3D(x=2.0, y=0, z=2.0),
        )
        placement2 = Placement(
            furniture=sample_furniture,
            position=Position3D(x=2.5, y=0, z=2.0),  # Overlapping
        )
        placement3 = Placement(
            furniture=sample_furniture,
            position=Position3D(x=10.0, y=0, z=10.0),  # Far away
        )

        assert placement1.collides_with(placement2) is True
        assert placement1.collides_with(placement3) is False

    def test_is_in_bounds(self, sample_placement: Placement) -> None:
        """Test bounds checking."""
        # Placement at (2.5, 0, 2.0) with width 2.0
        assert sample_placement.is_in_bounds(5.0, 4.0) is True
        assert sample_placement.is_in_bounds(2.0, 2.0) is False

    def test_distance_to(self, sample_furniture: Furniture) -> None:
        """Test distance calculation between placements."""
        placement1 = Placement(
            furniture=sample_furniture,
            position=Position3D(x=0, y=0, z=0),
        )
        placement2 = Placement(
            furniture=sample_furniture,
            position=Position3D(x=3, y=0, z=4),
        )
        assert placement1.distance_to(placement2) == 5.0

    def test_is_against_wall(self, sample_furniture: Furniture) -> None:
        """Test wall proximity check."""
        # Placement near west wall (x=0)
        near_wall = Placement(
            furniture=sample_furniture,
            position=Position3D(x=1.0, y=0, z=2.0),  # bbox.min_x = 0
        )
        # Placement in center
        in_center = Placement(
            furniture=sample_furniture,
            position=Position3D(x=2.5, y=0, z=2.0),
        )

        assert near_wall.is_against_wall(5.0, 4.0) is True
        assert in_center.is_against_wall(5.0, 4.0) is False

    def test_with_rotation(self, sample_placement: Placement) -> None:
        """Test creating placement with new rotation."""
        rotated = sample_placement.with_rotation(Rotation.DEG_90)

        assert rotated.rotation == Rotation.DEG_90
        assert rotated.position == sample_placement.position
        assert rotated.furniture == sample_placement.furniture

    def test_with_position(self, sample_placement: Placement) -> None:
        """Test creating placement with new position."""
        new_pos = Position3D(x=5.0, y=0, z=5.0)
        moved = sample_placement.with_position(new_pos)

        assert moved.position == new_pos
        assert moved.rotation == sample_placement.rotation

    def test_with_scale(self, sample_placement: Placement) -> None:
        """Test creating placement with new scale."""
        scaled = sample_placement.with_scale(0.8)

        assert scaled.scale == 0.8
        assert scaled.position == sample_placement.position

    def test_add_feng_shui_note(self, sample_placement: Placement) -> None:
        """Test adding feng shui notes."""
        sample_placement.add_feng_shui_note("Placed in command position")
        sample_placement.add_feng_shui_note("Facing door")

        assert len(sample_placement.feng_shui_notes) == 2
        assert "command position" in sample_placement.feng_shui_notes[0]
