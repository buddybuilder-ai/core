"""Tests for validator tool."""

import pytest

from src.modules.layout.infrastructure.tools.validator_tool import (
    LayoutItem,
    ValidationIssue,
    ValidationLevel,
    ValidatorInput,
    ValidatorOutput,
    ValidatorTool,
)


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_issue_creation(self) -> None:
        """Test creating a validation issue."""
        issue = ValidationIssue(
            code="TEST_ERROR",
            level=ValidationLevel.ERROR,
            message="Test error message",
            item_field="test_field",
            details={"key": "value"},
        )
        assert issue.code == "TEST_ERROR"
        assert issue.level == ValidationLevel.ERROR
        assert issue.message == "Test error message"
        assert issue.item_field == "test_field"
        assert issue.details["key"] == "value"

    def test_issue_to_dict(self) -> None:
        """Test issue serialization."""
        issue = ValidationIssue(
            code="TEST_ERROR",
            level=ValidationLevel.WARNING,
            message="Test message",
            item_field="field",
        )
        d = issue.to_dict()
        assert d["code"] == "TEST_ERROR"
        assert d["level"] == "warning"


class TestValidationLevel:
    """Tests for ValidationLevel enum."""

    def test_levels(self) -> None:
        """Test validation levels."""
        assert ValidationLevel.ERROR.value == "error"
        assert ValidationLevel.WARNING.value == "warning"
        assert ValidationLevel.INFO.value == "info"


class TestLayoutItem:
    """Tests for LayoutItem dataclass."""

    def test_item_creation(self) -> None:
        """Test creating a layout item."""
        item = LayoutItem(
            id="bed_001",
            name="Queen Bed",
            category="bed",
            pos_x=2.0,
            pos_z=1.5,
            width=1.6,
            depth=2.0,
            rotation=0,
            is_essential=True,
        )
        assert item.id == "bed_001"
        assert item.category == "bed"
        assert item.rotation == 0

    def test_item_defaults(self) -> None:
        """Test item default values."""
        item = LayoutItem(
            id="test",
            name="Test",
            category="test",
            pos_x=0.0,
            pos_z=0.0,
            width=1.0,
            depth=1.0,
        )
        assert item.rotation == 0
        assert item.is_essential is False


class TestValidatorOutput:
    """Tests for ValidatorOutput dataclass."""

    @pytest.fixture
    def sample_output(self) -> ValidatorOutput:
        """Create sample output."""
        issues = [
            ValidationIssue(
                code="ERROR_1",
                level=ValidationLevel.ERROR,
                message="Error 1",
                item_field="item_1",
            ),
            ValidationIssue(
                code="WARNING_1",
                level=ValidationLevel.WARNING,
                message="Warning 1",
                item_field="item_2",
            ),
            ValidationIssue(
                code="INFO_1",
                level=ValidationLevel.INFO,
                message="Info 1",
            ),
        ]
        return ValidatorOutput(
            is_valid=False,
            issues=issues,
            error_count=1,
            warning_count=1,
            info_count=1,
        )

    def test_get_issues_by_level(self, sample_output: ValidatorOutput) -> None:
        """Test filtering issues by level."""
        errors = sample_output.get_issues_by_level(ValidationLevel.ERROR)
        assert len(errors) == 1
        assert errors[0].code == "ERROR_1"

    def test_get_issues_for_item(self, sample_output: ValidatorOutput) -> None:
        """Test getting issues for specific item."""
        item_issues = sample_output.get_issues_for_item("item_1")
        assert len(item_issues) == 1
        assert item_issues[0].code == "ERROR_1"


class TestValidatorTool:
    """Tests for ValidatorTool."""

    @pytest.fixture
    def tool(self) -> ValidatorTool:
        """Create validator tool instance."""
        return ValidatorTool()

    @pytest.fixture
    def valid_bedroom_layout(self) -> ValidatorInput:
        """Create a valid bedroom layout."""
        return ValidatorInput(
            room_width=5.0,
            room_depth=4.0,
            room_type="bedroom",
            items=[
                LayoutItem(
                    id="bed_001",
                    name="Queen Bed",
                    category="bed",
                    pos_x=1.5,
                    pos_z=1.0,
                    width=1.6,
                    depth=2.0,
                    is_essential=True,
                ),
                LayoutItem(
                    id="nightstand_001",
                    name="Nightstand",
                    category="nightstand",
                    pos_x=0.5,
                    pos_z=1.5,
                    width=0.45,
                    depth=0.4,
                ),
            ],
            feng_shui_score=75,
        )

    def test_tool_name(self, tool: ValidatorTool) -> None:
        """Test tool name property."""
        assert tool.name == "VALIDATOR"

    def test_tool_description(self, tool: ValidatorTool) -> None:
        """Test tool description property."""
        assert "validate" in tool.description.lower()

    def test_validate_input_valid(self, tool: ValidatorTool) -> None:
        """Test input validation with valid data."""
        input_data = ValidatorInput(
            room_width=5.0,
            room_depth=4.0,
            room_type="bedroom",
        )
        errors = tool.validate_input(input_data)
        assert errors == []

    def test_validate_input_invalid_room_type(self, tool: ValidatorTool) -> None:
        """Test input validation with invalid room type."""
        input_data = ValidatorInput(
            room_width=5.0,
            room_depth=4.0,
            room_type="invalid",
        )
        errors = tool.validate_input(input_data)
        assert len(errors) > 0

    def test_validate_input_negative_dimensions(self, tool: ValidatorTool) -> None:
        """Test input validation with negative dimensions."""
        input_data = ValidatorInput(
            room_width=-5.0,
            room_depth=4.0,
            room_type="bedroom",
        )
        errors = tool.validate_input(input_data)
        assert len(errors) > 0

    @pytest.mark.asyncio
    async def test_valid_layout_passes(
        self, tool: ValidatorTool, valid_bedroom_layout: ValidatorInput
    ) -> None:
        """Test that valid layout passes validation."""
        result = await tool.execute(valid_bedroom_layout)

        assert result.success is True
        assert result.data is not None
        assert result.data.is_valid is True
        assert result.data.error_count == 0

    @pytest.mark.asyncio
    async def test_missing_essential_furniture(self, tool: ValidatorTool) -> None:
        """Test detection of missing essential furniture."""
        input_data = ValidatorInput(
            room_width=5.0,
            room_depth=4.0,
            room_type="bedroom",
            items=[
                LayoutItem(
                    id="nightstand_001",
                    name="Nightstand",
                    category="nightstand",
                    pos_x=0.5,
                    pos_z=1.5,
                    width=0.45,
                    depth=0.4,
                ),
            ],
            feng_shui_score=50,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data.is_valid is False
        assert result.data.error_count > 0

        missing_issues = [i for i in result.data.issues if i.code == "MISSING_ESSENTIAL"]
        assert len(missing_issues) > 0

    @pytest.mark.asyncio
    async def test_item_out_of_bounds(self, tool: ValidatorTool) -> None:
        """Test detection of item out of room bounds."""
        input_data = ValidatorInput(
            room_width=5.0,
            room_depth=4.0,
            room_type="bedroom",
            items=[
                LayoutItem(
                    id="bed_001",
                    name="Queen Bed",
                    category="bed",
                    pos_x=4.5,  # Will extend beyond room width
                    pos_z=1.0,
                    width=1.6,
                    depth=2.0,
                ),
            ],
            feng_shui_score=50,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data.is_valid is False

        bounds_issues = [i for i in result.data.issues if i.code == "ITEM_OUT_OF_BOUNDS"]
        assert len(bounds_issues) > 0

    @pytest.mark.asyncio
    async def test_negative_position(self, tool: ValidatorTool) -> None:
        """Test detection of negative position."""
        input_data = ValidatorInput(
            room_width=5.0,
            room_depth=4.0,
            room_type="bedroom",
            items=[
                LayoutItem(
                    id="bed_001",
                    name="Queen Bed",
                    category="bed",
                    pos_x=-1.0,  # Negative position
                    pos_z=1.0,
                    width=1.6,
                    depth=2.0,
                ),
            ],
            feng_shui_score=50,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data.is_valid is False
        assert result.data.error_count > 0

    @pytest.mark.asyncio
    async def test_invalid_rotation(self, tool: ValidatorTool) -> None:
        """Test detection of invalid rotation."""
        input_data = ValidatorInput(
            room_width=5.0,
            room_depth=4.0,
            room_type="bedroom",
            items=[
                LayoutItem(
                    id="bed_001",
                    name="Queen Bed",
                    category="bed",
                    pos_x=1.0,
                    pos_z=1.0,
                    width=1.6,
                    depth=2.0,
                    rotation=45,  # Invalid rotation
                ),
            ],
            feng_shui_score=50,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data.is_valid is False

        rotation_issues = [i for i in result.data.issues if i.code == "INVALID_ROTATION"]
        assert len(rotation_issues) > 0

    @pytest.mark.asyncio
    async def test_low_feng_shui_score(self, tool: ValidatorTool) -> None:
        """Test warning for low feng shui score."""
        input_data = ValidatorInput(
            room_width=5.0,
            room_depth=4.0,
            room_type="bedroom",
            items=[
                LayoutItem(
                    id="bed_001",
                    name="Queen Bed",
                    category="bed",
                    pos_x=1.0,
                    pos_z=1.0,
                    width=1.6,
                    depth=2.0,
                ),
            ],
            feng_shui_score=30,  # Below threshold
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data.warning_count > 0

        score_issues = [i for i in result.data.issues if i.code == "LOW_FENG_SHUI_SCORE"]
        assert len(score_issues) > 0

    @pytest.mark.asyncio
    async def test_excellent_feng_shui_score(self, tool: ValidatorTool) -> None:
        """Test info message for excellent feng shui score."""
        input_data = ValidatorInput(
            room_width=5.0,
            room_depth=4.0,
            room_type="bedroom",
            items=[
                LayoutItem(
                    id="bed_001",
                    name="Queen Bed",
                    category="bed",
                    pos_x=1.0,
                    pos_z=1.0,
                    width=1.6,
                    depth=2.0,
                ),
            ],
            feng_shui_score=85,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data.info_count > 0

        excellent_issues = [i for i in result.data.issues if i.code == "EXCELLENT_FENG_SHUI"]
        assert len(excellent_issues) > 0

    @pytest.mark.asyncio
    async def test_overlapping_items(self, tool: ValidatorTool) -> None:
        """Test detection of overlapping items."""
        input_data = ValidatorInput(
            room_width=5.0,
            room_depth=4.0,
            room_type="bedroom",
            items=[
                LayoutItem(
                    id="bed_001",
                    name="Queen Bed",
                    category="bed",
                    pos_x=1.0,
                    pos_z=1.0,
                    width=1.6,
                    depth=2.0,
                ),
                LayoutItem(
                    id="nightstand_001",
                    name="Nightstand",
                    category="nightstand",
                    pos_x=1.5,  # Overlaps with bed
                    pos_z=1.5,
                    width=0.45,
                    depth=0.4,
                ),
            ],
            feng_shui_score=50,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data.is_valid is False

        overlap_issues = [i for i in result.data.issues if i.code == "ITEMS_OVERLAP"]
        assert len(overlap_issues) > 0

    @pytest.mark.asyncio
    async def test_strict_mode_warnings_fail(self, tool: ValidatorTool) -> None:
        """Test that warnings cause failure in strict mode."""
        input_data = ValidatorInput(
            room_width=5.0,
            room_depth=4.0,
            room_type="bedroom",
            items=[
                LayoutItem(
                    id="bed_001",
                    name="Queen Bed",
                    category="bed",
                    pos_x=1.0,
                    pos_z=1.0,
                    width=1.6,
                    depth=2.0,
                ),
            ],
            feng_shui_score=30,  # Low score = warning
            strict_mode=True,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data.is_valid is False  # Fails in strict mode due to warning

    @pytest.mark.asyncio
    async def test_room_size_warnings(self, tool: ValidatorTool) -> None:
        """Test warnings for unusual room sizes."""
        # Very small room
        input_data = ValidatorInput(
            room_width=1.5,  # Very narrow
            room_depth=1.5,
            room_type="bedroom",
            items=[],
            feng_shui_score=50,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        # Should have warnings about room size
        size_issues = [i for i in result.data.issues if "ROOM_TOO" in i.code]
        assert len(size_issues) > 0

    @pytest.mark.asyncio
    async def test_rotated_item_bounds_check(self, tool: ValidatorTool) -> None:
        """Test that rotation is considered for bounds checking."""
        # Item that fits only when rotated
        input_data = ValidatorInput(
            room_width=5.0,
            room_depth=4.0,
            room_type="bedroom",
            items=[
                LayoutItem(
                    id="bed_001",
                    name="Queen Bed",
                    category="bed",
                    pos_x=3.3,  # 3.3 + 1.6 (rotated width) = 4.9 < 5.0
                    pos_z=1.0,
                    width=2.0,  # Would extend past room width if not rotated
                    depth=1.6,
                    rotation=90,  # Rotated, so effective width is 1.6
                ),
            ],
            feng_shui_score=50,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        # Should pass because rotation makes it fit
        bounds_errors = [
            i
            for i in result.data.issues
            if i.code == "ITEM_OUT_OF_BOUNDS" and i.level == ValidationLevel.ERROR
        ]
        assert len(bounds_errors) == 0

    @pytest.mark.asyncio
    async def test_returns_metadata(
        self, tool: ValidatorTool, valid_bedroom_layout: ValidatorInput
    ) -> None:
        """Test that validation returns metadata."""
        result = await tool.execute(valid_bedroom_layout)

        assert result.success is True
        assert "items_validated" in result.metadata
        assert "is_valid" in result.metadata
        assert "error_count" in result.metadata
        assert result.metadata["items_validated"] == 2

    @pytest.mark.asyncio
    async def test_measures_execution_time(
        self, tool: ValidatorTool, valid_bedroom_layout: ValidatorInput
    ) -> None:
        """Test that execution time is measured."""
        result = await tool.execute(valid_bedroom_layout)

        assert result.success is True
        assert result.execution_time_ms >= 0

    def test_to_langchain_tool_schema(self, tool: ValidatorTool) -> None:
        """Test LangChain tool schema conversion."""
        schema = tool.to_langchain_tool_schema()

        assert schema["name"] == "VALIDATOR"
        assert "parameters" in schema
        assert "room_width" in schema["parameters"]["properties"]
        assert "items" in schema["parameters"]["properties"]


class TestRoomTypeValidation:
    """Tests for room type specific validation."""

    @pytest.fixture
    def tool(self) -> ValidatorTool:
        """Create tool instance."""
        return ValidatorTool()

    @pytest.mark.asyncio
    async def test_living_room_requires_sofa(self, tool: ValidatorTool) -> None:
        """Test that living room requires sofa."""
        input_data = ValidatorInput(
            room_width=6.0,
            room_depth=5.0,
            room_type="living_room",
            items=[
                LayoutItem(
                    id="table_001",
                    name="Coffee Table",
                    category="coffee_table",
                    pos_x=2.0,
                    pos_z=2.0,
                    width=1.0,
                    depth=0.6,
                ),
            ],
            feng_shui_score=50,
        )
        result = await tool.execute(input_data)

        missing = [i for i in result.data.issues if i.code == "MISSING_ESSENTIAL"]
        assert len(missing) > 0
        assert any("sofa" in str(i.details) for i in missing)

    @pytest.mark.asyncio
    async def test_office_requires_desk_and_chair(self, tool: ValidatorTool) -> None:
        """Test that office requires desk and chair."""
        input_data = ValidatorInput(
            room_width=4.0,
            room_depth=4.0,
            room_type="office",
            items=[],
            feng_shui_score=50,
        )
        result = await tool.execute(input_data)

        missing = [i for i in result.data.issues if i.code == "MISSING_ESSENTIAL"]
        assert len(missing) >= 2  # desk and chair
