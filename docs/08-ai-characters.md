# AI Story Characters, Knowledge, and Guided Tours

`ai_character` is a placeable room object like a sofa or a bookshelf, but instead of an interaction menu it carries an authored persona: a name, role, appearance, a scripted conversation graph, an optional knowledge store, an optional LLM connection for free-form questions, and an optional guided tour. This document describes how those pieces fit together and how they are wired between the backend domain engines and the client builder panel.

## Placement and identity

Placing an `ai_character` object immediately provisions a matching character record (`server/game/room_builder.py: create_object` → `StoryEngine.add_character`) with a placeholder profile ("New Character" / `guide` role / `start` node). The object id and the character id are always the same value, so every character-scoped call in the socket API takes a single `objectId`. Provisioning up front means appearance, knowledge base, and generative-mode edits work the moment a character is placed, without requiring the author to save a name first. Deleting the object removes the character record and any guided tour together, so a recycled object id never inherits a previous character's profile.

`configure_character` (`room:character:configure`) is an upsert: naming a character for the first time creates its story-graph identity, and renaming it afterward updates the profile in place via `StoryEngine.set_character_profile` without resetting appearance, knowledge documents, or generative settings.

### Roles

A character's `role` is one of `ALLOWED_ROLES` (`guide`, `quiz_master`, `narrator`, `historical_persona`, `mentor`) and maps to a persona instruction in `ROLE_PERSONAS` (`server/game/story.py`). The persona is what makes the role a real behavioural setting rather than a stored label: `StoryEngine._build_system_prompt` prefixes the character's name and persona to the knowledge context before it is handed to the generative caller, so a `quiz_master` genuinely answers differently from a `narrator`.

`_build_system_prompt` is deliberately separate from `_build_knowledge_context`. The latter doubles as the *user-visible* predefined fallback answer, so folding persona text into it would reply to a visitor with "You are Owl, a warm, welcoming guide…" as though the character had said it.

The builder panel renders roles as a card list (`character-role-cards`, view-model `characterRoleCardOptions` in `src/story.js`) rather than a `<select>`. Each card states the behaviour change and shows an example reply, because the raw ids (`quiz_master`, `historical_persona`) told an author nothing about how the character would actually talk. `CHARACTER_ROLE_CARDS` descriptions must be kept in step with `ROLE_PERSONAS` so the UI never promises behaviour the server does not deliver.

## Appearance

`configure_character_appearance` (`room:character:appearance`) reuses the same option set and validation as player avatars (`server/game/avatar.py`), so AI characters render through the identical SVG avatar renderer as players — skin color, body type, hair, beard, glasses, clothes, and accessory.

The builder panel's "Appearance" section renders each of the seven fields as a row of option buttons (`character-appearance-pickers`, view-models `APPEARANCE_FIELDS` / `appearanceOptionCards` in `src/story.js`). Every option button contains a miniature avatar of *this* character with only that one field changed, so an author sees what "mohawk" or "goatee" does to their character instead of picking a word out of a dropdown and hoping. Skin tone is the one field rendered as plain colour swatches. Picking any option re-renders the whole set, since changing skin tone or body type also changes what the other rows' miniatures should show, and live-updates the large preview independently of the "Save Appearance" click.

The miniatures reuse `renderAvatarSVG`'s 60×90 output scaled down in CSS. The renderer only emits two sizes (`large` = 120×180, anything else = 60×90) and adding a third branch would ripple into player rendering. The thumbnail rule also sets `animation: none`, both because the global `.avatar-svg` idle-bob keyframes animate `transform` and would override the centering/scale, and because ~27 simultaneously bobbing miniatures would make the picker unreadable.

## Conversation triggers (predefined story graph)

Each character owns a small node graph (`room:character:node:add`, `room:character:node:list`, `room:character:talk`). A node has a `characterLine` and a list of choices, where each choice is either a leaf (no `nextNodeId`) or continues to another node. `room:character:talk` advances a per-user progress cursor (`StoryEngine._progress`), so two visitors can be at different points in the same character's conversation simultaneously. This is the zero-configuration mode: no LLM connection is required for a character to hold a scripted conversation.

## Knowledge base

A character's knowledge base (`room:character:knowledge_base:*`) is a small ordered document store, not a single free-text blob, so an author can organize multiple snippets:

- `title:set` — a short label for the whole knowledge base.
- `document:add` / `document:update` / `document:remove` / `document:reorder` — up to `MAX_KNOWLEDGE_DOCUMENTS` (20) documents, each `text`, `markdown`, or `link` typed, capped at `MAX_KNOWLEDGE_DOC_CONTENT_LENGTH` (4000) characters, so the combined prompt sent to an external API stays bounded in size and cost.

The builder panel lists documents with reorder/edit/remove actions and blocks adding more once the cap is reached.

## Generative mode (LLM-backed answers)

By default a character only responds along its scripted graph. Generative mode (`room:character:generative:configure`, backed by `StoryEngine.configure_generative_mode`) lets a room admin point a character at any OpenAI-compatible endpoint:

- **Base URL** — validated with `server/game/url_safety.py: is_safe_external_url` before being stored, rejecting internal/loopback/link-local addresses to prevent SSRF through a character's own configuration.
- **API key** — stored server-side only. It is never included in any value returned to a client (`StoryEngine._public_character` strips `apiKey` from every response), which is why the builder panel cannot pre-fill this field — it shows an explicit "Generative mode is ON/OFF" status line instead, since the key's absence in a response doesn't mean the key isn't set.

`room:character:ask` (`ask_character`) sends a learner's free-form question plus the assembled system prompt (role persona + knowledge-document context, see [Roles](#roles)) to the configured endpoint. Generative calls are rate-limited per user per character (`GENERATIVE_RATE_LIMIT_MAX_REQUESTS` = 5 per `GENERATIVE_RATE_LIMIT_WINDOW_MS` window) — predefined talk/hint flows are unaffected, only paid/third-party calls are throttled. Any call failure (timeout, non-2xx, malformed response) falls back to a predefined answer rather than surfacing an error, so the character never "goes silent" from a learner's perspective.

## Guided tours ("follow me")

A character can offer to walk a learner around the room. This is authored and run through `server/game/npc_guide.py`'s `GuideEngine`, wired into `RoomBuilderState` and the game loop:

- **Authoring** (`room:character:waypoint:add|remove|reorder|clear`) — up to 12 waypoints per character, each an (x, y) position clamped into the room bounds plus an optional spoken label (≤120 characters). Authoring is edit-permission gated like any other object edit. Editing the route cancels any tour currently in progress, since a running tour holds an index into the route.
- **Running a tour** (`room:character:tour:start|stop`) — starting a tour is deliberately *not* permission-gated; following a guide is a learner action, not an edit. The character walks to each waypoint in order at a pace slower than player movement so a learner can keep up, pauses and "speaks" the waypoint's label if it has one, then walks back to its origin position and the tour ends.
- **Broadcasting** — tour movement is ticked every game-loop frame and pushed over two lightweight events, `room:npc:moved` and `room:npc:say`, rather than being folded into the 30 Hz `room:builder:state` broadcast.

The builder panel's "Guided Tour" section lets an author drop a stop by clicking the map (crosshair cursor while picking) or by using their own current position, and lists stops in order with reorder/remove controls. The in-room dialogue modal shows "Follow me!" / "Stop following" buttons (mutually exclusive) and a live status line ("Walking (stop 2 of 3)", "Heading back...", "Tour complete").

## Event surface reference

| Event | Purpose |
| --- | --- |
| `room:character:configure` | Create or rename a character (upsert) |
| `room:character:appearance` | Set avatar-style appearance fields |
| `room:character:knowledge_base:title:set` | Set the knowledge base title |
| `room:character:knowledge_base:document:add/update/remove/reorder` | Manage knowledge documents |
| `room:character:generative:configure` | Set/clear the LLM base URL + API key |
| `room:character:node:add` / `node:list` | Author the scripted conversation graph |
| `room:character:talk` | Advance a visitor's scripted conversation |
| `room:character:ask` | Ask a free-form question (generative mode) |
| `room:character:waypoint:add/remove/reorder/clear` | Author a guided-tour route |
| `room:character:tour:start/stop` | Start or stop following a character's tour |
| `room:npc:moved` | Server → client: a touring character moved |
| `room:npc:say` | Server → client: a touring character spoke at a waypoint |

## Related domain modules

- `server/game/story.py` — `StoryEngine`: character profile/appearance, knowledge base, generative config, and the scripted node graph.
- `server/game/npc_guide.py` — `GuideEngine`: waypoint authoring and tour walk runtime.
- `server/game/room_builder.py` — owns both engines per room, enforces edit permissions, and decorates each `ai_character` room object with its `character`, `waypoints`, and `tour` state for every client in the room.
