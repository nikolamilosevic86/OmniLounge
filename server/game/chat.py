import time
from typing import Any
from uuid import uuid4

_message_counter = 0


def create_message(
    *,
    sender_id: str,
    sender_name: str,
    text: str,
    type: str,
    recipient_id: str | None = None,
) -> dict[str, Any]:
    global _message_counter
    _message_counter += 1
    return {
        "id": f"msg_{_message_counter}_{uuid4().hex[:8]}",
        "senderId": sender_id,
        "senderName": sender_name,
        "text": text,
        "type": type,
        "recipientId": recipient_id,
        "timestamp": int(time.time() * 1000),
    }


def should_show_bubble(message: dict[str, Any], viewer_id: str) -> bool:
    if message["type"] == "public":
        return True
    if message["type"] == "private":
        return message["senderId"] == viewer_id or message.get("recipientId") == viewer_id
    return False


def get_visible_messages(messages: list[dict[str, Any]], user_id: str) -> list[dict[str, Any]]:
    return [msg for msg in messages if should_show_bubble(msg, user_id)]


def filter_messages_for_user(messages: list[dict[str, Any]], user_id: str) -> list[dict[str, Any]]:
    return get_visible_messages(messages, user_id)
