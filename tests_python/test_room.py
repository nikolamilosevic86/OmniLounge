from server.game.avatar import create_default_avatar
from server.game.chat import create_message
from server.game.room import Room


class TestRoom:
    def setup_method(self):
        self.room = Room("lobby")

    def test_add_and_remove_player(self):
        self.room.add_player("p1", create_default_avatar("Alice"))
        assert self.room.get_player_count() == 1
        self.room.remove_player("p1")
        assert self.room.get_player_count() == 0

    def test_update_position(self):
        self.room.add_player("p1", create_default_avatar("Alice"))
        updated = self.room.update_player_position("p1", {"x": 200, "y": 150})
        assert updated["position"]["x"] == 200

    def test_set_direction_clears_target(self):
        self.room.add_player("p1", create_default_avatar("Alice"))
        self.room.set_player_target("p1", {"x": 500, "y": 400})
        self.room.set_player_direction("p1", {"x": 1, "y": 0})
        player = self.room.get_player("p1")
        assert player["targetPosition"] is None
        assert player["direction"]["x"] == 1

    def test_active_bubbles(self):
        self.room.add_player("p1", create_default_avatar("Alice"))
        msg = create_message(sender_id="p1", sender_name="Alice", text="Bubble", type="public")
        self.room.add_message(msg)
        bubbles = self.room.get_active_bubbles("p2")
        assert len(bubbles) == 1
        assert bubbles[0]["text"] == "Bubble"

    def test_private_bubble_visibility(self):
        self.room.add_player("p1", create_default_avatar("Alice"))
        self.room.add_player("p2", create_default_avatar("Bob"))
        self.room.add_message(create_message(
            sender_id="p1", sender_name="Alice", text="Secret", type="private", recipient_id="p2"
        ))
        assert len(self.room.get_active_bubbles("p3")) == 0
        assert len(self.room.get_active_bubbles("p2")) == 1
