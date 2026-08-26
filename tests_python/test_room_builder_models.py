import pytest
from pydantic import ValidationError

from server.game.room_builder_models import (
    BoundsModel,
    ContentPayloadModel,
    RoomObjectPlacementModel,
    TileCoordinateModel,
)


def test_tile_coordinate_within_mvp_bounds():
    tile = TileCoordinateModel(tile_x=2, tile_y=-2)
    assert tile.tile_x == 2
    assert tile.tile_y == -2


@pytest.mark.parametrize(
    "tile_x,tile_y",
    [
        (3, 0),
        (-3, 0),
        (0, 3),
        (0, -3),
    ],
)
def test_tile_coordinate_rejects_out_of_bounds(tile_x, tile_y):
    with pytest.raises(ValidationError):
        TileCoordinateModel(tile_x=tile_x, tile_y=tile_y)


def test_room_object_placement_validates_geometry_and_layering():
    obj = RoomObjectPlacementModel(
        object_id="obj-1",
        object_type="bookshelf",
        tile_x=0,
        tile_y=0,
        x=120.0,
        y=240.0,
        width=100.0,
        height=40.0,
        rotation=15.0,
        z_index=5,
        is_locked=False,
        interaction_radius=35.0,
    )
    assert obj.z_index == 5


def test_room_object_placement_rejects_invalid_dimensions():
    with pytest.raises(ValidationError):
        RoomObjectPlacementModel(
            object_id="obj-2",
            object_type="tv",
            tile_x=0,
            tile_y=0,
            x=120.0,
            y=240.0,
            width=0.0,
            height=40.0,
            rotation=0.0,
            z_index=0,
            is_locked=True,
            interaction_radius=20.0,
        )


def test_content_payload_requires_source_for_non_inline_types():
    with pytest.raises(ValidationError):
        ContentPayloadModel(
            resource_id="res-1",
            resource_type="video",
            content_type="external",
            title="Lesson",
            body=None,
            source_url=None,
        )


def test_bounds_model_rejects_inverted_bounds():
    with pytest.raises(ValidationError):
        BoundsModel(min_x=10.0, min_y=20.0, max_x=5.0, max_y=25.0)
