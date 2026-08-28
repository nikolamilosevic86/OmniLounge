import pytest

from server.game.inventory import InventoryEngine


class TestGrantAndHas:
    def test_has_defaults_to_false(self):
        engine = InventoryEngine()
        assert engine.has("u1", "brass-key") is False

    def test_grant_then_has_is_true(self):
        engine = InventoryEngine()
        engine.grant("u1", "brass-key")
        assert engine.has("u1", "brass-key") is True

    def test_grant_is_idempotent(self):
        engine = InventoryEngine()
        engine.grant("u1", "brass-key")
        engine.grant("u1", "brass-key")
        assert engine.list_items("u1") == ["brass-key"]

    def test_grants_are_isolated_per_user(self):
        engine = InventoryEngine()
        engine.grant("u1", "brass-key")
        assert engine.has("u2", "brass-key") is False
        assert engine.list_items("u2") == []


class TestListItems:
    def test_unknown_user_returns_empty_list(self):
        engine = InventoryEngine()
        assert engine.list_items("nobody") == []

    def test_returns_all_granted_items_sorted(self):
        engine = InventoryEngine()
        engine.grant("u1", "silver-coin")
        engine.grant("u1", "brass-key")
        assert engine.list_items("u1") == ["brass-key", "silver-coin"]


class TestRevokeAllForObject:
    def test_removes_item_from_every_user(self):
        engine = InventoryEngine()
        engine.grant("u1", "brass-key")
        engine.grant("u2", "brass-key")
        engine.revoke_all_for_object("brass-key")
        assert engine.has("u1", "brass-key") is False
        assert engine.has("u2", "brass-key") is False

    def test_does_not_affect_other_items(self):
        engine = InventoryEngine()
        engine.grant("u1", "brass-key")
        engine.grant("u1", "silver-coin")
        engine.revoke_all_for_object("brass-key")
        assert engine.list_items("u1") == ["silver-coin"]

    def test_revoking_ungranted_item_is_a_no_op(self):
        engine = InventoryEngine()
        engine.revoke_all_for_object("never-granted")  # must not raise
        assert engine.list_items("u1") == []
