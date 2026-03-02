"""Tests for output builder service."""

import pytest

from src.modules.layout.application.dtos import (
    AgentContext,
    PlacedFurniture,
    PlacementStrategy,
)
from src.modules.layout.application.dtos.placement_result import (
    BatchPlacementResult,
    PlacementStatus,
)
from src.modules.layout.application.services.output_builder import (
    LayoutReport,
    OutputBuilder,
    OutputConfig,
    OutputSummary,
    build_layout_report,
)
from src.modules.layout.domain.entities import DoorPosition, Room, RoomType
from src.modules.layout.domain.value_objects import FengShuiScore


class TestOutputConfig:
    """Tests for OutputConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = OutputConfig()
        assert config.include_metadata is True
        assert config.include_recommendations is True
        assert config.include_warnings is True
        assert config.max_recommendations == 5
        assert config.json_indent == 2

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = OutputConfig(
            include_metadata=False,
            max_recommendations=3,
            json_indent=None,
        )
        assert config.include_metadata is False
        assert config.max_recommendations == 3
        assert config.json_indent is None


class TestOutputSummary:
    """Tests for OutputSummary."""

    def test_summary_creation(self) -> None:
        """Test creating an output summary."""
        summary = OutputSummary(
            total_items=5,
            essential_items=2,
            optional_items=3,
            feng_shui_score=75,
            feng_shui_grade="B",
        )
        assert summary.total_items == 5
        assert summary.feng_shui_grade == "B"

    def test_summary_to_dict(self) -> None:
        """Test converting summary to dictionary."""
        summary = OutputSummary(
            total_items=3,
            feng_shui_score=80,
            feng_shui_grade="B",
            has_warnings=True,
            warning_count=2,
        )
        result = summary.to_dict()

        assert result["total_items"] == 3
        assert result["feng_shui_score"] == 80
        assert result["has_warnings"] is True


class TestOutputBuilder:
    """Tests for OutputBuilder."""

    @pytest.fixture
    def room(self) -> Room:
        """Create test room."""
        return Room(
            width=5.0,
            depth=4.0,
            height=2.8,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall="south", offset=2.0, width=0.9)],
        )

    @pytest.fixture
    def builder(self) -> OutputBuilder:
        """Create test output builder."""
        return OutputBuilder()

    @pytest.fixture
    def bed(self) -> PlacedFurniture:
        """Create test bed."""
        return PlacedFurniture(
            id="bed_1",
            furniture_id="bed_001",
            name="Queen Bed",
            category="bed",
            pos_x=1.5,
            pos_z=0.3,
            width=1.6,
            depth=2.0,
            height=0.5,
            rotation=0,
            is_essential=True,
            placement_strategy=PlacementStrategy.COMMAND_POSITION,
        )

    @pytest.fixture
    def nightstand(self) -> PlacedFurniture:
        """Create test nightstand."""
        return PlacedFurniture(
            id="nightstand_1",
            furniture_id="nightstand_001",
            name="Nightstand",
            category="nightstand",
            pos_x=0.3,
            pos_z=0.5,
            width=0.45,
            depth=0.4,
            height=0.55,
            rotation=0,
            is_essential=False,
        )

    @pytest.fixture
    def good_score(self) -> FengShuiScore:
        """Create good feng shui score."""
        return FengShuiScore(
            command_position=25,
            five_elements=15,
            chi_flow=20,
            sha_chi_avoidance=20,
        )

    def test_build_output_empty(
        self,
        builder: OutputBuilder,
        room: Room,
    ) -> None:
        """Test building output with no furniture."""
        output = builder.build_output(room, [])

        assert output.room_type == "bedroom"
        assert output.feng_shui_score == 0
        assert len(output.furniture) == 0
        assert len(output.warnings) > 0  # Should have warning about empty layout

    def test_build_output_with_furniture(
        self,
        builder: OutputBuilder,
        room: Room,
        bed: PlacedFurniture,
        nightstand: PlacedFurniture,
        good_score: FengShuiScore,
    ) -> None:
        """Test building output with furniture."""
        output = builder.build_output(
            room,
            [bed, nightstand],
            feng_shui_score=good_score,
        )

        assert output.room_type == "bedroom"
        assert output.feng_shui_score == 80
        assert len(output.furniture) == 2
        assert output.score_breakdown["command_position"] == 25

    def test_build_output_with_metadata(
        self,
        builder: OutputBuilder,
        room: Room,
        bed: PlacedFurniture,
        good_score: FengShuiScore,
    ) -> None:
        """Test that metadata is included."""
        output = builder.build_output(
            room,
            [bed],
            feng_shui_score=good_score,
        )

        assert "room" in output.metadata
        assert "furniture" in output.metadata
        assert "score" in output.metadata
        assert output.metadata["furniture"]["total_count"] == 1
        assert output.metadata["furniture"]["essential_count"] == 1

    def test_build_output_without_metadata(
        self,
        room: Room,
        bed: PlacedFurniture,
    ) -> None:
        """Test building output without metadata."""
        config = OutputConfig(include_metadata=False)
        builder = OutputBuilder(config)

        output = builder.build_output(room, [bed])

        assert output.metadata == {}

    def test_build_output_recommendations(
        self,
        builder: OutputBuilder,
        room: Room,
        bed: PlacedFurniture,
    ) -> None:
        """Test that recommendations are included for low scores."""
        low_score = FengShuiScore(
            command_position=5,
            five_elements=5,
            chi_flow=5,
            sha_chi_avoidance=5,
        )
        output = builder.build_output(
            room,
            [bed],
            feng_shui_score=low_score,
        )

        # Low score should generate recommendations
        assert len(output.recommendations) > 0

    def test_build_output_max_recommendations(
        self,
        room: Room,
        bed: PlacedFurniture,
    ) -> None:
        """Test max recommendations limit."""
        config = OutputConfig(max_recommendations=2)
        builder = OutputBuilder(config)

        low_score = FengShuiScore(
            command_position=5,
            five_elements=5,
            chi_flow=5,
            sha_chi_avoidance=5,
        )
        output = builder.build_output(
            room,
            [bed],
            feng_shui_score=low_score,
        )

        assert len(output.recommendations) <= 2

    def test_build_output_warnings_low_score(
        self,
        builder: OutputBuilder,
        room: Room,
        bed: PlacedFurniture,
    ) -> None:
        """Test warning for low feng shui score."""
        low_score = FengShuiScore(
            command_position=5,
            five_elements=5,
            chi_flow=5,
            sha_chi_avoidance=5,
        )
        output = builder.build_output(
            room,
            [bed],
            feng_shui_score=low_score,
        )

        assert any("Low feng shui score" in w for w in output.warnings)


class TestOutputBuilderFromContext:
    """Tests for building output from context."""

    @pytest.fixture
    def context(self) -> AgentContext:
        """Create test agent context."""
        room = Room(
            width=5.0,
            depth=4.0,
            height=2.8,
            room_type=RoomType.BEDROOM,
        )
        ctx = AgentContext(room=room, room_type="bedroom")
        ctx.placed_furniture = [
            PlacedFurniture(
                id="bed_1",
                furniture_id="bed_001",
                name="Bed",
                category="bed",
                pos_x=1.5,
                pos_z=0.3,
                width=1.6,
                depth=2.0,
                height=0.5,
                rotation=0,
                is_essential=True,
            ),
        ]
        ctx.feng_shui_score = FengShuiScore(
            command_position=20,
            five_elements=12,
            chi_flow=18,
            sha_chi_avoidance=18,
        )
        return ctx

    def test_build_from_context(self, context: AgentContext) -> None:
        """Test building output from agent context."""
        builder = OutputBuilder()
        output = builder.build_from_context(context)

        assert output.room_type == "bedroom"
        assert len(output.furniture) == 1
        assert output.feng_shui_score == 68


class TestOutputBuilderFormats:
    """Tests for output format methods."""

    @pytest.fixture
    def builder(self) -> OutputBuilder:
        """Create test builder."""
        return OutputBuilder()

    @pytest.fixture
    def room(self) -> Room:
        """Create test room."""
        return Room(
            width=5.0,
            depth=4.0,
            height=2.8,
            room_type=RoomType.BEDROOM,
        )

    @pytest.fixture
    def furniture(self) -> list[PlacedFurniture]:
        """Create test furniture list."""
        return [
            PlacedFurniture(
                id="bed_1",
                furniture_id="bed_001",
                name="Bed",
                category="bed",
                pos_x=1.5,
                pos_z=0.3,
                width=1.6,
                depth=2.0,
                height=0.5,
                rotation=0,
                is_essential=True,
            ),
        ]

    def test_format_as_json(
        self,
        builder: OutputBuilder,
        room: Room,
        furniture: list[PlacedFurniture],
    ) -> None:
        """Test JSON formatting."""
        output = builder.build_output(room, furniture)
        json_output = builder.format_as_json(output)

        assert "room_type" in json_output
        assert "furniture" in json_output
        assert "feng_shui_score" in json_output

    def test_format_as_simple_json(
        self,
        builder: OutputBuilder,
        room: Room,
        furniture: list[PlacedFurniture],
    ) -> None:
        """Test simplified JSON formatting."""
        output = builder.build_output(room, furniture)
        json_output = builder.format_as_simple_json(output)

        assert "room" in json_output
        assert "items" in json_output
        assert "score" in json_output
        assert json_output["room"]["type"] == "bedroom"

    def test_format_furniture_for_api(
        self,
        builder: OutputBuilder,
        furniture: list[PlacedFurniture],
    ) -> None:
        """Test furniture formatting for API."""
        api_furniture = builder.format_furniture_for_api(furniture)

        assert len(api_furniture) == 1
        assert api_furniture[0]["id"] == "bed_1"
        assert "position" in api_furniture[0]
        assert "dimensions" in api_furniture[0]
        assert api_furniture[0]["position"]["y"] == 0  # Floor level


class TestOutputBuilderSummary:
    """Tests for get_summary method."""

    @pytest.fixture
    def builder(self) -> OutputBuilder:
        """Create test builder."""
        return OutputBuilder()

    def test_get_summary(self, builder: OutputBuilder) -> None:
        """Test getting output summary."""
        furniture = [
            PlacedFurniture(
                id="bed",
                furniture_id="bed_001",
                name="Bed",
                category="bed",
                pos_x=0,
                pos_z=0,
                width=1.6,
                depth=2.0,
                height=0.5,
                is_essential=True,
            ),
            PlacedFurniture(
                id="nightstand",
                furniture_id="nightstand_001",
                name="Nightstand",
                category="nightstand",
                pos_x=2,
                pos_z=0,
                width=0.45,
                depth=0.4,
                height=0.55,
                is_essential=False,
            ),
        ]
        score = FengShuiScore(
            command_position=25,
            five_elements=15,
            chi_flow=20,
            sha_chi_avoidance=20,
        )
        warnings = ["Test warning"]

        summary = builder.get_summary(furniture, score, warnings)

        assert summary.total_items == 2
        assert summary.essential_items == 1
        assert summary.optional_items == 1
        assert summary.feng_shui_score == 80
        assert summary.feng_shui_grade == "B"
        assert summary.has_warnings is True
        assert summary.warning_count == 1


class TestOutputBuilderContextUpdate:
    """Tests for context update."""

    @pytest.fixture
    def builder(self) -> OutputBuilder:
        """Create test builder."""
        return OutputBuilder()

    def test_update_context(self, builder: OutputBuilder) -> None:
        """Test updating agent context."""
        room = Room(
            width=5.0,
            depth=4.0,
            height=2.8,
            room_type=RoomType.BEDROOM,
        )
        context = AgentContext(room=room, room_type="bedroom")

        furniture = [
            PlacedFurniture(
                id="bed",
                furniture_id="bed_001",
                name="Bed",
                category="bed",
                pos_x=1.5,
                pos_z=0.3,
                width=1.6,
                depth=2.0,
                height=0.5,
                is_essential=True,
            ),
        ]
        score = FengShuiScore(
            command_position=25,
            five_elements=15,
            chi_flow=20,
            sha_chi_avoidance=20,
        )

        output = builder.build_output(room, furniture, score)
        builder.update_context(context, output)

        assert "output" in context.metadata
        assert context.metadata["output"]["feng_shui_score"] == 80


class TestLayoutReport:
    """Tests for LayoutReport."""

    def test_report_creation(self) -> None:
        """Test creating a layout report."""
        from src.modules.layout.application.dtos.placement_result import LayoutOutput

        output = LayoutOutput(
            room_type="bedroom",
            room_dimensions={"width": 5.0, "depth": 4.0, "height": 2.8},
            furniture=[],
            feng_shui_score=75,
        )
        summary = OutputSummary(feng_shui_score=75, feng_shui_grade="B")

        report = LayoutReport(
            output=output,
            summary=summary,
            success=True,
        )

        assert report.success is True
        assert report.output is not None
        assert report.error_message is None

    def test_report_to_dict(self) -> None:
        """Test converting report to dictionary."""
        summary = OutputSummary(feng_shui_score=60, feng_shui_grade="C")
        report = LayoutReport(
            output=None,
            summary=summary,
            success=False,
            error_message="Test error",
        )

        result = report.to_dict()
        assert result["success"] is False
        assert result["error_message"] == "Test error"
        assert result["output"] is None


class TestBuildLayoutReport:
    """Tests for build_layout_report function."""

    def test_build_layout_report_success(self) -> None:
        """Test building report from context."""
        room = Room(
            width=5.0,
            depth=4.0,
            height=2.8,
            room_type=RoomType.BEDROOM,
        )
        context = AgentContext(room=room, room_type="bedroom")
        context.placed_furniture = [
            PlacedFurniture(
                id="bed",
                furniture_id="bed_001",
                name="Bed",
                category="bed",
                pos_x=1.5,
                pos_z=0.3,
                width=1.6,
                depth=2.0,
                height=0.5,
                is_essential=True,
            ),
        ]
        context.feng_shui_score = FengShuiScore(
            command_position=25,
            five_elements=15,
            chi_flow=20,
            sha_chi_avoidance=20,
        )

        report = build_layout_report(context)

        assert report.success is True
        assert report.output is not None
        assert report.summary.total_items == 1
        assert report.summary.feng_shui_score == 80


class TestWarningGeneration:
    """Tests for warning generation."""

    @pytest.fixture
    def builder(self) -> OutputBuilder:
        """Create test builder."""
        return OutputBuilder()

    @pytest.fixture
    def room(self) -> Room:
        """Create test room."""
        return Room(
            width=5.0,
            depth=4.0,
            height=2.8,
            room_type=RoomType.BEDROOM,
        )

    def test_warning_failed_placement(
        self,
        builder: OutputBuilder,
        room: Room,
    ) -> None:
        """Test warning when placements fail."""
        placement_result = BatchPlacementResult(
            total_items=3,
            placed_count=2,
            failed_count=1,
            overall_status=PlacementStatus.PARTIAL,
        )

        output = builder.build_output(
            room,
            [],
            placement_result=placement_result,
        )

        assert any("could not be placed" in w for w in output.warnings)

    def test_warning_no_essential_furniture(
        self,
        builder: OutputBuilder,
        room: Room,
    ) -> None:
        """Test warning when no essential furniture placed."""
        # Only optional furniture
        furniture = [
            PlacedFurniture(
                id="lamp",
                furniture_id="lamp_001",
                name="Lamp",
                category="lamp",
                pos_x=1.0,
                pos_z=1.0,
                width=0.3,
                depth=0.3,
                height=1.5,
                is_essential=False,
            ),
        ]

        output = builder.build_output(room, furniture)

        assert any("essential furniture" in w.lower() for w in output.warnings)
