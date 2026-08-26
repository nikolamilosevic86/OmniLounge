"""TDD regression tests for the previously-untested `combat:attack` /
`combat:block` socket handlers in server/main.py.

`combat_attack` forwards the client-supplied `targetId` directly into
`room.get_player(target_id)`, which does `self.players.get(player_id)` --
a raw dict lookup. Python dict lookups require a *hashable* key: a client
sending a JSON array or object as `targetId` (e.g. `{"targetId": [1, 2]}`)
produces an unhashable `list`/`dict` in Python once socket.io decodes the
JSON, and `dict.get(unhashable)` raises an uncaught `TypeError` -- neither
handler had any prior test coverage.
"""
import pytest

import server.main as main_module
from server.game.avatar import create_default_avatar


class FakeSio:
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None]] = []

    async def emit(self, event, data=None, room=None, skip_sid=None):
        self.emitted.append((event, data, room))

    async def enter_room(self, sid, room):
        return None

    async def leave_room(self, sid, room):
        return None


@pytest.fixture(autouse=True)
def isolate_registry(monkeypatch):
    from server.game.rooms_registry import RoomsRegistry

    fresh_rooms = RoomsRegistry()
    monkeypatch.setattr(main_module, "rooms", fresh_rooms)

    fake_sio = FakeSio()
    monkeypatch.setattr(main_module, "sio", fake_sio)

    return fresh_rooms, fake_sio


class TestCombatAttackHandlesMalformedTargetId:
    async def test_valid_attack_still_works(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        rooms.join_room("attacker", create_default_avatar("Alice"), "lobby")
        rooms.join_room("victim", create_default_avatar("Bob"), "lobby")
        room = rooms.get_room("lobby")
        # Put both players adjacent so the range check passes.
        room.get_player("attacker")["position"] = {"x": 100, "y": 100}
        room.get_player("victim")["position"] = {"x": 105, "y": 100}

        await main_module.combat_attack("attacker", {"type": "punch", "targetId": "victim"})

        hit_events = [e for e in fake_sio.emitted if e[0] == "combat:hit"]
        assert hit_events

    async def test_attack_with_unhashable_target_id_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        rooms.join_room("attacker", create_default_avatar("Alice"), "lobby")

        await main_module.combat_attack("attacker", {"type": "punch", "targetId": ["not", "hashable"]})

    async def test_attack_with_dict_target_id_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        rooms.join_room("attacker", create_default_avatar("Alice"), "lobby")

        await main_module.combat_attack("attacker", {"type": "punch", "targetId": {"nested": "dict"}})

    async def test_attack_with_missing_target_id_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        rooms.join_room("attacker", create_default_avatar("Alice"), "lobby")

        await main_module.combat_attack("attacker", {"type": "punch"})

    async def test_attack_with_unknown_attack_type_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        rooms.join_room("attacker", create_default_avatar("Alice"), "lobby")

        await main_module.combat_attack("attacker", {"type": "not-a-real-attack", "targetId": "someone"})


class TestCombatBlockHandlesMalformedInput:
    async def test_valid_block_still_works(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        rooms.join_room("p1", create_default_avatar("Alice"), "lobby")

        await main_module.combat_block("p1", {"blocking": True})

        room = rooms.get_room("lobby")
        assert room.get_player("p1")["blocking"] is True

    async def test_block_with_non_bool_value_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        rooms.join_room("p1", create_default_avatar("Alice"), "lobby")

        await main_module.combat_block("p1", {"blocking": "yes"})
