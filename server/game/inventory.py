"""Escape room feature: per-user, per-room inventory of picked-up items.

Pure, in-memory engine (design doc §7), following the same dict-backed
engine pattern as `PuzzleEngine`/`StoryEngine`. Items are identified by the
object_id of the `hidden_item` object that granted them, so "revoke
everything this deleted object ever granted" is a simple lookup by item id
rather than needing a separate source-tracking index.

Inventory is per-user (never room-wide), mirroring the per-user progress
rule in design doc §3.1: two visitors picking up "the same" hidden item in
their own independent playthroughs must not affect each other.
"""


class InventoryEngine:
    """Tracks which item ids each user currently holds."""

    def __init__(self) -> None:
        self._held: dict[str, set[str]] = {}

    def grant(self, user_id: str, item_id: str) -> None:
        self._held.setdefault(user_id, set()).add(item_id)

    def has(self, user_id: str, item_id: str) -> bool:
        return item_id in self._held.get(user_id, set())

    def list_items(self, user_id: str) -> list[str]:
        return sorted(self._held.get(user_id, set()))

    def revoke_all_for_object(self, item_id: str) -> None:
        """Remove `item_id` from every user's inventory. Used when the
        `hidden_item` object that grants this item is deleted, so a
        previously picked-up item doesn't linger as an orphaned inventory
        entry referencing a now-nonexistent object (§5.3)."""
        for held in self._held.values():
            held.discard(item_id)
