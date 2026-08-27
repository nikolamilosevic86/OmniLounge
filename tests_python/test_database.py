"""Unit tests for server/db/database.py.

The real Database class talks to Postgres via asyncpg. These tests never
touch a real database -- they substitute a fake connection pool so we can
verify the SQL parameter wiring and row->dict mapping without any network
or DB dependency (mirrors the "fake sio, no real network" pattern already
used throughout tests_python/test_main_*.py)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from server.db.database import Database


class FakeAcquireContext:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self._conn = conn
        self.closed = False

    def acquire(self):
        return FakeAcquireContext(self._conn)

    async def close(self):
        self.closed = True


@pytest.fixture
def fake_conn():
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock()
    return conn


@pytest.fixture
def db(fake_conn):
    database = Database()
    database.pool = FakePool(fake_conn)
    return database


class TestConnectDisconnect:
    async def test_connect_creates_pool_via_asyncpg(self, monkeypatch):
        created = {}

        async def fake_create_pool(url, **kwargs):
            created["url"] = url
            created["kwargs"] = kwargs
            return FakePool(MagicMock())

        monkeypatch.setattr("server.db.database.asyncpg.create_pool", fake_create_pool)

        database = Database()
        assert database.pool is None
        await database.connect()

        assert database.pool is not None
        assert created["kwargs"] == {"min_size": 1, "max_size": 10}

    async def test_disconnect_closes_existing_pool(self):
        database = Database()
        fake_pool = FakePool(MagicMock())
        database.pool = fake_pool

        await database.disconnect()

        assert fake_pool.closed is True

    async def test_disconnect_without_a_pool_does_not_raise(self):
        database = Database()
        await database.disconnect()


class TestSaveAvatar:
    async def test_save_avatar_passes_fields_in_correct_order(self, db, fake_conn):
        avatar = {
            "username": "Alice",
            "skinColor": "#ffcc99",
            "gender": "female",
            "hair": "short",
            "beard": "none",
            "glasses": "none",
            "clothes": "casual",
            "accessory": "none",
        }

        await db.save_avatar(avatar)

        fake_conn.execute.assert_awaited_once()
        args = fake_conn.execute.call_args.args
        assert args[1] == "Alice"
        assert args[2] == "#ffcc99"
        assert args[3] == "female"
        assert args[4] == "short"

    async def test_save_avatar_defaults_missing_gender_to_neutral(self, db, fake_conn):
        avatar = {
            "username": "Bob",
            "skinColor": "#ffcc99",
            "hair": "short",
            "beard": "none",
            "glasses": "none",
            "clothes": "casual",
            "accessory": "none",
        }

        await db.save_avatar(avatar)

        args = fake_conn.execute.call_args.args
        assert args[3] == "neutral"


class TestGetAvatar:
    async def test_get_avatar_returns_none_when_no_matching_row(self, db, fake_conn):
        fake_conn.fetchrow.return_value = None

        result = await db.get_avatar("nobody")

        assert result is None

    async def test_get_avatar_maps_row_columns_to_camelcase_dict(self, db, fake_conn):
        fake_conn.fetchrow.return_value = {
            "username": "Alice",
            "skin_color": "#ffcc99",
            "gender": "female",
            "hair": "short",
            "beard": "none",
            "glasses": "none",
            "clothes": "casual",
            "accessory": "none",
        }

        result = await db.get_avatar("Alice")

        assert result == {
            "username": "Alice",
            "skinColor": "#ffcc99",
            "gender": "female",
            "hair": "short",
            "beard": "none",
            "glasses": "none",
            "clothes": "casual",
            "accessory": "none",
        }


class TestSaveMessage:
    async def test_save_message_passes_fields_in_correct_order(self, db, fake_conn):
        message = {
            "id": "m1",
            "senderId": "p1",
            "senderName": "Alice",
            "text": "hi",
            "type": "chat",
            "timestamp": 12345,
        }

        await db.save_message(message, room_id="lobby")

        args = fake_conn.execute.call_args.args
        assert args[1] == "m1"
        assert args[2] == "lobby"
        assert args[3] == "p1"
        assert args[8] == 12345

    async def test_save_message_defaults_room_id_to_lobby(self, db, fake_conn):
        message = {
            "id": "m1",
            "senderId": "p1",
            "senderName": "Alice",
            "text": "hi",
            "type": "chat",
            "timestamp": 12345,
        }

        await db.save_message(message)

        args = fake_conn.execute.call_args.args
        assert args[2] == "lobby"

    async def test_save_message_defaults_missing_recipient_id_to_none(self, db, fake_conn):
        message = {
            "id": "m1",
            "senderId": "p1",
            "senderName": "Alice",
            "text": "hi",
            "type": "whisper",
            "timestamp": 12345,
        }

        await db.save_message(message)

        args = fake_conn.execute.call_args.args
        assert args[7] is None


class TestGetRecentMessages:
    async def test_get_recent_messages_reverses_rows_to_chronological_order(self, db, fake_conn):
        fake_conn.fetch.return_value = [
            {
                "id": "m2", "sender_id": "p1", "sender_name": "Alice",
                "text": "second", "type": "chat", "recipient_id": None,
                "timestamp_ms": 200,
            },
            {
                "id": "m1", "sender_id": "p1", "sender_name": "Alice",
                "text": "first", "type": "chat", "recipient_id": None,
                "timestamp_ms": 100,
            },
        ]

        result = await db.get_recent_messages("lobby", 50)

        assert [m["id"] for m in result] == ["m1", "m2"]
        assert result[0]["text"] == "first"
        assert result[0]["senderId"] == "p1"

    async def test_get_recent_messages_uses_room_id_and_limit_params(self, db, fake_conn):
        fake_conn.fetch.return_value = []

        await db.get_recent_messages("room-42", 5)

        args = fake_conn.fetch.call_args.args
        assert args[1] == "room-42"
        assert args[2] == 5

    async def test_get_recent_messages_returns_empty_list_when_no_rows(self, db, fake_conn):
        fake_conn.fetch.return_value = []

        result = await db.get_recent_messages("lobby")

        assert result == []
