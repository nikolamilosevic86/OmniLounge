from server.game.chat import (
    create_message,
    filter_messages_for_user,
    get_visible_messages,
    should_show_bubble,
)


class TestChat:
    def test_create_public_message(self):
        msg = create_message(
            sender_id="u1",
            sender_name="Alice",
            text="Hello!",
            type="public",
        )
        assert msg["type"] == "public"
        assert msg["recipientId"] is None

    def test_create_private_message(self):
        msg = create_message(
            sender_id="u1",
            sender_name="Alice",
            text="Secret",
            type="private",
            recipient_id="u2",
        )
        assert msg["recipientId"] == "u2"

    def test_should_show_bubble_public(self):
        msg = create_message(sender_id="u1", sender_name="A", text="Hi", type="public")
        assert should_show_bubble(msg, "u2") is True

    def test_should_show_bubble_private(self):
        msg = create_message(
            sender_id="u1", sender_name="A", text="Secret", type="private", recipient_id="u2"
        )
        assert should_show_bubble(msg, "u1") is True
        assert should_show_bubble(msg, "u2") is True
        assert should_show_bubble(msg, "u3") is False

    def test_get_visible_messages(self):
        messages = [
            create_message(sender_id="u1", sender_name="A", text="Public", type="public"),
            create_message(sender_id="u1", sender_name="A", text="Private", type="private", recipient_id="u2"),
        ]
        assert len(get_visible_messages(messages, "u3")) == 1
        assert len(get_visible_messages(messages, "u2")) == 2

    def test_filter_messages_for_user(self):
        messages = [
            create_message(sender_id="u1", sender_name="A", text="Psst", type="private", recipient_id="u2"),
        ]
        assert len(filter_messages_for_user(messages, "u3")) == 0
