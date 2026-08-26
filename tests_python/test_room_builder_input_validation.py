"""TDD regression tests: room:object:move / resize / rotate must not crash
(or silently corrupt shared room state broadcast to every client) when a
malicious/malformed client sends non-numeric x/y/width/height/rotation.

Unlike `create_object` (which validates through the pydantic
`RoomObjectPlacementModel`), `move_object`, `resize_object`, and
`rotate_object` previously performed zero type validation on their
numeric arguments:
  - `move_object` stored whatever was given verbatim (no exception at all),
    silently corrupting state broadcast to every client in the room.
  - `resize_object` compared `width <= 0` / `height <= 0`, raising an
    uncaught `TypeError` for non-numeric input.
  - `rotate_object` computed `rotation % 360`, raising an uncaught
    `TypeError` for non-numeric input (or, worse, silently reformatting an
    attacker-supplied format string via Python's `%` string-formatting
    operator if `rotation` were a string).
"""
import pytest

from server.game.room_builder import RoomBuilderState


class TestObjectMutationsRejectNonNumericInput:
    def setup_method(self):
        self.builder = RoomBuilderState()
        self.builder.create_object(object_id="o1", object_type="chair", tile=(0, 0), x=10, y=10)

    def test_move_object_rejects_non_numeric_x(self):
        with pytest.raises(ValueError):
            self.builder.move_object("o1", "not-a-number", 10)

    def test_move_object_rejects_non_numeric_y(self):
        with pytest.raises(ValueError):
            self.builder.move_object("o1", 10, "not-a-number")

    def test_move_object_does_not_corrupt_state_on_bad_input(self):
        with pytest.raises(ValueError):
            self.builder.move_object("o1", "not-a-number", 10)
        obj = self.builder.get_object("o1")
        assert obj["x"] == 10  # unchanged, not corrupted with the bad string

    def test_move_object_still_works_with_valid_numeric_input(self):
        moved = self.builder.move_object("o1", 55, 65)
        assert moved["x"] == 55
        assert moved["y"] == 65

    def test_resize_object_rejects_non_numeric_width(self):
        with pytest.raises(ValueError):
            self.builder.resize_object("o1", "not-a-number", 50)

    def test_resize_object_rejects_non_numeric_height(self):
        with pytest.raises(ValueError):
            self.builder.resize_object("o1", 50, "not-a-number")

    def test_resize_object_still_works_with_valid_numeric_input(self):
        resized = self.builder.resize_object("o1", 40, 50)
        assert resized["width"] == 40
        assert resized["height"] == 50

    def test_rotate_object_rejects_non_numeric_rotation(self):
        with pytest.raises(ValueError):
            self.builder.rotate_object("o1", "not-a-number")

    def test_rotate_object_rejects_format_string_rotation(self):
        # Regression guard: a string like "%s" must not be silently accepted
        # and run through Python's `%` string-formatting operator.
        with pytest.raises(ValueError):
            self.builder.rotate_object("o1", "%s")

    def test_rotate_object_still_works_with_valid_numeric_input(self):
        rotated = self.builder.rotate_object("o1", 400)
        assert rotated["rotation"] == 40
