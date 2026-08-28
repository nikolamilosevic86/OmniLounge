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

**Server-side visibility, not client-side hiding.** An unrevealed `hidden_item` must never be sent to a visitor's client at all — not even with a "don't render this" flag — because a visitor could otherwise discover its exact position by inspecting network traffic before solving anything, defeating the entire puzzle. `RoomBuilderState.list_objects_for_tiles` (and `list_objects`) therefore gain a `requester_id`/`is_room_host` pair of parameters: for a normal play-mode visitor, any `hidden_item` not yet revealed for that `requester_id` is omitted from the returned list entirely; for `is_room_host` (build-mode/editor) calls, every `hidden_item` is always included (shown with a distinct "hidden until revealed" badge in the builder UI, §10) so authors can find and edit it. This is the same never-trust-the-client discipline already applied to puzzle answers (§6.1) and AI character API keys (`StoryEngine._public_character`).

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
    def configure(self, enabled: bool, time_limit_ms: float, briefing: str | None) -> None: ...
    def start(self, user_id: str, now_ms: float) -> dict:  # per-user attempt clock
    def status(self, user_id: str, now_ms: float) -> dict:
        # {"state": "not_started"|"in_progress"|"won"|"expired", "remainingMs": float}
    def mark_won(self, user_id: str, now_ms: float) -> dict:  # called when the last required escape_door opens
    def record_attempt(self, user_id: str, display_name: str, elapsed_ms: float) -> None:
        # appended to an ordered leaderboard list, same append-then-sort pattern as
        # RoomBuilderState._versions
    def leaderboard(self, limit: int = 10) -> list[dict]: ...

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
When `escape_door`'s `attempt_open` interaction succeeds for a visitor (per the unlock formula in §5.1), `RoomBuilderState` calls `self._escape.open_door(requester_id, object_id)` (§8.1) so the door stops blocking that visitor from now on, then: if `destinationTile` is unset, calls `mark_won(requester_id, now_ms)` and that is the win condition; if set, the visitor also transitions tiles via the existing tile-crossing path, and the room is "escaped" as a bonus rather than the sole win condition — supporting the "escape door leads to the next themed room" chained-rooms pattern from §4.2 without any new spatial code.

**Expiry does not retroactively block opening, but it does block winning.** Per the genre principle in §2.1 that a room stays explorable after time runs out, a visitor whose session has already transitioned to `expired` may still solve puzzles and open doors — nothing about gameplay is hard-gated by the timer. However, `mark_won`/`record_attempt` are only ever called while that visitor's session state is `in_progress`; if it is already `expired`, opening the final door still unlocks it mechanically (so the visitor isn't stuck) but is not recorded as a win and does not appear on the leaderboard. Puzzle attempts, hint requests, and item pickups are likewise never blocked by session state (`not_started`/`expired`) — the timer only gates leaderboard eligibility, not the ability to keep playing.

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
| `room:puzzle:add` / `:remove` / `:list` | client → server | Author puzzles (edit-permission gated) |
| `room:puzzle:attempt` | client → server | Submit a guess; returns `{correct, attemptsRemaining, alreadySolved, locked}` — **never** the answer |
| `room:puzzle:hint` | client → server | Same shape as `room:character:ask`'s rate-limited pattern; returns the next hint string |
| `room:puzzle:reset` | client → server | Edit-permission gated; clears one visitor's exhausted attempt count for a puzzle without clearing their solved state (§6.1) |
| `room:door:configure` | client → server | Set `requiredItemId`/`requiredPuzzleIds`/`destinationTile` on an `escape_door` |
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
- **Server-authoritative reveal/unlock state.** `isRevealed`/`isOpen` are only ever flipped by server-side puzzle/trigger logic, never by a raw client-sent field — the same validated-input discipline already enforced by `RoomObjectPlacementModel` and the "reject non-numeric input" bug-fix history visible in this repo's commit log.
- **Edit-permission-gated authoring, learner-open gameplay.** Adding/editing puzzles and doors requires the same `_require_edit_permission` check as every other object edit; *attempting* a puzzle or door is intentionally open to any room visitor, mirroring the existing precedent that *starting a guided tour* is not permission-gated even though *authoring* one is (see [docs/08-ai-characters.md](../docs/08-ai-characters.md) §"Guided tours").
- **No SSRF/URL surface added.** This feature introduces no new external URL fields, so `is_safe_external_url` is not implicated — puzzles are pure text/number matching.
- **Unrevealed items are never transmitted, not just unrendered.** As in §5.2, an undiscovered `hidden_item`'s position and existence are withheld server-side (filtered out of `list_objects_for_tiles` for that visitor) rather than sent to the client with a "please don't draw this" flag, which would leak its location to anyone inspecting network traffic.
- **Per-visitor isolation prevents griefing and spoilers alike.** Because solved-puzzle, revealed-item, and opened-door state are all keyed per user (§3.1), one visitor cannot lock another out of a puzzle via attempt-lockout, spoil another visitor's hidden item by revealing it first, or let another visitor walk through a door they didn't personally earn.

## 13. Data Model Additions (for the eventual persistence phase)

Following the existing style in `server/db/schema.sql` (the current schema already anticipates `story_nodes`, `room_objects`, etc. as Phase A foundations even though most runtime state today is in-memory per §16 of [educational_rooms_feature_design.md](educational_rooms_feature_design.md)):

```sql
CREATE TABLE IF NOT EXISTS room_puzzles (
    id            VARCHAR PRIMARY KEY,
    room_id       VARCHAR NOT NULL REFERENCES rooms(id),
    prompt        TEXT NOT NULL,
    answer_hash   VARCHAR NOT NULL,      -- never store plaintext answers
    match_mode    VARCHAR NOT NULL DEFAULT 'exact',
    hints         JSONB NOT NULL DEFAULT '[]',
    reveal_item_id VARCHAR,
    unlock_door_id VARCHAR,
    max_attempts  INT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

## 14. Delivery Phases

### Phase 1 (MVP)
- `escape_door` and `hidden_item` catalog entries + per-visitor collision/reveal wiring (§3.1, §5).
- `PuzzleEngine` with typed-answer puzzles bound to any object, including per-user solved state and attempt lockout/reset (§6.1–6.2).
- `InventoryEngine` with pick-up/require-item door logic (§7).
- `EscapeSessionEngine` with per-user timer, briefing, win/expired states, and per-user reveal/open tracking (§8.1–8.3).
- Builder panel + player HUD + puzzle modal, including build-mode-only visibility of unrevealed `hidden_item` objects (§10).
- Full unit test coverage for all three new engines, mirroring the existing `tests_python/test_npc_guide.py`/`test_story.py` structure (pure-logic tests, no sockets), plus `tests_python/test_main_*` handler-level tests following the `FakeSio` harness already used for guided tours.

### Phase 2
- Trigger-revealed puzzles (`reveal_object` event type) (§6.3).
- Story-character `knowledge_check` gating (§6.4) and the `ask_hint` payload wiring (§6.5).
- Leaderboard persistence and display (§8.4).
- Multi-door / multi-room chained escape sequences using `destinationTile` (§8.3).
- **Team/Shared Mode**: a room-host toggle that pools the timer, solved puzzles, revealed items, and opened doors room-wide instead of per-visitor, for groups who want the classic synchronized physical-escape-room-team experience (§3.1, §8.1).

### Phase 3
- Puzzle template library (pre-built riddle/cipher/sequence puzzle types with built-in `match_mode` presets) so non-technical creators can drop in a puzzle without writing their own answer-matching logic.
- Attempt analytics (which puzzles get the most wrong guesses / hint requests) to help creators tune difficulty, extending the same metrics spirit as §17 of [educational_rooms_feature_design.md](educational_rooms_feature_design.md).

## 15. Risks and Mitigations

- **Risk:** a creator builds an unsolvable room (a puzzle whose required fact is never actually placed anywhere reachable). **Mitigation:** the builder's existing Play Mode (§4.1 step 7) is the validation path; Phase 3's authoring guidance/checklist can also prompt "does every puzzle have a fact source in the room?"
- **Risk:** guess brute-forcing for short numeric codes. **Mitigation:** per-puzzle-per-user rate limiting (§12) and an optional `max_attempts` lockout.
- **Risk:** a hidden item or door is deleted mid-session, orphaning a visitor's in-progress inventory/state. **Mitigation:** `InventoryEngine.revoke_all_for_object` and `PuzzleEngine`/`EscapeSessionEngine` follow the same defensive discard pattern `GuideEngine.discard` already establishes for deleted `ai_character` objects (see `delete_object` in `room_builder.py`).
- **Risk:** per-user timers feel less "team" than genre-standard shared timers. **Mitigation:** explicitly scoped as a Phase 2 opt-in Team/Shared Mode (§3.1, §8.1, §14), not blocking MVP.
- **Risk:** per-visitor progress tracking (solved puzzles, revealed items, opened doors, each keyed per user) could grow unbounded in a very popular room with many one-time visitors. **Mitigation:** bounded the same way object/tile counts already are (`MAX_OBJECTS_PER_TILE`) — a follow-up cap on tracked escape-progress entries per room, plus normal inactive-session eviction, is a Phase 2 operational concern, not a Phase 1 blocker given typical concurrent-visitor counts.

## 16. Alignment Questions for Product Direction

1. Should MVP support only one escape door + one key per room, or multiple independent lock/key pairs from day one?
2. Should a failed/expired attempt let a visitor immediately retry (reset their own inventory/puzzle-solved state), or require a room host to reset the room for everyone?
3. Is a shared, room-wide "team" timer (everyone in the room shares one clock, matching the physical escape-room genre most closely) a Phase 1 requirement, or is the per-user timer proposed here acceptable for MVP?
4. Should the leaderboard be per-room only, or eventually cross-room (a global "fastest escapes" board) once persistence exists?
5. Do we want a built-in puzzle-type library (cipher, sequence, sudoku, riddle) in Phase 1, or is free-text/numeric answer matching sufficient to start, with templates deferred to Phase 3?
6. Should Team/Shared Mode (§3.1, §14) be pulled forward into Phase 1 if early educational users (classrooms, team-building groups) most commonly want one shared clock/progress per group rather than per individual?
