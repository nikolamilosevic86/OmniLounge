from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from server.game.room_object_catalog import COLOR_PRESETS, MATERIAL_PRESETS, is_valid_object_type


class TileCoordinateModel(BaseModel):
    tile_x: int
    tile_y: int

    @field_validator("tile_x", "tile_y")
    @classmethod
    def validate_tile_bounds(cls, value: int) -> int:
        if value < -2 or value > 2:
            raise ValueError("tile coordinates must stay within MVP 5x5 bounds [-2, 2]")
        return value


class BoundsModel(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @model_validator(mode="after")
    def validate_bounds(self) -> "BoundsModel":
        if self.max_x < self.min_x or self.max_y < self.min_y:
            raise ValueError("max bounds must be greater than or equal to min bounds")
        return self


class RoomObjectPlacementModel(BaseModel):
    object_id: str = Field(min_length=1, max_length=64)
    object_type: str = Field(min_length=1, max_length=40)
    tile_x: int
    tile_y: int
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    z_index: int = 0
    is_locked: bool = False
    interaction_radius: float = 20.0
    size_preset: Literal["S", "M", "L"] | None = None
    color: str | None = None
    material: str | None = None
    edit_permission: Literal["owner_only", "anyone"] = "owner_only"
    interaction_cooldown_ms: float = 0.0

    @field_validator("tile_x", "tile_y")
    @classmethod
    def validate_tile_coordinates(cls, value: int) -> int:
        if value < -2 or value > 2:
            raise ValueError("tile coordinates must stay within MVP 5x5 bounds [-2, 2]")
        return value

    @field_validator("width", "height", "interaction_radius")
    @classmethod
    def validate_positive_geometry(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("geometry dimensions must be positive")
        return value

    @field_validator("interaction_cooldown_ms")
    @classmethod
    def validate_non_negative_cooldown(cls, value: float) -> float:
        if value < 0:
            raise ValueError("interaction cooldown must not be negative")
        return value

    @field_validator("object_type")
    @classmethod
    def validate_object_type(cls, value: str) -> str:
        if not is_valid_object_type(value):
            raise ValueError(f"unknown object type: {value}")
        return value

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value is not None and value not in COLOR_PRESETS:
            raise ValueError(f"unknown color preset: {value}")
        return value

    @field_validator("material")
    @classmethod
    def validate_material(cls, value: str | None) -> str | None:
        if value is not None and value not in MATERIAL_PRESETS:
            raise ValueError(f"unknown material preset: {value}")
        return value


class ContentPayloadModel(BaseModel):
    resource_id: str = Field(min_length=1, max_length=64)
    resource_type: str = Field(min_length=1, max_length=40)
    content_type: Literal["inline", "markdown", "external", "video", "audio"]
    title: str = Field(min_length=1, max_length=120)
    body: str | None = None
    source_url: str | None = None

    @model_validator(mode="after")
    def validate_content_source(self) -> "ContentPayloadModel":
        if self.content_type in {"external", "video", "audio"} and not self.source_url:
            raise ValueError("source_url is required for non-inline content types")
        return self
