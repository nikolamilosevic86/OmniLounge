# Escape Room Feature Design

## 1. Product Intent

This feature turns any OmniLaunge room into a cooperative escape room: a creator places furniture, hidden items, locked doors, and AI characters as they already do today, then layers puzzle logic on top so a group of visitors must *solve their way to a hidden key* before a locked door will open. It is designed as an authoring layer on top of the existing room builder, tile graph, object catalog, story-character, zone, and trigger systems — not a parallel system. Section 3 maps every new escape-room concept to the existing engine it extends.

This also directly serves the educational use cases already documented in the top-level [README.md](../README.md) ("Escape rooms and puzzle-based learning") and in [docs/08-ai-characters.md](../docs/08-ai-characters.md) (AI characters as puzzle-holders/hint-givers): a teacher can build a history-themed locked room where the "key" is only found after learners correctly answer three checkpoints seeded through the room's existing knowledge-base and story-node systems.

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
| A locked door that only opens once conditions are met | `RoomBuilderState.set_locked` / `isLocked` exists, but currently means "locked *from editing*," not "locked as a game obstacle" | A distinct **gameplay lock** state on `escape_door` objects, independent of the existing builder edit-lock (§5.1) |
| Carrying a found key between puzzles | Nothing exists yet | New per-user **Inventory** concept (§7), modeled after `StoryEngine`'s existing per-user progress dict pattern |
| A room-wide countdown and win/fail state | Nothing exists yet | New **EscapeSessionEngine** (§8), following the same in-memory, pure, unit-testable engine pattern as `GuideEngine`/`StoryEngine`/`MediaLibrary` |
| Fastest-completion leaderboard | `RoomBuilderState` versioning already tracks ordered history (`_versions`, `save_draft`/`publish`) as a precedent for append-only in-memory history | New `_attempts` list on `EscapeSessionEngine` (§8.4) |
| Multi-room puzzle sequences ("solve room 1, walk through the door into room 2") | The 5×5 tile grid and `tile_navigation.can_add_neighbor_tile` (documented in [educational_rooms_feature_design.md](educational_rooms_feature_design.md) §6) already support multi-tile rooms | `escape_door.destinationTile` reuses this instead of inventing new spatial logic (§5.1) |
| Object collision (a locked door blocks movement like any other object) | `movement.py: resolve_collision` + `server/main.py: _tile_collision_obstacles`, which already turns every builder-placed object into a solid AABB obstacle | No change — an `escape_door` is solid by default, exactly like a table; opening it just removes it from the obstacle list dynamically (§5.1) |
| Room edit permissions for who can author puzzles | `RoomBuilderState._require_edit_permission` / `editPermission: owner_only \| anyone` per object | No change — puzzle authoring uses the same permission check as every other object edit |

This table is the core argument for the design: **escape rooms are not a new subsystem, they are seven small additions wired through six systems that already exist and are already tested.**

## 4. End-to-End Experience Walkthrough

### 4.1 Creator (authoring) flow
1. Creator builds a room as normal: tiles, furniture, an AI character, a bookshelf, a TV — using the existing builder panels.
2. Creator opens the new **"Escape Room" builder panel** (parallel to the existing "AI Character" panel) and flips **Enable Escape Mode** on for the room. This exposes a time limit field (minutes) and a short briefing text field (shown to visitors before the timer starts).
3. Creator places a **Locked Door** object (new catalog type `escape_door`) somewhere in the room — the literal exit — and configures what unlocks it: either a specific **key item id**, or a list of **puzzle ids** that must all be solved first (or both).
4. Creator places one or more **Hidden Item** objects (new catalog type `hidden_item`, defaults to `isRevealed: false` so it renders nothing and cannot be interacted with) representing the eventual key, and optionally decoy items.
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
4. Solving a puzzle either reveals a hidden item (which now renders in the room and becomes interactable — "Pick Up") or reports success and unlocks the door directly.
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
Config fields (stored in the existing per-object `config` dict, same mechanism `bookshelf`/`tv`/`music_player` already use for object-specific data):
- `requiredItemId: str | None` — an inventory item id that must be held to open it.
- `requiredPuzzleIds: list[str]` — puzzle ids that must all be in a "solved" state.
- `destinationTile: {"x": int, "y": int} | None` — reuses the existing tile-graph coordinate model; if set, a successful open transitions the visitor there via the same mechanism as a normal edge crossing; if omitted, opening it marks that visitor's escape attempt as **won**.
- `isOpen: bool` — runtime state, defaults to `False`.

Gameplay-lock vs edit-lock: `escape_door` deliberately does **not** reuse `RoomBuilderState.isLocked`/`set_locked`, because that field already means "an editor cannot move/delete/resize this object" (`_require_unlocked` in `delete_object`/move/resize handlers). Overloading it would mean an author's escape door became un-editable the moment gameplay locked it, or (worse) a player "unlocking" it during play would accidentally grant editors the ability to move it. A door's `isOpen` runtime flag is a separate, independent piece of state, exactly the same way `ai_character`'s `tour`/`waypoints` runtime state already lives alongside the object without touching `isLocked`.

Collision: while `isOpen` is `False`, `escape_door` is a solid AABB obstacle for free — `server/main.py: _tile_collision_obstacles` already turns every object in `RoomBuilderState.list_objects` into a blocking box with no per-type special-casing needed. Once `isOpen` flips to `True`, `_tile_collision_obstacles` must skip objects where `record["objectType"] == "escape_door" and record["config"].get("isOpen")`, so the one required change is a single added condition in that existing function, not a new subsystem.

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
Config fields:
- `isRevealed: bool` — defaults to `False`. While `False`, the object is decorated exactly like today but the client renders nothing for it and `interact_with_object` rejects `pick_up` with a `PermissionError` ("this cannot be interacted with yet"), mirroring the existing `isInteractable` check pattern.
- `itemKind: "key" | "tool" | "note"` — cosmetic/inventory-icon hint only.
- `singleUse: bool` — whether the item disappears from the world once picked up (default `True`; the common case for a key).

Revealing an item is just `record["config"]["isRevealed"] = True`, settable from three places, matching §4.1's three puzzle-authoring paths: a solved puzzle's reward, a fired area trigger's `reveal_object` payload (§6.3), or a story node's `knowledge_check` success branch (§6.4).

## 6. Puzzle Authoring Paths (reusing existing systems)

### 6.1 New `PuzzleEngine` domain module
A new, small, pure module `server/game/puzzle.py`, matching the existing style of `GuideEngine`/`BookshelfLibrary`/`MediaLibrary` (plain dict-backed state, no I/O, fully unit-testable without sockets or a DB):

```python
class PuzzleEngine:
    def __init__(self) -> None:
        self._puzzles: dict[str, dict[str, Any]] = {}   # puzzle_id -> definition + solved-by set
        self._attempt_limiter = SlidingWindowRateLimiter(...)  # reuse server/game/rate_limiter.py

    def add_puzzle(self, puzzle_id, prompt, answer, hints: list[str], reveal_item_id=None,
                   unlock_door_id=None, max_attempts: int | None = None) -> dict: ...
    def remove_puzzle(self, puzzle_id) -> bool: ...
    def get_puzzle_public(self, puzzle_id) -> dict:  # never includes `answer`
    def attempt_solve(self, puzzle_id, user_id, guess: str, now_ms: float) -> dict:
        # returns {"correct": bool, "attemptsRemaining": int | None, "alreadySolved": bool}
        # rate-limited per (puzzle_id, user_id) to blunt brute-forcing short codes
    def is_solved(self, puzzle_id, user_id=None) -> bool:
        # user_id=None checks "solved by anyone in the room" for shared-progress rooms
    def request_hint(self, puzzle_id, user_id, now_ms: float) -> dict:
        # returns {"hint": str | None, "hintsUsed": int, "hintsRemaining": int}
```
Answer comparison is case-insensitive and whitespace-trimmed by default (a `matchMode: "exact" | "numeric" | "contains"` field on the puzzle covers riddles vs number-lock codes vs keyword-search answers, mirroring the puzzle-type variety in §2.1). The **answer field is only ever read server-side**; `get_puzzle_public` is the only representation ever serialized to a client, exactly the same discipline `StoryEngine._public_character` already applies to strip `apiKey` before any client-facing response (see [docs/08-ai-characters.md](../docs/08-ai-characters.md)).

`RoomBuilderState` owns one `PuzzleEngine` instance per room (`self._puzzles = PuzzleEngine()` in `__init__`, next to `self._story`/`self._guide`), the same ownership pattern already used for every other per-room engine.

### 6.2 Puzzle panel interaction (typed-answer puzzles)
Rather than inventing a tenth object type, any existing interactive object gains an optional puzzle binding: a `puzzleId` field in its `config`. When present, a new generic interaction `solve_puzzle` (added to `bookshelf`, `table`, or any object type a creator wants to double as a puzzle prop — e.g. a "desk" is just a `table` with a bound puzzle) opens a small answer-input modal client-side and calls `room:puzzle:attempt` with the typed guess.

### 6.3 Trigger-revealed puzzles (search-based / environmental)
`RoomBuilderState.evaluate_area_enter` already fires trigger payloads keyed by `eventType`. This design adds one new recognized `eventType`: `"reveal_object"`, with `payload: {"objectId": "<hidden_item id>"}`. No change to the trigger *engine* is required — `evaluate_area_enter`'s cooldown/repeatable/fired-once semantics already fully cover "reveal this the first time someone steps on this rug." The only new code is the handler in `server/main.py` that, on receiving a fired `reveal_object` trigger, calls the existing `set_object_config`-style setter to flip `isRevealed` and broadcasts the updated object — the same broadcast path every other builder mutation already uses.

### 6.4 Story-character knowledge checks (character-guarded puzzles)
`StoryNodeModel.knowledge_check` and `completion_flag` already exist in `server/game/story.py` but `StoryEngine.talk`/`advance` never reads them — they are currently write-only metadata. This design activates them: when a node has `knowledge_check` set to a `puzzle_id`, `StoryEngine.talk` (called from `room:character:talk`) consults the room's `PuzzleEngine.is_solved(puzzle_id, user_id)` before allowing the choice that leads past that node; if unsolved, the character's line branches to a "you need to figure that out first" response instead of the configured next node. This lets a creator build a character who simply won't hand over a hint or the next chapter of the story until the visitor has actually solved something — the "quiz master" role already listed in `ALLOWED_ROLES` finally has a concrete mechanical purpose.

### 6.5 Hint system via the existing `ask_hint` interaction
`ai_character`'s interaction menu already advertises `"ask_hint"` (`{"interactionType": "ask_hint", "label": "Ask Hint", ...}`), and `room_builder.py: _interaction_payload` already has a matching `if interaction_type == "ask_hint":` branch — today it just returns the character record with no hint content. This design fills in that branch: an `ai_character` gets an optional `guardsPuzzleId` config field; `ask_hint` then calls `PuzzleEngine.request_hint(guardsPuzzleId, requester_id, now_ms)` and returns the next hint string (if any remain) alongside the character payload. This reuses 100% of the existing interaction plumbing, cooldown handling (`interactionCooldownMs` already exists per-object and is a natural fit for "you can only ask this character for a hint once every N seconds"), and dialogue-modal UI — the only new code is what the stub branch returns.

## 7. Inventory

A new, small, per-room, per-user structure — deliberately not a generalized item/economy system, since nothing else in the product needs one yet:

```python
class InventoryEngine:  # server/game/inventory.py
    def __init__(self) -> None:
        self._held: dict[str, set[str]] = {}  # user_id -> set of item object ids

    def grant(self, user_id: str, item_object_id: str) -> None: ...
    def has(self, user_id: str, item_object_id: str) -> bool: ...
    def list_items(self, user_id: str) -> list[str]: ...
    def revoke_all_for_object(self, item_object_id: str) -> None:  # object deleted mid-game
```
This mirrors the `dict[str, set[...]]`-per-user-key shape already used by `StoryEngine._progress` (keyed by `(object_id, character_id, user_id)`) and `BookshelfLibrary`'s reading-progress map, so it fits the codebase's existing idiom rather than introducing a new persistence style. `interact_with_object`'s `pick_up` branch on `hidden_item` calls `self._inventory.grant(requester_id, object_id)`, flips `singleUse` items to no longer render for that user (or globally, for `singleUse` items shared by the whole room — configurable per item), and the client adds it to the HUD inventory strip.

## 8. Escape Session (timer, win/lose, leaderboard)

### 8.1 `EscapeSessionEngine` (`server/game/escape_session.py`)
One instance per room, owned by `RoomBuilderState` exactly like `PuzzleEngine`/`InventoryEngine`:

```python
class EscapeSessionEngine:
    def configure(self, enabled: bool, time_limit_ms: float, briefing: str | None) -> None: ...
    def start(self, user_id: str, now_ms: float) -> dict:  # per-user attempt clock
    def status(self, user_id: str, now_ms: float) -> dict:
        # {"state": "not_started"|"in_progress"|"won"|"expired", "remainingMs": float}
    def mark_won(self, user_id: str, now_ms: float) -> dict:  # called when the escape_door opens
    def record_attempt(self, user_id: str, display_name: str, elapsed_ms: float) -> None:
        # appended to an ordered leaderboard list, same append-then-sort pattern as
        # RoomBuilderState._versions
    def leaderboard(self, limit: int = 10) -> list[dict]: ...
```
Per-user (not room-wide) timers are the default because OmniLaunge rooms are persistent, ambient multiplayer spaces (per [docs/01-user-experience.md](../docs/01-user-experience.md)) rather than a booked, synchronized physical session — a visitor who joins mid-session should not inherit someone else's countdown. A room-host-configurable "shared team timer" mode is listed as a Phase 2 item (§10) for groups who want the classic synchronized-team experience.

### 8.2 Game-loop tick
`server/main.py`'s existing `game_loop()` already ticks per-room, per-frame concerns (see `tick_guided_tours`). A new `tick_escape_sessions(room_id, now_ms)` follows the exact same shape: for each in-progress session past its `time_limit_ms`, transition it to `expired` and emit a lightweight `room:escape:expired` event to that user only — mirroring how `room:npc:moved` is a targeted, lightweight event rather than a full state rebroadcast.

### 8.3 Winning
When `escape_door`'s `attempt_open` interaction succeeds, `RoomBuilderState` calls `self._escape.mark_won(requester_id, now_ms)` and, if `destinationTile` is unset, that is the win condition; if set, the visitor also transitions tiles via the existing tile-crossing path, and the room is "escaped" as a bonus rather than the sole win condition — supporting the "escape door leads to the next themed room" chained-rooms pattern from §4.2 without any new spatial code.

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
| `room:escape:won` | server → client | Broadcast (to the winner, and optionally room-wide as a celebratory toast) when a door opens the room |
| `room:escape:leaderboard:list` | client → server | Fetch top completion times |
| `room:puzzle:add` / `:remove` / `:list` | client → server | Author puzzles (edit-permission gated) |
| `room:puzzle:attempt` | client → server | Submit a guess; returns `{correct, attemptsRemaining, alreadySolved}` — **never** the answer |
| `room:puzzle:hint` | client → server | Same shape as `room:character:ask`'s rate-limited pattern; returns the next hint string |
| `room:door:configure` | client → server | Set `requiredItemId`/`requiredPuzzleIds`/`destinationTile` on an `escape_door` |
| `room:door:attempt_open` | client → server | Also reachable via the generic `room:object:interact` with `interactionType: "attempt_open"`, consistent with every other object's interaction dispatch |
| `room:item:pick_up` | client → server | Also reachable via `room:object:interact` with `interactionType: "pick_up"`, same as above |
| `room:inventory:list` | client → server | Fetch the requester's current held items for the HUD |

All of these follow the already-established handler skeleton in `server/main.py` (`room_id, _tile, builder = _current_room_and_builder(sid)` → guard → `try/except (KeyError, PermissionError, ValueError)` → `emit("error", ...)` → `broadcast_builder_state` where relevant), so no new error-handling pattern needs to be introduced.

## 10. Client UI Additions

- **Builder panel**: a new "Escape Room" section in the existing builder sidebar (parallel to "AI Character," see [client/index.html](../client/index.html)'s `#configure-character-section`), with an Enable toggle, time-limit field, briefing textarea, and a puzzle list (add/edit/remove) using the same `.builder-field`/`.builder-primary-btn`/`.builder-object-list` Material 3 classes already standardized across the builder (see the recent Knowledge Store panel M3 unification).
- **Door/Item authoring**: placing an `escape_door` or `hidden_item` object surfaces a small config section (required item/puzzle dropdown for doors; reveal-condition summary for items), reusing the existing per-object-type "Configure" section pattern already used for bookshelf/tv/music_player/ai_character.
- **Player HUD**: a compact countdown timer chip and an inventory strip of small icons, added next to the existing tile/build-mode HUD chips in the room view (see the screenshot in [README.md](../README.md) for the existing HUD chip style to match).
- **Puzzle modal**: a small modal (reusing the existing dialogue-modal shell used for AI character conversations) with the prompt text, a single text input, a Submit button, and an "Ask for a Hint" secondary action when the puzzle is bound to a character.
- **Briefing / win / expired cards**: full-panel overlays reusing the existing modal/overlay component already used for the room-chooser and dialogue modals, not a new overlay system.

## 11. Worked Example: "The Locked Archive" (educational template)

To ground the design in the educational use case from the README, a concrete authored example:
1. Room theme: a history archive. Briefing: "The archive door has sealed itself. Find the librarian's key before the vault reseals in 15 minutes."
2. An `ai_character` "Archivist" (role `quiz_master`) has a knowledge base pre-loaded with three short historical facts (existing knowledge-document system). Its story graph has a `knowledge_check` node gated on puzzle `date-riddle`.
3. A `bookshelf` holds a "clue" book whose content contains the fact needed to answer `date-riddle` (reuses the existing reading system — no new content type).
4. A `table` object is bound to `puzzle: date-riddle` (numeric match mode) — visitors read the book, talk to the Archivist to confirm their understanding, then interact with the table to submit the year.
5. Solving `date-riddle` reveals a `hidden_item` ("Brass Key") elsewhere in the room via its `rewardItemId`.
6. An `escape_door` requires that key. Opening it has no `destinationTile` set, so opening it is the win condition and ends that visitor's timer.
7. A leaderboard on the room's info panel shows the fastest three visitors to find the key.

This example uses **zero new content types** — book, character, table, and door are all either pre-existing or the two new catalog entries from §5.

## 12. Security and Anti-Cheat Considerations

- **Answers never leave the server.** `PuzzleEngine.get_puzzle_public` strips `answer`, matching the existing `StoryEngine._public_character` discipline of never returning `apiKey`.
- **Rate-limit guesses.** `attempt_solve` uses the existing `SlidingWindowRateLimiter` (already used for generative AI calls) per `(puzzle_id, user_id)`, so a short numeric code cannot be brute-forced by an automated script.
- **Server-authoritative reveal/unlock state.** `isRevealed`/`isOpen` are only ever flipped by server-side puzzle/trigger logic, never by a raw client-sent field — the same validated-input discipline already enforced by `RoomObjectPlacementModel` and the "reject non-numeric input" bug-fix history visible in this repo's commit log.
- **Edit-permission-gated authoring, learner-open gameplay.** Adding/editing puzzles and doors requires the same `_require_edit_permission` check as every other object edit; *attempting* a puzzle or door is intentionally open to any room visitor, mirroring the existing precedent that *starting a guided tour* is not permission-gated even though *authoring* one is (see [docs/08-ai-characters.md](../docs/08-ai-characters.md) §"Guided tours").
- **No SSRF/URL surface added.** This feature introduces no new external URL fields, so `is_safe_external_url` is not implicated — puzzles are pure text/number matching.

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
```
`room_objects.config` (already a JSON/JSONB config column per the existing schema pattern used by bookshelf/tv/music_player) absorbs `escape_door`/`hidden_item` fields with no schema change needed there.

## 14. Delivery Phases

### Phase 1 (MVP)
- `escape_door` and `hidden_item` catalog entries + collision/reveal wiring (§5).
- `PuzzleEngine` with typed-answer puzzles bound to any object (§6.1–6.2).
- `InventoryEngine` with pick-up/require-item door logic (§7).
- `EscapeSessionEngine` with per-user timer, briefing, win/expired states (§8.1–8.3).
- Builder panel + player HUD + puzzle modal (§10).
- Full unit test coverage for all three new engines, mirroring the existing `tests_python/test_npc_guide.py`/`test_story.py` structure (pure-logic tests, no sockets), plus `tests_python/test_main_*` handler-level tests following the `FakeSio` harness already used for guided tours.

### Phase 2
- Trigger-revealed puzzles (`reveal_object` event type) (§6.3).
- Story-character `knowledge_check` gating (§6.4) and the `ask_hint` payload wiring (§6.5).
- Leaderboard persistence and display (§8.4).
- Multi-door / multi-room chained escape sequences using `destinationTile` (§8.3).
- Optional room-host-configurable shared/synchronized team timer (§8.1).

### Phase 3
- Puzzle template library (pre-built riddle/cipher/sequence puzzle types with built-in `match_mode` presets) so non-technical creators can drop in a puzzle without writing their own answer-matching logic.
- Attempt analytics (which puzzles get the most wrong guesses / hint requests) to help creators tune difficulty, extending the same metrics spirit as §17 of [educational_rooms_feature_design.md](educational_rooms_feature_design.md).

## 15. Risks and Mitigations

- **Risk:** a creator builds an unsolvable room (a puzzle whose required fact is never actually placed anywhere reachable). **Mitigation:** the builder's existing Play Mode (§4.1 step 7) is the validation path; Phase 3's authoring guidance/checklist can also prompt "does every puzzle have a fact source in the room?"
- **Risk:** guess brute-forcing for short numeric codes. **Mitigation:** per-puzzle-per-user rate limiting (§12) and an optional `max_attempts` lockout.
- **Risk:** a hidden item or door is deleted mid-session, orphaning a visitor's in-progress inventory/state. **Mitigation:** `InventoryEngine.revoke_all_for_object` and `PuzzleEngine`/`EscapeSessionEngine` follow the same defensive discard pattern `GuideEngine.discard` already establishes for deleted `ai_character` objects (see `delete_object` in `room_builder.py`).
- **Risk:** per-user timers feel less "team" than genre-standard shared timers. **Mitigation:** explicitly scoped as a Phase 2 opt-in mode (§8.1), not blocking MVP.

## 16. Alignment Questions for Product Direction

1. Should MVP support only one escape door + one key per room, or multiple independent lock/key pairs from day one?
2. Should a failed/expired attempt let a visitor immediately retry (reset their own inventory/puzzle-solved state), or require a room host to reset the room for everyone?
3. Is a shared, room-wide "team" timer (everyone in the room shares one clock, matching the physical escape-room genre most closely) a Phase 1 requirement, or is the per-user timer proposed here acceptable for MVP?
4. Should the leaderboard be per-room only, or eventually cross-room (a global "fastest escapes" board) once persistence exists?
5. Do we want a built-in puzzle-type library (cipher, sequence, sudoku, riddle) in Phase 1, or is free-text/numeric answer matching sufficient to start, with templates deferred to Phase 3?
