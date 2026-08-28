# Escape Room Feature Design

## 1. Product Intent

This feature turns any OmniLaunge room into a cooperative escape room: a creator places furniture, hidden items, locked doors, and AI characters as they already do today, then layers puzzle logic on top so a group of visitors must *solve their way to a hidden key* before a locked door will open. It is designed as an authoring layer on top of the existing room builder, tile graph, object catalog, story-character, zone, and trigger systems — not a parallel system. Section 3 maps every new escape-room concept to the existing engine it extends.

This also directly serves the educational use cases already documented in the top-level [README.md](../README.md) ("Escape rooms and puzzle-based learning") and in [docs/08-ai-characters.md](../docs/08-ai-characters.md) (AI characters as puzzle-holders/hint-givers): a teacher can build a history-themed locked room where the "key" is only found after learners correctly answer three checkpoints seeded through the room's existing knowledge-base and story-node systems.

All new client-facing UI introduced by this feature — the builder panel, HUD, and every modal/overlay — is a **Material 3 (M3) implementation with no exceptions**; it must use the app's existing `--md-*` design tokens and shared `.builder-*`/`.kb-*`/`.dialogue-*` component classes rather than any bespoke styling. This is not a stylistic preference but a hard requirement carried over from the app's existing single design-system convention (the whole builder UI, including the just-unified Knowledge Store panel, is M3-native — see [docs/08-ai-characters.md](../docs/08-ai-characters.md)); §10 spells out exactly which tokens and classes each new UI piece must reuse and gives a compliance checklist.

## 2. Research: How Escape Rooms Actually Work

This section summarizes commonly documented, genre-standard escape room mechanics (physical escape room industry and "escape-the-room" video games) so the design below reuses proven patterns rather than inventing new ones.

### 2.1 Structural pattern common to virtually all escape rooms
- **Briefing** — a short intro (video, audio, live host, or in our case an on-screen card/AI character) sets the theme and the goal before the clock starts.
- **Timer** — a visible countdown (typically 45–60 minutes physically; shorter for casual/digital formats) creates urgency and defines "win" vs "time's up."
- **Puzzle chain, not a single puzzle** — players explore, find clues, and solve a *sequence* of puzzles that unlock access to new items, containers, or areas. Puzzles are rarely solvable in isolation; solving one typically reveals or unlocks the next (a "linear chain" or a "hub-and-spoke" structure where several independent puzzles must all be solved before a final combined step).
- **Puzzle variety** — the genre-standard toolbox includes: word/number puzzles (ciphers, riddles, math), pattern-arranging puzzles (sequences, sorting, matching symbols), search-based puzzles (finding a hidden physical object in the environment), combination locks unlocked by a code assembled from clues found elsewhere in the room, and knowledge checks that require correctly recalling information encountered earlier in the room.
- **No outside expertise required** — a well-designed puzzle never assumes players already know something; any specialized fact needed to solve it must be discoverable inside the room itself. This is a hard design constraint we carry into the authoring guidance below.
- **Hint system with a cost** — most rooms let a stuck team ask for a hint (via a live "game master," a phone, or an in-room terminal), but hints usually cost something — a time penalty, a limited hint budget, or both — so a team is incentivized to keep trying before asking.
- **Win/lose framing** — teams "win" by finishing inside the time limit and "lose" (with a "good ending" experience regardless, per genre best practice) if the timer runs out; some rooms show a distinct narrative outcome for each case rather than just a bare pass/fail.
- **Leaderboards** — many rooms track and display the fastest completion times, which drives replay and competition among groups.

### 2.2 Patterns from digital / virtual-space implementations
Digital escape-the-room games and social virtual spaces (browser point-and-click escape games, and puzzle-gated doors in tools like virtual office/event platforms) reinforce a few translatable patterns:
- **Inventory of collected items** — a player "picks up" an item (a key, a tool, a note) into a small visible inventory, then "uses" it on another object (a locked door, a chest) to progress. This is the mechanic this design adds as the escape room's core primitive.
- **State-gated interactions** — an object's available actions change based on world state (a locked door only offers "It's locked" until a flag flips to unlocked), rather than the object itself being replaced.
- **Environmental storytelling over walls of text** — clues are attached to the same objects/characters already in the room (a book on a shelf, a character's dialogue, a note pinned to a wall) instead of a separate "puzzle UI" bolted onto the world, which matches this codebase's existing "behavior emerges from place" design principle (see [docs/02-room-interactions.md](../docs/02-room-interactions.md)).

### 2.3 Design principles carried into this feature
1. Reuse room objects and AI characters as puzzle carriers; do not invent a separate "puzzle world."
2. The **answer to a puzzle must never be sent to the client** — only the server may know whether a submitted guess is correct (see §9's security notes).
3. Hints cost something (a hint counter and/or a time penalty), mirroring the genre standard.
4. A room has one authored **goal**: reach the hidden key, then use it (or a solved combination) to open a specific locked door. Everything else is in service of that goal.
5. Every puzzle must be solvable using only information available inside the room (documents, character dialogue, videos, objects) — this is an authoring guideline surfaced directly in the builder UI, not a server-enforced rule.

## 3. Reuse Map: What Already Exists vs What Is New

| Escape-room concept | Existing system it reuses | What's new |
| --- | --- | --- |
| Placing puzzle props, doors, keys in a room | `RoomBuilderState.create_object` / `room_object_catalog.py` (Phase D/E object model) | Two new catalog entries: `escape_door`, `hidden_item` (§5) |
| A puzzle "trigger area" (step on the rug, approach the desk) | Existing zone (`collision`/`interaction`) + trigger (`evaluate_area_enter`) system in `room_builder.py` | A third zone-adjacent use: triggers can now emit a `reveal_object` event type (§6.3) |
| A puzzle that's really a question with a right/wrong answer | `StoryEngine` node graph (`characterLine`, `choices`, **`completion_flag`**, **`knowledge_check`** — both fields already exist in `story.py`/`StoryNodeModel` but are currently unused hooks) | Wire `knowledge_check` to actually gate progress (§6.4); add a free-text-answer story node variant |
| A character that gives a clue or a hint | `ai_character`'s knowledge base + the **already-defined but unimplemented `ask_hint` interaction** (`OBJECT_TYPE_CATALOG["ai_character"]["interactions"]`, stubbed in `room_builder.py: _interaction_payload`) | Real hint-budget logic behind `ask_hint` (§6.5) |
| A locked door that only opens once conditions are met | `RoomBuilderState.set_locked` / `isLocked` exists, but currently means "locked *from editing*," not "locked as a game obstacle" | A distinct, **per-visitor gameplay lock** state, tracked independently of the existing builder edit-lock (§3.1, §5.1) |
| Carrying a found key between puzzles | Nothing exists yet | New per-user **Inventory** concept (§7), modeled after `StoryEngine`'s existing per-user progress dict pattern |
| A room-wide countdown and win/fail state | Nothing exists yet | New **EscapeSessionEngine** (§8), following the same in-memory, pure, unit-testable engine pattern as `GuideEngine`/`StoryEngine`/`MediaLibrary` |
| Fastest-completion leaderboard | `RoomBuilderState` versioning already tracks ordered history (`_versions`, `save_draft`/`publish`) as a precedent for append-only in-memory history | New `_attempts` list on `EscapeSessionEngine` (§8.4) |
| Multi-room puzzle sequences ("solve room 1, walk through the door into room 2") | The 5×5 tile grid and `tile_navigation.can_add_neighbor_tile` (documented in [educational_rooms_feature_design.md](educational_rooms_feature_design.md) §6) already support multi-tile rooms | `escape_door.destinationTile` reuses this instead of inventing new spatial logic (§5.1) |
| Object collision (a locked door blocks movement like any other object) | `movement.py: resolve_collision` + `server/main.py: _tile_collision_obstacles`, which already turns every builder-placed object into a solid AABB obstacle | Small addition — `_tile_collision_obstacles` gains a `requester_id` parameter (it is already invoked once per player per movement tick, so the caller already has this value) so an opened `escape_door` stops blocking only the specific visitor who opened it (§3.1, §5.1) |
| Room edit permissions for who can author puzzles | `RoomBuilderState._require_edit_permission` / `editPermission: owner_only \| anyone` per object | No change — puzzle authoring uses the same permission check as every other object edit |

This table is the core argument for the design: **escape rooms are not a new subsystem — they are a small, bounded set of additions layered onto systems that already exist and are already tested.**

### 3.1 Consistency Rule: Per-User Progress by Default

Every piece of *live* escape-room progress — which puzzles are solved, which hidden items are revealed, which doors are open, and how much time is left — defaults to **per-visitor, private state**, not shared room-wide state. This mirrors a separation the codebase already relies on: `StoryEngine` keeps authored node *definitions* (`_nodes`) completely separate from per-`(object_id, character_id, user_id)` *progress* (`_progress`), so two visitors can be at different points in the same character's conversation simultaneously. Escape rooms need the identical separation for the same reason: OmniLaunge rooms are persistent, ambient spaces (per [docs/01-user-experience.md](../docs/01-user-experience.md)) that many unrelated visitors can drop into at any time, not a single booked session for one team. Concretely:

- **Puzzle-solved state** is tracked per `(puzzle_id, user_id)`, not globally per puzzle (§6.1).
- **Hidden-item-revealed state** is tracked per `(object_id, user_id)`, not as a single shared flag on the object (§5.2, §8.1).
- **Door-open state** is tracked per `(object_id, user_id)`, so a door one visitor has unlocked keeps blocking every other visitor who hasn't solved it themselves (§5.1, §8.1).
- **The countdown timer** is already per-user by design (§8.1).

Without this rule, the first visitor to reach the door would silently unlock it — and reveal every hidden item — for every other concurrent visitor too, letting them walk straight through with zero puzzle-solving. Defaulting to private per-user state avoids that failure mode entirely and lets any number of people attempt the same room independently and concurrently, same as they'd each independently start a guided tour or a story conversation today. A room-host-togglable **Team/Shared Mode**, where a group intentionally pools progress the way a physical escape room team does, is scoped to Phase 2 (§14) rather than being the default.

## 4. End-to-End Experience Walkthrough

### 4.1 Creator (authoring) flow
1. Creator builds a room as normal: tiles, furniture, an AI character, a bookshelf, a TV — using the existing builder panels.
2. Creator opens the new **"Escape Room" builder panel** (parallel to the existing "AI Character" panel) and flips **Enable Escape Mode** on for the room. This exposes a time limit field (minutes) and a short briefing text field (shown to visitors before the timer starts).
3. Creator places a **Locked Door** object (new catalog type `escape_door`) somewhere in the room — the literal exit — and configures what unlocks it: a specific **key item id**, a list of **puzzle ids** that must all be solved first, or both together (the door only opens once every configured condition is satisfied — see the exact unlock formula in §5.1).
4. Creator places one or more **Hidden Item** objects (new catalog type `hidden_item`, invisible and non-interactable to every visitor until they personally reveal it — see §3.1/§5.2) representing the eventual key, and optionally decoy items.
5. Creator authors **puzzles** in the same panel: each puzzle has a prompt, an answer (never exposed to clients), a list of hint strings, and a **reward** — typically "reveal this hidden item" or "unlock this door directly." A puzzle can be presented through:
   - A **puzzle panel object** (new interaction on any object, e.g. a desk or a locked chest) where a visitor types a free-text or numeric answer.
   - An existing **AI character's story node**, using the already-defined-but-unused `knowledge_check` field to gate that node's next choice on a correct answer instead of always advancing.
   - An **area trigger** (existing zone/trigger system) that auto-reveals a clue once a visitor walks to the right spot — no typed answer needed, matching the "search-based puzzle" genre pattern from §2.1.
6. Creator wires up hints: for the AI character, they just use the already-existing "Ask Hint" menu action, which the creator gives content by attaching hint text to whichever puzzle that character is guarding.
7. Creator plays their own room in "Play Mode" (existing build/play toggle) to validate the chain before publishing.

### 4.2 Visitor (player) flow
1. Visitor joins the room and sees a **briefing card** ("You have 20 minutes to find the archivist's key and escape the vault.") with a **Start** button. The timer does not start until a visitor (or the room host) starts it, so idle browsing before commitment doesn't burn the clock.
2. A persistent HUD shows the countdown and a small **inventory strip** (icons for held items).
3. Visitor explores, talks to characters, reads books, watches videos, and interacts with puzzle objects exactly as they already do for any interactive object — using the existing radial interaction menu.
4. Solving a puzzle either reveals a hidden item for that visitor (which now renders in the room and becomes interactable — "Pick Up") or reports success and unlocks the door directly for them (§3.1).
5. Visitor picks up the key item; it moves into their personal inventory.
6. Visitor approaches the locked door and interacts with it. If they hold the required key (or all required puzzles are solved), the door opens: it stops blocking movement, and if the creator configured a `destinationTile`, the visitor transitions there (reusing the existing tile-edge-transition system) — otherwise the room is marked **escaped** for that visitor.
7. If the timer expires first, the visitor sees a "time's up" outcome card, matching the genre's "good ending / bad ending regardless of success" principle from §2.1 — nothing is lost except the win, and the room stays explorable.
8. Optionally, the room's leaderboard shows the fastest completion times for anyone who has escaped that room.

## 5. New / Extended Object Catalog Entries

Both entries live in `server/game/room_object_catalog.py` next to the existing seven types, following the exact same `OBJECT_TYPE_CATALOG` shape.

### 5.1 `escape_door`
```python
"escape_door": {
    "category": "interactive",
    "defaultSizePreset": "M",
    "interactions": [
        {"interactionType": "attempt_open", "label": "Try the Door", "actionState": None},
    ],
},
```
Config fields (stored in the existing per-object `config` dict, same mechanism `bookshelf`/`tv`/`music_player` already use for object-specific data). Per §3.1, this `config` dict only holds the **authored blueprint** for the door — it never holds live per-visitor open/closed state:
- `requiredItemId: str | None` — an inventory item id that must be held to open it.
- `requiredPuzzleIds: list[str]` — puzzle ids that must all be in a "solved" state.
- `destinationTile: {"x": int, "y": int} | None` — reuses the existing tile-graph coordinate model; if set, a successful open transitions the visitor there via the same mechanism as a normal edge crossing; if omitted, opening it marks that visitor's escape attempt as **won** (subject to the expiry rule in §8.3).

**Unlock formula** (evaluated per requesting visitor, never room-wide): a door opens for visitor `user_id` when
```
(requiredItemId is None or inventory.has(user_id, requiredItemId))
and all(puzzles.is_solved(pid, user_id) for pid in requiredPuzzleIds)
```
This is a strict **AND** across both conditions — an author configuring both a required item and required puzzles means a visitor needs *all* of them, not just one. If neither field is set, the door has no gate and opens unconditionally on first attempt (useful for a final "free exit" door with no further puzzle). This is the same logic §4.1 step 3 refers back to.

**Multiple win-doors are OR-gated, not AND-gated.** `mark_won` (§8.1/§8.3) fires the first time *any* `escape_door` with no `destinationTile` opens for a visitor; it is idempotent and safe to call again if the visitor later opens a second such door. A room with several independent "final" doors therefore lets a visitor win via whichever one they reach first — they are alternate/redundant exits, not a checklist that must all be opened. A creator who wants a *staged* goal ("open door A, which leads to a second room containing door B, the real exit") must chain them with `destinationTile` rather than placing multiple unconfigured win-doors in the same room, since only a door that actually lacks a `destinationTile` counts as a win trigger.

Gameplay-lock vs edit-lock: `escape_door` deliberately does **not** reuse `RoomBuilderState.isLocked`/`set_locked`, because that field already means "an editor cannot move/delete/resize this object" (`_require_unlocked` in `delete_object`/move/resize handlers). Overloading it would mean an author's escape door became un-editable the moment gameplay locked it, or (worse) a player "unlocking" it during play would accidentally grant editors the ability to move it. A door's open/closed state is therefore tracked entirely outside the object record, in `EscapeSessionEngine` (§8.1), keyed per `(object_id, user_id)` — the same kind of external, per-user-keyed runtime state `StoryEngine._progress` already keeps separate from its own node definitions (§3.1).

Collision: an `escape_door` a given visitor has not yet opened remains a solid AABB obstacle for that visitor, exactly like any other object — `server/main.py: _tile_collision_obstacles` already turns every object in `RoomBuilderState.list_objects` into a blocking box with no per-type special-casing needed. Per §3.1, this function gains a `requester_id` parameter (it is already called once per player per movement tick from inside `apply_player_movement`, so the caller already has this value on hand) and skips only `escape_door` objects where `escape_session.has_opened(requester_id, object_id)` is `True` — so the door keeps blocking every other visitor who hasn't opened it themselves. This is the one behavioral change to an existing function; every other object type is completely unaffected.

### 5.2 `hidden_item`
```python
"hidden_item": {
    "category": "interactive",
    "defaultSizePreset": "S",
    "interactions": [
        {"interactionType": "pick_up", "label": "Pick Up", "actionState": None},
    ],
},
```
Config fields — again, only the authored blueprint, per §3.1:
- `itemKind: "key" | "tool" | "note"` — cosmetic/inventory-icon hint only.
- `singleUse: bool` — whether, once a visitor has picked the item up, it stops appearing as pick-up-able for that same visitor again (default `True`; the common case for a key). Because reveal/held state is already per-visitor (below), this only prevents a single visitor from re-collecting the same item, not a room-wide disappearance.

Whether the item is currently revealed is **not** stored on the object at all — it is per-visitor runtime state on `EscapeSessionEngine` (§8.1), exactly like `escape_door`'s open state. A hidden item is revealed for visitor `user_id` via `escape_session.reveal_item(user_id, object_id)`, settable from three places, matching §4.1's three puzzle-authoring paths: a solved puzzle's reward, a fired area trigger's `reveal_object` payload (§6.3), or a story node's `knowledge_check` success branch (§6.4).

**Once picked up, an item leaves that visitor's world view.** After `InventoryEngine.grant` succeeds (§7), the item is granted but must not keep appearing as a loose, pick-up-able object in that same visitor's room view — otherwise it would look duplicated (once lying on the floor, once in the HUD strip). `list_objects_for_tiles`'s per-visitor filter (below) therefore also omits any `hidden_item` the requesting visitor already holds (`inventory.has(requester_id, object_id)`), in addition to omitting ones they haven't revealed yet; the item remains fully visible to other visitors who have separately revealed their own copy of the puzzle chain, since reveal/hold state never crosses between visitors (§3.1).

**Server-side visibility, not client-side hiding.** An unrevealed `hidden_item` must never be sent to a visitor's client at all — not even with a "don't render this" flag — because a visitor could otherwise discover its exact position by inspecting network traffic before solving anything, defeating the entire puzzle. `RoomBuilderState.list_objects_for_tiles` (and `list_objects`) therefore gain a `requester_id`/`is_room_host` pair of parameters: for a normal play-mode visitor, any `hidden_item` not yet revealed for that `requester_id`, or already picked up by them, is omitted from the returned list entirely; for `is_room_host` (build-mode/editor) calls, every `hidden_item` is always included (shown with a distinct "hidden until revealed" badge in the builder UI, §10) so authors can find and edit it. This is the same never-trust-the-client discipline already applied to puzzle answers (§6.1) and AI character API keys (`StoryEngine._public_character`).

### 5.3 Object Deletion Cleanup

`RoomBuilderState.delete_object` already special-cases `ai_character` deletion, calling both `self._guide.discard(object_id)` and `self._story.remove_character(object_id, object_id)` so a deleted character's runtime state doesn't linger. This feature extends that same cleanup step, following the identical "delete the object, then let every engine that might reference it discard its own records" pattern, rather than a new deletion pathway:

- Deleting a **`hidden_item`**: call `self._inventory.revoke_all_for_object(object_id)` (§7) so nobody keeps a phantom key for an item that no longer exists, and clear any `reveal_item`/`has_revealed` entries for that `object_id` on `EscapeSessionEngine` (§8.1) for every visitor.
- Deleting an **`escape_door`**: clear any `open_door`/`has_opened` entries for that `object_id` on `EscapeSessionEngine` for every visitor, and if the door was the sole win condition for the room, no special handling is needed beyond that — a visitor who already won keeps their recorded leaderboard entry (§8.4), since `record_attempt` has already fired and is not retroactively undone by a later edit.
- Deleting **any object with a bound `config.get("puzzleId")`** (§6.2): if no other object still references that `puzzle_id`, call `self._puzzles.remove_puzzle(puzzle_id)` so a dangling puzzle definition doesn't accumulate; if another object (or an `ai_character`'s `guardsPuzzleId`, §6.5) still references the same `puzzle_id`, the puzzle definition is left intact.

## 6. Puzzle Authoring Paths (reusing existing systems)

### 6.1 New `PuzzleEngine` domain module
A new, small, pure module `server/game/puzzle.py`, matching the existing style of `GuideEngine`/`BookshelfLibrary`/`MediaLibrary` (plain dict-backed state, no I/O, fully unit-testable without sockets or a DB):

```python
class PuzzleEngine:
    def __init__(self) -> None:
        self._puzzles: dict[str, dict[str, Any]] = {}   # puzzle_id -> definition (prompt, answer, hints, ...)
        self._solved_by: dict[str, set[str]] = {}        # puzzle_id -> set of user_ids who solved it (per §3.1)
        self._hints_used: dict[tuple[str, str], int] = {}  # (puzzle_id, user_id) -> hints requested so far
        self._attempt_limiter = SlidingWindowRateLimiter(...)  # reuse server/game/rate_limiter.py

    def add_puzzle(self, puzzle_id, prompt, answer, hints: list[str], reveal_item_id=None,
                   unlock_door_id=None, match_mode="exact", max_attempts: int | None = None) -> dict: ...
    def remove_puzzle(self, puzzle_id) -> bool: ...
    def get_puzzle_public(self, puzzle_id) -> dict:  # never includes `answer`
    def attempt_solve(self, puzzle_id, user_id, guess: str, now_ms: float) -> dict:
        # returns {"correct": bool, "attemptsRemaining": int | None, "alreadySolved": bool, "locked": bool}
        # rate-limited per (puzzle_id, user_id) to blunt brute-forcing short codes; once a user's
        # per-puzzle attempt count reaches max_attempts, further guesses return locked=True until
        # a room host calls reset_attempts (below) -- see the lockout note after this block
    def reset_attempts(self, puzzle_id, user_id) -> None:
        # edit-permission-gated (room:puzzle:reset); clears a locked-out user's attempt count only,
        # never their solved state, so a solved puzzle can never be "un-solved" by a reset
    def is_solved(self, puzzle_id, user_id) -> bool:
        # always evaluated for a specific visitor (per §3.1) -- Phase 2 Team Mode is the only path
        # that treats "solved by anyone on the team" as equivalent to "solved by this user" (§14)
    def request_hint(self, puzzle_id, user_id, now_ms: float) -> dict:
        # returns {"hint": str | None, "hintsUsed": int, "hintsRemaining": int}
```
Answer comparison is case-insensitive and whitespace-trimmed by default (`match_mode: "exact" | "numeric" | "contains"` on the puzzle covers riddles vs number-lock codes vs keyword-search answers, mirroring the puzzle-type variety in §2.1). The **answer field is only ever read server-side**; `get_puzzle_public` is the only representation ever serialized to a client, exactly the same discipline `StoryEngine._public_character` already applies to strip `apiKey` before any client-facing response (see [docs/08-ai-characters.md](../docs/08-ai-characters.md)).

**Attempt lockout.** A puzzle configured with `max_attempts` stops accepting guesses from a user once they exhaust it (`attempt_solve` returns `locked: True` instead of checking the guess); only a room editor can clear that lockout for that one visitor via `reset_attempts` / the `room:puzzle:reset` event (§9), so a locked-out visitor cannot brute-force further but also isn't permanently blocked without recourse.

**Reconciling `reveal_item_id`/`unlock_door_id` with the door's own `requiredPuzzleIds`.** A puzzle's `reveal_item_id`/`unlock_door_id` and a door's `requiredPuzzleIds` describe the *same* authored relationship from opposite ends, which could drift out of sync if set independently. To avoid that, these are never edited as two separate raw fields: the builder's puzzle-authoring panel's "reward" picker (§4.1 step 5) is the single UI action that sets both sides atomically — choosing "reveal this hidden item" as a puzzle's reward sets the puzzle's `reveal_item_id` and nothing further is needed on the item itself (reveal is driven purely by `reveal_item_id`, not by any field stored on the `hidden_item`); choosing "unlock this door" sets the puzzle's `unlock_door_id` *and* appends this puzzle's id into that door's `requiredPuzzleIds` server-side in the same call. `requiredPuzzleIds` on the door remains the single source of truth `attempt_open` actually evaluates (§5.1); `unlock_door_id` on the puzzle is purely a convenience back-reference the builder UI uses to show "this puzzle unlocks: Vault Door" without a separate lookup.

This atomic, two-sided wiring cannot live inside `PuzzleEngine.add_puzzle` itself, since `PuzzleEngine` has no reference to room objects and must not reach into `RoomBuilderState._objects` to stay a small, independently-testable module (mirroring how `GuideEngine`/`StoryEngine` never touch `_objects` directly either). Instead, `RoomBuilderState` gains a thin orchestrator method, `add_puzzle(...)`, that calls `self._puzzles.add_puzzle(...)` and then, only if `unlock_door_id` is supplied, appends the new puzzle id into `self._objects[unlock_door_id]["config"]["requiredPuzzleIds"]` directly. This is the same "engine owns its own state, `RoomBuilderState` owns cross-engine orchestration" division of responsibility already established by `create_object`'s auto-provisioning of a `StoryEngine` character for every new `ai_character` and by `configure_character`'s upsert logic (§1).

`RoomBuilderState` owns one `PuzzleEngine` instance per room (`self._puzzles = PuzzleEngine()` in `__init__`, next to `self._story`/`self._guide`), the same ownership pattern already used for every other per-room engine.

### 6.2 Puzzle panel interaction (typed-answer puzzles)
Rather than inventing a tenth object type, any existing interactive object gains an optional puzzle binding: a `puzzleId` field in its `config`. When present, a new generic interaction `solve_puzzle` (added to `bookshelf`, `table`, or any object type a creator wants to double as a puzzle prop — e.g. a "desk" is just a `table` with a bound puzzle) opens a small answer-input modal client-side and calls `room:puzzle:attempt` with the typed guess.

This requires one small change to how interaction menus are built: today `get_interaction_menu(object_type)` (and the `_decorate_object` step that attaches its result to every object) is purely a function of `objectType` — it has no way to add an interaction only some instances of a type should offer. Object decoration must therefore append `{"interactionType": "solve_puzzle", "label": "Solve", "actionState": None}` onto the menu returned for a specific object *only when that object's own `config.get("puzzleId")` is set*, in addition to (not instead of) its type's static catalog menu. This is a small, localized change inside `_decorate_object`, not a change to the catalog itself — every object type keeps exactly the static menu it has today unless it's also been bound to a puzzle.

### 6.3 Trigger-revealed puzzles (search-based / environmental)
`RoomBuilderState.evaluate_area_enter` already fires trigger payloads keyed by `eventType`, and it is already called per-player (`evaluate_area_enter(player_id, tile, x, y, now_ms)`), so it already carries the visiting player's identity needed for a per-user reveal. This design adds one new recognized `eventType`: `"reveal_object"`, with `payload: {"objectId": "<hidden_item id>"}`. No change to the trigger *engine* is required — `evaluate_area_enter`'s cooldown/repeatable/fired-once semantics already fully cover "reveal this the first time someone steps on this rug," and since fired-state is already tracked per `(player_id, trigger_id)`, per-user reveal (§3.1) falls out for free. The only new code is the handler in `server/main.py` that, on a fired `reveal_object` trigger, calls the new `escape_session.reveal_item(player_id, object_id)` method (§8.1) and broadcasts the updated object list to that one player — the same targeted-broadcast pattern already used for `room:npc:moved` (§8.2) rather than a full-room rebroadcast, since the reveal is only meaningful to the player who triggered it.

### 6.4 Story-character knowledge checks (character-guarded puzzles)
`StoryNodeModel.knowledge_check` and `completion_flag` already exist in `server/game/story.py` but `StoryEngine.talk`/`advance` never reads them — they are currently write-only metadata. This design activates them: when a node has `knowledge_check` set to a `puzzle_id`, `StoryEngine.talk` (called from `room:character:talk`) consults the room's `PuzzleEngine.is_solved(puzzle_id, user_id)` before allowing the choice that leads past that node; if unsolved, the character's line branches to a "you need to figure that out first" response instead of the configured next node. This lets a creator build a character who simply won't hand over a hint or the next chapter of the story until the visitor has actually solved something — the "quiz master" role already listed in `ALLOWED_ROLES` finally has a concrete mechanical purpose.

### 6.5 Hint system via the existing `ask_hint` interaction
`ai_character`'s interaction menu already advertises `"ask_hint"` (`{"interactionType": "ask_hint", "label": "Ask Hint", ...}`), and `room_builder.py: _interaction_payload` already has a matching `if interaction_type == "ask_hint":` branch — today it just returns the character record with no hint content. This design fills in that branch: an `ai_character` gets an optional `guardsPuzzleId` config field; `ask_hint` then calls `PuzzleEngine.request_hint(guardsPuzzleId, requester_id, now_ms)` and returns the next hint string (if any remain) alongside the character payload. This reuses 100% of the existing interaction plumbing, cooldown handling (`interactionCooldownMs` already exists per-object and is a natural fit for "you can only ask this character for a hint once every N seconds"), and dialogue-modal UI — the only new code is what the stub branch returns.

## 7. Inventory

A new, small, per-room, per-user structure — deliberately not a generalized item/economy system, since nothing else in the product needs one yet. Per §3.1, held items are always private to the visitor who picked them up:

```python
class InventoryEngine:  # server/game/inventory.py
    def __init__(self) -> None:
        self._held: dict[str, set[str]] = {}  # user_id -> set of item object ids

    def grant(self, user_id: str, item_object_id: str) -> None: ...
    def has(self, user_id: str, item_object_id: str) -> bool: ...
    def list_items(self, user_id: str) -> list[str]: ...
    def revoke_all_for_object(self, item_object_id: str) -> None:  # object deleted mid-game, all users
```
This mirrors the `dict[str, set[...]]`-per-user-key shape already used by `StoryEngine._progress` (keyed by `(object_id, character_id, user_id)`) and `BookshelfLibrary`'s reading-progress map, so it fits the codebase's existing idiom rather than introducing a new persistence style. `interact_with_object`'s `pick_up` branch on `hidden_item` requires `escape_session.has_revealed(requester_id, object_id)` to be `True` (§5.2, §8.1) — a visitor cannot pick up an item they haven't personally uncovered yet — then calls `self._inventory.grant(requester_id, object_id)`. Because reveal/hold state is per-visitor throughout, one visitor picking up an item never affects what any other visitor sees or can pick up; the client simply adds it to that one visitor's HUD inventory strip.

## 8. Escape Session (timer, win/lose, leaderboard)

### 8.1 `EscapeSessionEngine` (`server/game/escape_session.py`)
One instance per room, owned by `RoomBuilderState` exactly like `PuzzleEngine`/`InventoryEngine`:

```python
class EscapeSessionEngine:
    def __init__(self) -> None:
        self._attempts: list[dict] = []  # ordered leaderboard entries, appended by record_attempt (§3, §8.4)

    def configure(self, enabled: bool, time_limit_ms: float, briefing: str | None) -> None: ...
    def start(self, user_id: str, now_ms: float) -> dict:
        # per-user attempt clock; a no-op returning the current status if already in_progress,
        # so a visitor double-clicking Start (or reconnecting mid-session) can never reset their
        # own clock back to full time (§16 Q2 covers the separate, explicit reset flow below)
    def status(self, user_id: str, now_ms: float) -> dict:
        # {"state": "not_started"|"in_progress"|"won"|"expired", "remainingMs": float}
    def mark_won(self, user_id: str, display_name: str, now_ms: float) -> dict:
        # called once, when the visitor's session transitions in_progress -> won (i.e. the last
        # required escape_door opens for them); computes elapsed_ms from this session's own
        # start_ms and calls record_attempt itself, so callers never separately compute elapsed
        # time or forget to record a leaderboard entry
    def record_attempt(self, user_id: str, display_name: str, elapsed_ms: float) -> None:
        # invoked only from mark_won; appended to an ordered leaderboard list, same
        # append-then-sort pattern as RoomBuilderState._versions
    def leaderboard(self, limit: int = 10) -> list[dict]: ...
    def reset(self, user_id: str) -> None:
        # clears this visitor's timer plus every per-visitor flag below (reveal/open state);
        # only callable when that visitor's own state is "not_started" or "expired" -- resetting
        # an "in_progress" session is rejected (PermissionError) so a visitor can never use reset
        # to dodge a bad guess's rate limit or claim a fresh leaderboard run mid-attempt (§9, §16 Q2)

    # Per-visitor live progress (§3.1) -- kept here, alongside the timer, rather than on the
    # objects themselves, mirroring StoryEngine's separation of node definitions from _progress:
    def reveal_item(self, user_id: str, object_id: str) -> None: ...
    def has_revealed(self, user_id: str, object_id: str) -> bool: ...
    def open_door(self, user_id: str, object_id: str) -> None: ...
    def has_opened(self, user_id: str, object_id: str) -> bool: ...
```
Per-user (not room-wide) timers are the default because OmniLaunge rooms are persistent, ambient multiplayer spaces (per [docs/01-user-experience.md](../docs/01-user-experience.md)) rather than a booked, synchronized physical session — a visitor who joins mid-session should not inherit someone else's countdown, revealed items, or opened doors (§3.1). A room-host-configurable **Team/Shared Mode** — where the timer, solved puzzles, revealed items, and opened doors are all pooled room-wide instead of per-visitor, matching the classic synchronized physical-escape-room-team experience — is scoped to Phase 2 (§14) rather than being the MVP default.

### 8.2 Game-loop tick
`server/main.py`'s existing `game_loop()` already ticks per-room, per-frame concerns (see `tick_guided_tours`). A new `tick_escape_sessions(room_id, now_ms)` follows the exact same shape: for each in-progress session past its `time_limit_ms`, transition it to `expired` and emit a lightweight `room:escape:expired` event to that user only — mirroring how `room:npc:moved` is a targeted, lightweight event rather than a full state rebroadcast.

### 8.3 Winning
When `escape_door`'s `attempt_open` interaction succeeds for a visitor (per the unlock formula in §5.1), `RoomBuilderState` calls `self._escape.open_door(requester_id, object_id)` (§8.1) so the door stops blocking that visitor from now on, then: if `destinationTile` is unset, calls `mark_won(requester_id, display_name, now_ms)` (the visitor's already-known display name, the same one every other room-presence event already carries — no new lookup required) and that single call both marks the win and records the leaderboard entry (§8.1); if `destinationTile` is set instead, the visitor also transitions tiles via the existing tile-crossing path, and the room is "escaped" as a bonus rather than the sole win condition — supporting the "escape door leads to the next themed room" chained-rooms pattern from §4.2 without any new spatial code.

**Expiry does not retroactively block opening, but it does block winning.** Per the genre principle in §2.1 that a room stays explorable after time runs out, a visitor whose session has already transitioned to `expired` may still solve puzzles and open doors — nothing about gameplay is hard-gated by the timer. However, `mark_won` is only ever called while that visitor's session state is `in_progress`; if it is already `expired`, opening the final door still unlocks it mechanically (so the visitor isn't stuck) but does not transition to `won` and does not record a leaderboard entry. Puzzle attempts, hint requests, and item pickups are likewise never blocked by session state (`not_started`/`expired`) — the timer only gates leaderboard eligibility, not the ability to keep playing.

### 8.4 Leaderboard
Purely additive: an ordered list of `{displayName, elapsedMs, completedAtMs}`, exposed read-only via `room:escape:leaderboard:list`. In-memory for MVP (matches every other engine in this codebase, all of which are in-memory pending the Phase A persistence work already tracked in [educational_rooms_feature_design.md](educational_rooms_feature_design.md) §16); persisting it is a natural, low-risk Phase 2 add-on once/if a `room_versions`-style table is extended.

## 9. Event Contract Additions

Following the exact naming and payload conventions of the existing `room:character:*` family documented in [docs/08-ai-characters.md](../docs/08-ai-characters.md):

| Event | Direction | Purpose |
| --- | --- | --- |
| `room:escape:configure` | client → server | Enable/disable escape mode, set time limit + briefing text (edit-permission gated, room-host style) |
| `room:escape:start` | client → server | Visitor starts their own countdown |
| `room:escape:status` | client → server | Poll current state/remaining time (also pushed proactively on join) |
| `room:escape:expired` | server → client | Game-loop tick informs a visitor their time ran out |
| `room:escape:won` | server → client | Broadcast (to the winner, and optionally room-wide as a celebratory toast that omits any spoiler detail) when that visitor opens their winning door |
| `room:escape:leaderboard:list` | client → server | Fetch top completion times |
| `room:escape:reset` | client → server | Self-serve retry: clears the requester's own timer, solved puzzles, revealed items, and opened doors, per `EscapeSessionEngine.reset` (§8.1). Rejected with `PermissionError` while that visitor's state is `in_progress`, so it can only be used after finishing (`won`) or timing out (`expired`), never mid-attempt |
| `room:puzzle:add` / `:remove` / `:list` | client → server | Author puzzles (edit-permission gated) |
| `room:puzzle:attempt` | client → server | Submit a guess; returns `{correct, attemptsRemaining, alreadySolved, locked}` — **never** the answer |
| `room:puzzle:hint` | client → server | Same shape as `room:character:ask`'s rate-limited pattern; returns the next hint string |
| `room:puzzle:reset` | client → server | Edit-permission gated; clears one visitor's exhausted attempt count for a puzzle without clearing their solved state (§6.1) |
| `room:door:configure` | client → server | Set `requiredItemId`/`requiredPuzzleIds`/`destinationTile` on an `escape_door` (edit-permission gated) |
| `room:item:configure` | client → server | Set `itemKind`/`singleUse` on a `hidden_item` (edit-permission gated) — the item-side counterpart to `room:door:configure`, following the same per-object-type "Configure" event convention already used for bookshelf/tv/music_player |
| `room:door:attempt_open` | client → server | Also reachable via the generic `room:object:interact` with `interactionType: "attempt_open"`, consistent with every other object's interaction dispatch |
| `room:item:pick_up` | client → server | Also reachable via `room:object:interact` with `interactionType: "pick_up"`, same as above |
| `room:inventory:list` | client → server | Fetch the requester's current held items for the HUD |

All of these follow the already-established handler skeleton in `server/main.py` (`room_id, _tile, builder = _current_room_and_builder(sid)` → guard → `try/except (KeyError, PermissionError, ValueError)` → `emit("error", ...)` → `broadcast_builder_state` where relevant), so no new error-handling pattern needs to be introduced.

## 10. Client UI Additions — Material 3 Compliance Required

**Every new UI surface in this feature must be built entirely with the app's existing Material 3 design system — no new colors, shapes, fonts, or one-off component styles.** OmniLaunge standardized its entire client on M3 tokens and shared component classes (defined in [client/css/styles.css](../client/css/styles.css)'s `:root` token block), and the most recent UI work in this codebase was specifically a cleanup that *removed* a divergent, hand-rolled "IBM Carbon" design system from the Knowledge Store panel and replaced it with M3-native classes (documented in [docs/08-ai-characters.md](../docs/08-ai-characters.md)). This feature must not reintroduce that kind of drift. Concretely:

### 10.1 Tokens every new style must use
- **Color roles** — `--md-primary`/`--md-on-primary`, `--md-surface-container` through `--md-surface-container-highest`, `--md-outline`/`--md-outline-variant`, `--md-error`/`--md-on-error`/`--md-error-container` (for a failed guess or a locked-out puzzle), `--md-success`/`--md-on-success`/`--md-success-container` (for a correct guess, a revealed item, or the win card), and `--md-warning`/`--md-on-warning-container` (for a low-time HUD warning state). No new hex colors are introduced anywhere in this feature.
- **Shape** — `--md-shape-sm`/`--md-shape-md` for inputs and chips, `--md-shape-lg`/`--md-shape-xl` for modals/cards, `--md-shape-full` for the countdown timer chip and inventory icon slots (pill/circle shapes), matching the existing HUD chip shapes.
- **Elevation** — `--md-elevation-2`/`--md-elevation-3` for the puzzle modal and briefing/win/expired overlays, the same tier already used by tooltips and dialogue modals.
- **Motion** — `--md-easing-standard`/`--md-easing-emphasized` with `--md-duration-short`/`--md-duration-medium` for the timer chip's low-time pulse, the inventory strip's item-added animation, and modal enter/exit transitions — no custom easing curves or durations.

### 10.2 Components every new UI piece must reuse (not reinvent)
- **Builder panel**: a new "Escape Room" section in the existing builder sidebar (parallel to "AI Character," see [client/index.html](../client/index.html)'s `#configure-character-section`), built entirely from the existing `.builder-field` (label + input/select/textarea, including the `textarea` selector fix already applied — §10.4), `.builder-primary-btn`/secondary action button classes, `.builder-object-list` (for the puzzle list, add/edit/remove rows), and `.builder-error`/`.builder-error.hidden` for validation messages (e.g., "a puzzle needs at least one hint") — the exact same classes the AI Character and Knowledge Store panels already use, so the Escape Room panel is visually indistinguishable in style from its neighbors.
- **Door/Item authoring**: the required item/puzzle dropdown for doors and the reveal-condition summary for items reuse the existing per-object-type "Configure" section pattern (`.builder-field` rows) already used for bookshelf/tv/music_player/ai_character — no new config-panel layout is introduced.
- **Player HUD**: the countdown timer chip and inventory strip reuse the existing HUD chip component (rounded `--md-shape-full` pill, `--md-surface-container-high` background, `--md-elevation-1`) already seen in the tile/build-mode HUD chips (see the screenshot in [README.md](../README.md)) — not a new chip style. The low-time warning state reskins the same chip with `--md-warning`/`--md-on-warning-container` rather than introducing a new "alert chip" component.
- **Puzzle modal**: reuses the existing dialogue-modal shell (`.dialogue-action-row` and its surrounding modal container) already used for AI character conversations, with a single `.builder-field` text input, a `.builder-primary-btn` Submit button, and a secondary-style "Ask for a Hint" action using the same secondary-button treatment `.builder-primary-btn`'s sibling class already defines (see the styles.css comment: "Secondary builder action: same shape as `.builder-primary-btn` but visually...").
- **Briefing / win / expired cards**: full-panel overlays reusing the existing modal/overlay shell already used for the room-chooser and dialogue modals — same scrim (`--md-scrim`), same elevation tier, same corner radius (`--md-shape-xl`) — not a new overlay system. The win card uses `--md-success-container`/`--md-on-success-container` as its accent; the expired card uses `--md-surface-container`/`--md-on-surface-variant` (a neutral, non-punitive tone, consistent with §2.1's "good ending regardless" principle) rather than `--md-error`, since running out of time is not a failure state the design wants to visually punish.
- **Puzzle-bound object badge / hidden-item build-mode badge**: small inline badges (e.g., "Puzzle: date-riddle", "Hidden until revealed") reuse the same small-pill badge treatment already established for object state indicators in the builder (`--md-shape-full`, `--md-surface-container-highest`, `--md-on-surface-variant` text) rather than a new badge component.

### 10.3 Explicit non-goals
- No new font stack, weight scale, or type-ramp values outside the ones already defined for the builder UI.
- No new color literals (hex/rgb) anywhere in new CSS — every color is a `var(--md-*)` reference, matching the same rule already enforced when the Knowledge Store panel's IBM Plex/blue-60 Carbon styling was removed.
- No third-party UI/component library — every new element is composed from existing `.builder-*`/`.dialogue-*`/`.kb-*` classes and raw HTML, exactly like every other builder panel today.
- No divergent light/dark handling — new components must resolve correctly under both existing theme blocks the same way `.builder-field`/`.kb-panel` already do, since `--md-*` tokens are redefined per theme rather than hardcoded.

### 10.4 Compliance checklist (to be verified during Phase 1 implementation and code review)
1. Every new CSS rule added for this feature only references `var(--md-*)` custom properties for color, shape, elevation, and motion — grep for raw hex codes (`#[0-9a-fA-F]{3,6}`) in the new stylesheet additions and confirm zero matches outside the existing token block.
2. Every new builder-panel field is a `.builder-field` wrapping an `input`/`select`/`textarea` — re-verify the `textarea` selector is present in any rule these new fields depend on (the exact bug this repo already hit once with the Knowledge Store panel's story/choice/document textareas, per [docs/08-ai-characters.md](../docs/08-ai-characters.md)).
3. Every new modal/overlay reuses the existing dialogue-modal or room-chooser overlay shell rather than a new `<div>`-and-inline-style construction.
4. Every new HUD element matches the existing HUD chip's shape, elevation, and sizing so the countdown/inventory strip reads as part of the same HUD family as existing chips, not a bolted-on widget.
5. The feature is visually reviewed in both light and dark theme blocks before merging, since `--md-*` tokens differ between them.

## 11. Worked Example: "The Locked Archive" (educational template)

To ground the design in the educational use case from the README, a concrete authored example:
1. Room theme: a history archive. Briefing: "The archive door has sealed itself. Find the librarian's key before the vault reseals in 15 minutes."
2. An `ai_character` "Archivist" (role `quiz_master`) has a knowledge base pre-loaded with three short historical facts (existing knowledge-document system). Its story graph has a `knowledge_check` node gated on puzzle `date-riddle`.
3. A `bookshelf` holds a "clue" book whose content contains the fact needed to answer `date-riddle` (reuses the existing reading system — no new content type).
4. A `table` object is bound to `puzzle: date-riddle` (numeric match mode) — visitors read the book, talk to the Archivist to confirm their understanding, then interact with the table to submit the year.
5. Solving `date-riddle` reveals a `hidden_item` ("Brass Key") elsewhere in the room via the puzzle's `reveal_item_id` (§6.1) — for that visitor only (§3.1); a second visitor exploring the same room concurrently would need to solve their own copy of `date-riddle` before their own key appears.
6. An `escape_door` requires that key. Opening it has no `destinationTile` set, so opening it is the win condition and ends that visitor's timer, per §8.3.
7. A leaderboard on the room's info panel shows the fastest three visitors to find the key, each independently timed from when they pressed Start (§8.1).

This example uses **zero new content types** — book, character, table, and door are all either pre-existing or the two new catalog entries from §5.

## 12. Security and Anti-Cheat Considerations

- **Answers never leave the server.** `PuzzleEngine.get_puzzle_public` strips `answer`, matching the existing `StoryEngine._public_character` discipline of never returning `apiKey`.
- **Rate-limit guesses.** `attempt_solve` uses the existing `SlidingWindowRateLimiter` (already used for generative AI calls) per `(puzzle_id, user_id)`, so a short numeric code cannot be brute-forced by an automated script.
- **Server-authoritative reveal/unlock state.** Per-visitor reveal and open flags are only ever flipped by server-side puzzle/trigger/door logic calling `EscapeSessionEngine.reveal_item`/`open_door` (§8.1), never by a raw client-sent field — the same validated-input discipline already enforced by `RoomObjectPlacementModel` and the "reject non-numeric input" bug-fix history visible in this repo's commit log.
- **Edit-permission-gated authoring, learner-open gameplay.** Adding/editing puzzles and doors requires the same `_require_edit_permission` check as every other object edit; *attempting* a puzzle or door is intentionally open to any room visitor, mirroring the existing precedent that *starting a guided tour* is not permission-gated even though *authoring* one is (see [docs/08-ai-characters.md](../docs/08-ai-characters.md) §"Guided tours").
- **No SSRF/URL surface added.** This feature introduces no new external URL fields, so `is_safe_external_url` is not implicated — puzzles are pure text/number matching.
- **Unrevealed items are never transmitted, not just unrendered.** As in §5.2, an undiscovered `hidden_item`'s position and existence are withheld server-side (filtered out of `list_objects_for_tiles` for that visitor) rather than sent to the client with a "please don't draw this" flag, which would leak its location to anyone inspecting network traffic.
- **Per-visitor isolation prevents griefing and spoilers alike.** Because solved-puzzle, revealed-item, and opened-door state are all keyed per user (§3.1), one visitor cannot lock another out of a puzzle via attempt-lockout, spoil another visitor's hidden item by revealing it first, or let another visitor walk through a door they didn't personally earn.

## 13. Data Model Additions (for the eventual persistence phase)

Following the existing style in `server/db/schema.sql` (the current schema already anticipates `story_nodes`, `room_objects`, etc. as Phase A foundations even though most runtime state today is in-memory per §16 of [educational_rooms_feature_design.md](educational_rooms_feature_design.md)):

```sql
CREATE TABLE IF NOT EXISTS room_puzzles (
    id               VARCHAR PRIMARY KEY,
    room_id          VARCHAR NOT NULL REFERENCES rooms(id),
    prompt           TEXT NOT NULL,
    match_mode       VARCHAR NOT NULL DEFAULT 'exact',  -- 'exact' | 'numeric' | 'contains'
    answer_hash      VARCHAR,               -- normalized-answer hash; set when match_mode is 'exact' or 'numeric'
    answer_encrypted VARCHAR,               -- app-key-encrypted (reversible) plaintext; set when match_mode is 'contains'
    hints            JSONB NOT NULL DEFAULT '[]',
    reveal_item_id   VARCHAR,
    unlock_door_id   VARCHAR,
    max_attempts     INT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
**Why two answer columns.** `"exact"`/`"numeric"` matching only ever needs to compare a normalized guess against a known normalized answer, so a one-way hash (the same discipline already used for password-style secrets) is sufficient and preferable — the plaintext answer never needs to be recovered. `"contains"` matching (a keyword that must appear somewhere inside a longer free-text guess, per §6.1's `match_mode` options) fundamentally requires the plaintext answer at check time, since there is no way to test "does this hash appear as a substring of that guess" without already knowing the substring — so `"contains"` puzzles store an application-key-encrypted (reversible), not hashed, answer instead. Exactly one of `answer_hash`/`answer_encrypted` is populated per row, determined by `match_mode`; this is validated in `PuzzleEngine.add_puzzle` before persistence, not left as an unenforced convention. In-memory (`PuzzleEngine._puzzles`, pre-persistence), the plaintext answer is simply held in process memory the same way any other in-memory engine state is today — only the eventual persisted row needs this hash-vs-encrypt distinction.

```sql
CREATE TABLE IF NOT EXISTS room_escape_attempts (
    id             VARCHAR PRIMARY KEY,
    room_id        VARCHAR NOT NULL REFERENCES rooms(id),
    user_id        VARCHAR NOT NULL,
    display_name   VARCHAR NOT NULL,
    elapsed_ms     BIGINT NOT NULL,
    completed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Per-visitor live progress (§3.1): which puzzles/items/doors this user has personally solved,
-- revealed, or opened in this room. Mirrors the existing per-(object,user) shape of
-- `reading_progress` rather than introducing a new persistence idiom.
CREATE TABLE IF NOT EXISTS room_escape_progress (
    room_id             VARCHAR NOT NULL REFERENCES rooms(id),
    user_id             VARCHAR NOT NULL,
    solved_puzzle_ids   JSONB NOT NULL DEFAULT '[]',
    revealed_item_ids   JSONB NOT NULL DEFAULT '[]',
    opened_door_ids     JSONB NOT NULL DEFAULT '[]',
    hints_used          JSONB NOT NULL DEFAULT '{}',
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (room_id, user_id)
);
```
`room_objects.config` (already a JSON/JSONB config column per the existing schema pattern used by bookshelf/tv/music_player) absorbs `escape_door`/`hidden_item` *authored blueprint* fields with no schema change needed there; only the new `room_escape_progress` table above is needed for the *live per-visitor* state described in §3.1.

## 14. Implementation Plan (Tracked Checklist)

This section is the authoritative, trackable task breakdown for building this feature. Check items off as they land; each item names the concrete artifact it produces and the design section that specifies it, so progress can be verified against the spec rather than against a vague phase name. Sub-items must be completed in order within each group where a dependency exists (e.g., an engine before the handlers that call it, handlers before the UI that calls them).

### Phase 1 (MVP)

**Domain engines (server/game/)**
- [x] `server/game/puzzle.py`: `PuzzleEngine` with `add_puzzle`, `remove_puzzle`, `get_puzzle_public`, `attempt_solve` (rate-limited via the existing `SlidingWindowRateLimiter`), `reset_attempts`, `is_solved`, `request_hint` (§6.1). Built TDD-first; see [tests_python/test_puzzle.py](../tests_python/test_puzzle.py) (37 tests).
- [x] `server/game/inventory.py`: `InventoryEngine` with `grant`, `has`, `list_items`, `revoke_all_for_object` (§7). Built TDD-first; see [tests_python/test_inventory.py](../tests_python/test_inventory.py) (9 tests).
- [x] `server/game/escape_session.py`: `EscapeSessionEngine` with `configure`, `start` (idempotent no-op if already `in_progress`), `status`, `mark_won` (internally calls `record_attempt`), `record_attempt`, `leaderboard`, `reset` (rejects while `in_progress`), `reveal_item`/`has_revealed`, `open_door`/`has_opened` (§8.1). Also adds `expire_overdue_sessions(now_ms)` (an internal helper not listed in the §8.1 skeleton, needed to implement the §8.2 game-loop tick without mutating state inside the otherwise-pure `status` read). Built TDD-first; see [tests_python/test_escape_session.py](../tests_python/test_escape_session.py) (24 tests).
- [x] Wire all three engines into `RoomBuilderState.__init__` (`self._puzzles`, `self._inventory`, `self._escape`), following the existing `self._story`/`self._guide` ownership pattern.
- [x] `RoomBuilderState.add_puzzle(...)` orchestrator: calls `PuzzleEngine.add_puzzle`, then atomically appends the new puzzle id to the target door's `requiredPuzzleIds` when `unlock_door_id` is set (§6.1). Validates `unlock_door_id` exists before creating the puzzle so a bad reference never leaves a dangling puzzle. See `TestAddPuzzleOrchestrator` in [tests_python/test_room_builder.py](../tests_python/test_room_builder.py).
- [x] `RoomBuilderState.attempt_solve_puzzle` now auto-reveals the puzzle's `reveal_item_id` (via `self._escape.reveal_item`) the moment a guess is correct, matching §6.1's "reveal is driven purely by `reveal_item_id`" -- this had been a silent gap where the orchestrator only forwarded to `PuzzleEngine.attempt_solve` with no reveal side effect at all. See `TestAttemptSolvePuzzleRevealsRewardItem`.
- [x] Room-wide (non-object-bound) escape/puzzle authoring methods -- `configure_escape_session`, `add_puzzle`, `remove_puzzle`, `reset_puzzle_attempts` -- gained `requester_id`/`is_room_host` parameters gated by a new `_require_room_host` helper (`if requester_id is not None and not is_room_host: raise PermissionError`), since none of them has a single owning object record for the existing `_require_edit_permission` check to run against. Mirrors the existing room-host-only gate already used by `configure_character_generative_mode`. `requester_id=None` keeps trusted/internal callers (existing tests, migrations) working unchanged. See `TestPuzzleAuthoringWrappers`, `TestEscapeSessionWrappers`.
- [x] New `RoomBuilderState` wrapper methods: `remove_puzzle`, `list_puzzles`, `request_puzzle_hint`, `reset_puzzle_attempts`, `escape_leaderboard`, `reset_escape_session`, `list_inventory`, `expire_escape_sessions`, `configure_door`, `configure_item` -- each a thin pass-through to the corresponding engine, following the exact shape of pre-existing wrappers like `configure_character`/`set_object_style`. `configure_door`/`configure_item` are object-scoped (`_require_object` + `_require_edit_permission`, same pattern as `configure_character`). `_is_visible_to` was also extended to respect a `hidden_item`'s new `config.singleUse` field (default `True`): a `singleUse=False` item remains visible/re-collectible for a visitor even after they've picked it up, whereas the previous behavior unconditionally hid any already-held item. See `TestConfigureDoorAndItem`, `TestEscapeSessionWrappers`.
- [x] Object-deletion cleanup in `delete_object`: revoke inventory grants for a deleted `hidden_item`, clear reveal/open state for a deleted `hidden_item`/`escape_door`, and remove an orphaned puzzle definition when its last referencing object is deleted (§5.3). `EscapeSessionEngine` gained `clear_revealed_for_object`/`clear_opened_for_object` helpers (TDD'd in `test_escape_session.py`) to support this. See `TestEscapeRoomDeletionCleanup`.

**Catalog and collision**
- [x] `escape_door` and `hidden_item` entries added to `OBJECT_TYPE_CATALOG` in `room_object_catalog.py` (§5.1, §5.2).
- [x] `_tile_collision_obstacles` gains a `requester_id` parameter and skips `escape_door` objects the requester has personally opened (§5.1). Threaded from `apply_player_movement`'s `player.get("id")` (the socket sid, matching the `requester_id=sid` convention used elsewhere in `main.py`). Delegates to a new thin `RoomBuilderState.has_opened_door(object_id, requester_id)` wrapper rather than reaching into the private `_escape` engine directly, matching the "main.py only calls public `RoomBuilderState` methods" convention. See `TestHasOpenedDoorWrapper` in `test_room_builder.py` and `TestEscapeDoorCollisionIsPerVisitor` in [tests_python/test_main_movement.py](../tests_python/test_main_movement.py).
- [x] `list_objects_for_tiles`/`list_objects` gain `requester_id`/`is_room_host` parameters and omit unrevealed-or-already-held `hidden_item` objects for ordinary visitors (§5.2). Backward compatible: omitting `requester_id` (existing call sites) keeps showing everything, matching the existing "no requester means trusted" convention `_can_edit` already uses. See `TestHiddenItemVisibility`.
- [x] `_decorate_object` appends the `solve_puzzle` interaction only for the specific object instances whose `config.get("puzzleId")` is set (§6.2). `interact_with_object`'s menu validation was also switched from the static per-type catalog menu to this dynamic per-instance menu, since it previously would have rejected `solve_puzzle` as "unsupported" even though `_decorate_object` advertised it. See `TestSolvePuzzleInteraction`.

**Socket event handlers (server/main.py)**
- [x] `room:escape:configure`, `room:escape:start`, `room:escape:status`, `room:escape:won` (server → client), `room:escape:expired` (server → client), `room:escape:reset`, `room:escape:leaderboard:list` (§9). `room:escape:won` is emitted from `room_object_interact` right after a fresh, non-`alreadyOpen`, no-`destinationTile` door open, gated on `get_escape_status(...)["state"] == "won"` (since `mark_won` is a no-op unless the visitor's session was `in_progress`) -- privately to the winner and room-wide (`skip_sid`) as the celebratory toast described in §9. See `TestEscapeSessionHandlers`, `TestObjectInteractEmitsWinEvent` in [tests_python/test_main_escape_room.py](../tests_python/test_main_escape_room.py).
- [x] `room:puzzle:add`, `room:puzzle:remove`, `room:puzzle:list`, `room:puzzle:attempt`, `room:puzzle:hint`, `room:puzzle:reset` (§9). See `TestPuzzleHandlers`.
- [x] `room:door:configure`, `room:item:configure`, `room:inventory:list` (§9). See `TestDoorItemConfigureAndInventory`.
- [x] `attempt_open`/`pick_up` wired into the existing generic `room:object:interact` dispatch (§9). No `server/main.py` change was needed for this specific item: that handler already dispatches any `interactionType` through `RoomBuilderState.interact_with_object` with no per-object-type allowlist, so implementing the `escape_door`/`hidden_item` branches inside `_interaction_payload` (see `TestEscapeDoorInteraction`, `TestHiddenItemInteraction`) made them reachable end-to-end for free. `interact_with_object` gained an optional `display_name` parameter (defaults to `requester_id` when not supplied) so `mark_won` has a display name to record on the leaderboard; the remaining `room:main.py` handlers below still need to pass the visitor's real display name through once that plumbing exists.
- [x] `tick_escape_sessions(room_id, now_ms)` added to the existing `game_loop()` right after `tick_guided_tours`, mirroring its per-room, try/except-wrapped shape (a broken tick logs and returns instead of killing the shared loop), and emitting a targeted `room:escape:expired` to each expired visitor's own `sid` room (the same `room=<sid>` targeting already used for private chat messages) (§8.2). See `TestTickEscapeSessions`.

**Client UI — Material 3 only (§10)**
- [x] Builder "Escape Room" panel section (enable toggle, time limit, briefing, puzzle list) using `.builder-field`/`.builder-primary-btn`/`.builder-object-list`/`.builder-error` (§10.2). HTML in [client/index.html](../client/index.html)'s `#escape-room-section`; wired in [client/js/main.js](../client/js/main.js) (`escapeSettingsSaveBtn`, `puzzleAddBtn`/`puzzleListEl`, `escapeLeaderboardBtn`).
- [x] Door/item "Configure" sub-panels reusing the existing per-object-type config pattern (§10.2). `#configure-escape-door-section`/`#configure-item-section` in `client/index.html`; `renderEscapeDoorSelect`/`renderHiddenItemSelect`/`renderEscapeDoorFields`/`renderItemFields` and the `configByType` dispatch entries in `client/js/main.js`.
- [x] Player HUD countdown chip + inventory strip reusing the existing HUD chip component, including the `--md-warning`/`--md-error-container` low-time state (§10.2). `#escape-timer-pill`/`#escape-inventory-pill`; `updateEscapeHud()` (driven by the existing 33ms game loop) in `client/js/main.js`, using `formatCountdown`/`isLowTime` from [src/escape-room.js](../src/escape-room.js).
- [x] Puzzle modal reusing the existing dialogue-modal shell, with a "Solve" and secondary "Ask for a Hint" action (§10.2). `#puzzle-modal` in `client/index.html`; `openPuzzleModal`/`closePuzzleModal` wired to `room:puzzle:attempt`/`room:puzzle:hint` in `client/js/main.js`, feedback text via `puzzleAttemptMessage`.
- [x] Briefing / win / expired overlay cards reusing the existing modal/overlay shell (§10.2). `#escape-briefing-modal`/`#escape-win-modal`/`#escape-expired-modal`; opened from `escapeTimerPill` click (briefing) and the `room:escape:won`/`room:escape:expired` listeners (win/expired) in `client/js/main.js`.
- [x] Build-mode-only "hidden until revealed" badge on `hidden_item` objects (§5.2, §10.2). `.builder-object-chip.hidden-item-badge` rendered in `renderBuilderObjectList()`.
- [x] Run the §10.4 compliance checklist (no raw hex colors, `textarea` selectors present, shared modal shell reused, HUD chip parity, both theme blocks reviewed) before merging. All new CSS additions use only `var(--md-*)` tokens (`--md-error-container`/`--md-on-error-container`, `--md-warning-container`/`--md-on-warning-container`, `--md-success`); no raw hex codes introduced. New modals reuse the existing `.reader-modal`/`.reader-modal-card` shell; new HUD chips reuse `.hud-pill`.

**Tests**
- [x] `tests_python/test_puzzle.py`, `tests_python/test_inventory.py`, `tests_python/test_escape_session.py` — pure-logic unit tests for the three new engines, mirroring the existing `test_npc_guide.py`/`test_story.py` structure, including: per-user isolation (two `user_id`s never see each other's solved/revealed/opened state), the AND unlock formula, attempt lockout + `reset_attempts` recovery, `reset()` rejecting an `in_progress` session, and `mark_won` producing exactly one leaderboard entry per win. (Already noted under "Domain engines" above with per-file test counts; listed here too since this checklist item predates that entry.)
- [x] Handler-level tests in `tests_python/test_main_*` using the existing `FakeSio` harness for every new event in §9, including a rejected `room:escape:reset` while `in_progress` and a permission-denied case for `room:puzzle:add`/`room:door:configure` from a non-editor. See [tests_python/test_main_escape_room.py](../tests_python/test_main_escape_room.py) (17 tests).
- [x] JS-side tests under `tests/` for the new client modules (HUD chip, puzzle modal, inventory strip), matching the existing `tests/*.test.js` structure. See [tests/escape-room.test.js](../tests/escape-room.test.js) (26 tests covering `escapeStatusLabel`/`formatCountdown`/`isLowTime`/`puzzleAttemptMessage`/`formatLeaderboardEntry`/`doorAttemptMessage`, the pure-logic helpers backing the HUD chip, puzzle modal feedback, and leaderboard rendering) and the `builder-objects.test.js` additions for the `escape_door`/`hidden_item` icon mappings.

### Phase 2
- [x] Trigger-revealed puzzles: `reveal_object` event type on `evaluate_area_enter` (§6.3). **Scope note:** `evaluate_area_enter` existed but had zero callers anywhere in `server/main.py` — the scripted trigger editor (create/delete/list) was fully authorable but never actually fired during live gameplay, a pre-existing gap predating this design doc (`§6.3`'s premise that "the trigger engine already fires during gameplay" did not hold). Fixed by threading an optional `fired_triggers` output list through `apply_player_movement` (§5.1's collision `requester_id` pattern), evaluated via a new `_evaluate_area_triggers` helper after every position update. `server/main.py: game_loop` collects fired triggers per tick and hands each to a new `handle_fired_trigger(room_id, fired)`, which echoes a generic `room:trigger:fired` event to that visitor and, for `reveal_object`, calls the new `RoomBuilderState.reveal_item` accessor then pushes a personalized `room:builder:state` refresh (targeted broadcast, matching `room:npc:moved`). See `TestAreaEnterTriggersFireDuringMovement` in [tests_python/test_main_movement.py](../tests_python/test_main_movement.py), `TestHandleFiredTrigger` in [tests_python/test_main_escape_room.py](../tests_python/test_main_escape_room.py), and `TestRevealItemAccessor` in [tests_python/test_room_builder.py](../tests_python/test_room_builder.py).
- [ ] `StoryEngine.talk`/`advance` reads `knowledge_check`/`completion_flag` and consults `PuzzleEngine.is_solved` before allowing gated progression (§6.4).
- [x] `room_builder.py: _interaction_payload`'s existing `ask_hint` stub branch calls `PuzzleEngine.request_hint` for an `ai_character` with `guardsPuzzleId` set and returns the next hint (§6.5). This landed alongside the rest of Phase 1's interaction wiring (this checklist item was left stale/unchecked by mistake). See `TestAskHintGuardsPuzzle` in [tests_python/test_room_builder.py](../tests_python/test_room_builder.py).
- [ ] Leaderboard persistence: `room_puzzles`, `room_escape_attempts`, `room_escape_progress` tables applied via `schema.sql` and read/written from the relevant engines (§13).
- [ ] Multi-door / multi-room chained escape sequences using `destinationTile` (§8.3).
- [ ] **Team/Shared Mode**: room-host toggle pooling the timer, solved puzzles, revealed items, and opened doors room-wide instead of per-visitor (§3.1, §8.1, §16 Q3).
- [ ] Revisit the answer-storage split from §13 (`answer_hash` vs `answer_encrypted`) once persistence lands, including key-rotation handling for encrypted `"contains"`-mode answers.
- [x] **Security fix (found during review, not a pre-existing checklist item):** `server/main.py`'s `room:builder:state` broadcasts (`broadcast_builder_state` and every join/kick/room-change snapshot) never passed `requester_id`/`is_room_host` into `RoomBuilderState.list_objects`/`list_objects_for_tiles`, so despite `_is_visible_to`'s per-visitor hidden_item filtering being correctly implemented and unit-tested at the engine level (`TestHiddenItemVisibility` in `test_room_builder.py`), it was never actually applied over the wire — every connected client received every hidden_item regardless of reveal state, violating the explicit §5.2/§12 security requirement ("unrevealed items are never transmitted, not just unrendered"). Fixed by threading `requester_id`/`is_room_host` through `builder_state_payload` and every call site, and changing `broadcast_builder_state` from a single room-wide emit to a personalized per-player emit (targeted at each player's own sid), mirroring the `room:npc:moved` targeted-broadcast pattern. See `TestHiddenItemVisibilityOverTheWire` in [tests_python/test_main_escape_room.py](../tests_python/test_main_escape_room.py).



### Phase 3
- [ ] Puzzle template library (pre-built riddle/cipher/sequence puzzle types with built-in `match_mode` presets).
- [ ] Attempt analytics (wrong-guess / hint-request frequency per puzzle) to help creators tune difficulty, extending the metrics spirit of §17 of [educational_rooms_feature_design.md](educational_rooms_feature_design.md).
- [ ] Cross-room global leaderboard, contingent on the alignment decision in §16 Q4.

## 15. Risks and Mitigations

- **Risk:** a creator builds an unsolvable room (a puzzle whose required fact is never actually placed anywhere reachable). **Mitigation:** the builder's existing Play Mode (§4.1 step 7) is the validation path; Phase 3's authoring guidance/checklist can also prompt "does every puzzle have a fact source in the room?"
- **Risk:** guess brute-forcing for short numeric codes. **Mitigation:** per-puzzle-per-user rate limiting (§12) and an optional `max_attempts` lockout.
- **Risk:** a hidden item or door is deleted mid-session, orphaning a visitor's in-progress inventory/state. **Mitigation:** `InventoryEngine.revoke_all_for_object` and `PuzzleEngine`/`EscapeSessionEngine` follow the same defensive discard pattern `GuideEngine.discard` already establishes for deleted `ai_character` objects (see `delete_object` in `room_builder.py`).
- **Risk:** per-user timers feel less "team" than genre-standard shared timers. **Mitigation:** explicitly scoped as a Phase 2 opt-in Team/Shared Mode (§3.1, §8.1, §14), not blocking MVP.
- **Risk:** per-visitor progress tracking (solved puzzles, revealed items, opened doors, each keyed per user) could grow unbounded in a very popular room with many one-time visitors. **Mitigation:** bounded the same way object/tile counts already are (`MAX_OBJECTS_PER_TILE`) — a follow-up cap on tracked escape-progress entries per room, plus normal inactive-session eviction, is a Phase 2 operational concern, not a Phase 1 blocker given typical concurrent-visitor counts.

## 16. Alignment Questions for Product Direction

1. Should MVP support only one escape door + one key per room, or multiple independent lock/key pairs from day one? *(Note: nothing in this design actually restricts a room to one door/item pair — any number of `escape_door`/`hidden_item`/puzzle combinations can already coexist, and §5.1 clarifies multiple unconfigured win-doors are OR-gated alternate exits. This question is really about authoring UX complexity — e.g., does the Phase 1 builder panel need a way to group puzzles into named "chains" per door — not a technical limitation.)*
2. Should a failed/expired attempt let a visitor immediately retry (reset their own inventory/puzzle-solved state), or require a room host to reset the room for everyone? *(§8.1/§9 now specify a self-serve `room:escape:reset` for MVP, usable only from `won`/`expired` state; confirm this is the desired default rather than requiring host intervention.)*
3. Is a shared, room-wide "team" timer (everyone in the room shares one clock, matching the physical escape-room genre most closely) a Phase 1 requirement, or is the per-user timer proposed here acceptable for MVP?
4. Should the leaderboard be per-room only, or eventually cross-room (a global "fastest escapes" board) once persistence exists?
5. Do we want a built-in puzzle-type library (cipher, sequence, sudoku, riddle) in Phase 1, or is free-text/numeric answer matching sufficient to start, with templates deferred to Phase 3?
6. Should Team/Shared Mode (§3.1, §14) be pulled forward into Phase 1 if early educational users (classrooms, team-building groups) most commonly want one shared clock/progress per group rather than per individual?
