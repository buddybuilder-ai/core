"""Base layout schemas."""

from pydantic import BaseModel, Field


class RoomDimensions(BaseModel):
    """Room dimensions in meters."""

    width: float = Field(..., gt=0, description="Room width in meters")
    depth: float = Field(..., gt=0, description="Room depth in meters")
