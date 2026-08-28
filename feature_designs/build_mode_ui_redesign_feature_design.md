# Build Mode UI Redesign — Feature Design

## 1. Product Intent

Build Mode is how every OmniLaunge room gets furnished, and today it works entirely through a right-hand form: a type dropdown, a handful of preset dropdowns, an "Add Object Here" button that drops the object on top of whichever player clicked it, and a stack of numeric X/Y/width/height/rotation text inputs to move it afterwards. It is functional but it does not *feel* like furnishing a room — there is no palette to browse, nothing to drag, and no sense of "reaching into the room and placing a couch where you want it." Comparable creative building tools (The Sims' Build/Buy mode, IKEA-style room planners, browser-based room designers) all share a small set of interaction patterns that make placement feel tactile and immediate: a visual catalog you drag from, direct manipulation of what's already placed (grab it, spin it, resize it, right where it sits), and a room that visibly reads as a *room* — walls with real doorways you walk through, not a rectangle you fall off the edge of.

This design turns Build Mode into a drag-and-drop, click-to-edit authoring surface with a Sims-inspired visual language, while reusing every engine, socket event, and permission check that already exists — this is a **client-side interaction and rendering redesign**, not a rewrite of the object model. It also fixes a specific, concrete rough edge the user flagged: tiles are stitched together by an invisible edge you silently walk through, and the only wall the room ever draws (the back wall) has no opening in it, so walking "north" reads as walking straight into solid wall texture. This design replaces that with real doorway graphics that only appear where a neighboring tile actually exists, using tile data the client already holds.

## 2. Research: What Makes Placement UIs Feel Good

Genre-standard patterns from life-simulation building modes (The Sims), room/interior planners, and other placement-driven builders, distilled into principles this design follows:

1. **Catalog, not a form.** Items to place are browsed visually — thumbnails grouped by category/tab — not chosen from a text dropdown. The thumbnail should look like the thing you're about to place, including its current color/material, not a generic icon.
2. **Drag from catalog into the world.** The primary placement gesture is picking an item up from the palette and dropping it where you want it, with a live preview (a translucent "ghost" of the object) following the cursor before you commit.
3. **Direct manipulation of placed objects.** Once something is in the room, you interact with *it*, not with a side panel: click it to select, drag it to move, grab a corner to resize, grab a handle to rotate, click a swatch to recolor. A side panel is still useful for anything that isn't spatial (which book is on the shelf, what video plays), but position/size/rotation/color are edited in place.
4. **Snapping and guides.** Grid or alignment snapping makes placement feel precise instead of fiddly, with an easy way to turn it off for freeform placement.
5. **The room reads as a room.** Walls, doorways, and floor boundaries are legible at a glance — you can tell where you can and can't walk before you try it, and transitions between spaces happen at visibly-marked doorways, not invisible thresholds.
6. **Non-destructive, low-friction editing.** Selecting something never feels risky — a clearly reachable Delete/undo affordance, and edits preview live rather than requiring a separate "commit" step.
7. **Show the least possible, expand on demand.** The best building tools default to an almost-empty screen — a palette and a room — and reveal deeper controls only once they're relevant (an object is selected, a rarely-used feature is opened). Nothing sits on screen "just in case." This is the guiding constraint on every layout decision in §6 and §8: prefer one small, well-labeled control that expands over five permanently-visible ones.

These seven principles map directly onto §6–§12 below.

## 3. Current State Audit

This section is the grounding for the "reuse map" in §5 — every claim here is what exists *today*, cited to file:line.

### 3.1 Build panel structure
[client/index.html](../client/index.html#L156-L350) defines `<aside id="build-controls" class="builder-panel hidden">`, a fixed-width (300px, [client/css/styles.css](../client/css/styles.css#L1032)) right-hand sidebar containing seven stacked sections in one long scroll: Tiles, Objects, Zones, Triggers, Escape Room, Room Admin, Versions. Every section is always visible at once (no tabs), so the panel is already long before any redesign.

### 3.2 Object creation today
[client/js/main.js](../client/js/main.js#L650-L661) — `objectAddBtn` reads `objectTypeSelect`/`objectSizeSelect`/`objectColorSelect`/`objectMaterialSelect` and emits `room:object:create` at the **clicking player's current avatar position**, not a chosen point:
```javascript
objectAddBtn?.addEventListener('click', () => {
  const me = state.players.get(state.playerId);
  const x = me?.position?.x ?? 400;
  const y = me?.position?.y ?? 300;
  state.socket?.emit('room:object:create', { objectType: objectTypeSelect?.value || 'table', x, y, ... });
});
```
There is no palette, no thumbnail, and no way to choose *where* to place something except by walking your avatar there first.

### 3.3 Object selection & editing today
Clicking a configurable object on the canvas in build mode calls `selectBuilderObjectForConfiguration(obj)` ([client/js/main.js](../client/js/main.js#L2329-L2360)), which shows a type-specific section of the separate `#configure-controls` panel (bookshelf/tv/music_player/ai_character/escape_door/hidden_item — each with its own content fields). Position/size/rotation are edited through **text inputs**, not by touching the object:
```javascript
configureFieldsContainer?.addEventListener('input', (evt) => {
  const input = evt.target;
  const field = input.getAttribute('data-field');
  if (field === 'x' || field === 'y') state.socket?.emit('room:object:move', { objectId, x, y });
  else if (field === 'width' || field === 'height') state.socket?.emit('room:object:resize', { objectId, width, height });
  else if (field === 'rotation') state.socket?.emit('room:object:rotate', { objectId, rotation: value });
});
```
[client/js/builder-objects.js](../src/builder-objects.js#L56-L59)'s `getBuilderObjectAtPoint()` is the only canvas-hit-testing helper that exists — it is used purely for click-to-select, never for drag. **There is no drag-and-drop anywhere in the codebase today** — confirmed by the absence of any `pointerdown`/`mousedown`+`mousemove` drag sequence or native HTML5 `draggable` usage on canvas or palette elements.

### 3.4 Object catalog
[server/game/room_object_catalog.py](../server/game/room_object_catalog.py#L52-L136) `OBJECT_TYPE_CATALOG` defines 10 types (`table`, `chair`, `bar`, `sofa`, `bookshelf`, `tv`, `music_player`, `ai_character`, `escape_door`, `hidden_item`), each with a `category`, `defaultSizePreset`, and an `interactions` list. Size presets ([lines 20-25](../server/game/room_object_catalog.py#L20-L25)) are `S: 48×48`, `M: 72×72`, `L: 108×108`; color presets ([lines 27-31](../server/game/room_object_catalog.py#L27-L31)) are 8 named swatches; materials ([line 33](../server/game/room_object_catalog.py#L33)) are `wood/metal/fabric/glass/stone`. [client/index.html](../client/index.html#L192-L228) mirrors this as a hardcoded `<select>` populated with the same 10 types plus the same preset lists — this mirror is the palette's data source and needs no server change to become a visual grid instead of a `<select>`.

### 3.5 Canvas rendering & the "walking through a wall" problem
[client/js/room-renderer.js](../client/js/room-renderer.js#L75-L84) draws, per frame: `drawBackdrop` → `drawWall` → `drawFloor` → (lobby-only) `drawFurniture` → `drawBuilderObjects` → ambient light/vignette. Critically, **only one wall is ever drawn** — `drawWall(ctx)` ([lines 98-124](../client/js/room-renderer.js#L98-L124)) paints a wall texture (with windows and wall art) across the *top* of the 800×600 canvas only, up to `WALL_HEIGHT = ROOM_HEIGHT * 0.42`. The left, right, and bottom edges of the room are just the edge of the floor — there is no wall geometry there at all today. This exactly matches the reported symptom: walking off the top of a tile visually means walking straight into the one wall the room has, because there is no doorway opening drawn into it, while walking off the other three edges means walking off open floor into nothing.

The actual tile-to-tile transition is edge-crossing, not a door: `server/game/tile_navigation.py`'s [`detect_edge_transition`](../server/game/tile_navigation.py#L35-L48) fires when a player's position comes within `EDGE_EPSILON = 20.0` px of any of the four canvas edges, and `RoomsRegistry.transition_player_tile_if_needed` ([server/game/rooms_registry.py](../server/game/rooms_registry.py#L313-L338)) only actually moves the player to the neighbor tile if that neighbor exists in `room_tiles`; otherwise nothing happens and the player is simply blocked at the boundary by the existing collision clamp. So the mechanic itself is already exactly right (you can't walk somewhere with no tile) — what's missing is purely the **visual signal** of where a doorway is versus where a wall should stop you.

The client already has every piece of data needed to draw that signal without any new network request: `state.roomTiles` (the full set of tile coordinates in the room, refreshed by the `room:tiles` handler at [client/js/main.js](../client/js/main.js#L1693-L1696)) and `state.currentTile`. This pairing is already consumed by [`buildMiniMapCells`](../src/world-map.js#L11-L28) to render the existing corner mini-map — the exact same neighbor-lookup logic just needs to run per-edge instead of per-mini-map-cell.

### 3.6 Room style presets already exist but are create-only
[client/js/room-styles.js](../client/js/room-styles.js) / [server/game/room_styles.py](../server/game/room_styles.py) already define 5 named ambient presets (`modern-loft`, `cozy-den`, `sunlit-studio`, `midnight-lounge`, `minimalist-white`+1 more) controlling backdrop/wall/floor colors and the ambient light tint, each with a `label`/`description`. Today a room's style is fixed at creation time (`create_room(..., room_style=...)`, [server/game/rooms_registry.py](../server/game/rooms_registry.py#L59-L74)) and re-served on join ([server/main.py](../server/main.py#L869)) — there is no mutator to change it afterward, and no Build Mode UI surfaces it at all.

### 3.7 Design system tokens available for reuse
[client/css/styles.css](../client/css/styles.css#L11-L84) defines a full Material 3 token set already used throughout the builder: `--md-primary/secondary/tertiary(-container)`, `--md-surface-container-{lowest,low,,high,highest}`, `--md-outline(-variant)`, `--md-shape-{xs,sm,md,lg,xl,full}`, `--md-elevation-{1..5}`, and `--md-duration-{short,medium}`/`--md-easing-{standard,emphasized}`. Every new element in this design must be built from these tokens — no new colors or bespoke shadows.

The app also already standardizes on the **Material Symbols Outlined** icon font (class `material-symbols-outlined`), used throughout the existing UI — e.g. `construction` for the Build Mode toggle ([client/index.html:158](../client/index.html#L158)), `tune` for the Configure panel ([client/index.html:392](../client/index.html#L392)), and `palette` already labeling the avatar Skin Color field ([client/index.html:39](../client/index.html#L39)). Every new icon this design introduces (§8, §12) is a named glyph from this same font, at the same sizing convention — never an emoji or a custom SVG. Two component *patterns* used below, however, do not exist anywhere in the codebase yet and must be built net-new from the token set: filter chips (§7.1) and a small icon-button toolbar with tooltips (§8.1/§8.3). The existing `.builder-checkbox-field` (a native checkbox, [styles.css:1349](../client/css/styles.css#L1349)) is not reused for the new Snap-to-Grid control (§12) — that is better expressed as a single toggleable icon button, consistent with the "least possible controls" principle (§2.7), not a labeled checkbox.

## 4. Design Goals

1. **Palette over paperwork.** Replace the type/size/color/material dropdown stack with a visual, categorized catalog grid, styled and laid out the way a Sims Buy Mode catalog is.
2. **Grab it, don't type it.** Placement and movement become drag gestures on the canvas; numeric inputs remain available as a precision/accessibility fallback, never as the *only* way in.
3. **Select it, see its handles.** A selected object shows its own move/resize/rotate affordances directly on the canvas, Sims-style, instead of only reflecting state in a side panel.
4. **Rooms look like rooms.** Every tile edge either shows a walkable doorway (when a neighbor tile exists) or a capped wall/rail (when it doesn't) — no more invisible thresholds.
5. **Reuse, never replace.** No existing socket event, engine method, permission check, or the type-specific `#configure-controls` deep-editing sections (books, playlists, dialogue, puzzles) changes behavior — this redesign sits entirely in the client's rendering and input layer plus one small, well-scoped server addition (a room-style mutator, §11).
6. **As few things on screen as the task allows.** Nothing is shown "in case it's needed" — rarely-used controls (puzzle/zone authoring, room admin) collapse under one clearly-labeled entry point instead of standing permanently alongside everyday furnishing controls, and a selected object's editing affordances appear only while it is selected and disappear the moment it isn't. See §6.1 for how this is applied to the panel layout, and §8.1 for the on-canvas toolbar.

### 4.1 Progressive disclosure ladder
Every control in this design sits at exactly one of three visibility tiers, and nothing is promoted to a higher tier than it needs:
- **Tier 1 — always visible:** the room canvas itself, the tab strip (§6.1), and the catalog grid's default (unfiltered, all-categories) view.
- **Tier 2 — visible when contextually relevant:** the on-canvas selection toolbar (only while an object is selected, §8.1), catalog filter chips and search (only meaningfully useful once the grid has more than a handful of cards, §7.1), the Add-Tile hotspot on a closed rail (only where there's no neighbor tile yet, §10.4).
- **Tier 3 — one click away, collapsed by default:** the Advanced accordion sections (Puzzles & Zones, Room Admin, Versions — §6.1), and per-type non-spatial editing ("Edit Details…", only for object types that actually have non-spatial config, §8.4).

## 5. Reuse Map

| Concern | Existing system reused | What's new |
| --- | --- | --- |
| Object types, sizes, colors, materials | `OBJECT_TYPE_CATALOG`, `SIZE_PRESETS`, `COLOR_PRESETS`, `MATERIAL_PRESETS` ([room_object_catalog.py](../server/game/room_object_catalog.py)) | A client-side thumbnail renderer and a palette grid layout — no new server data |
| Creating an object | `room:object:create` ([server/main.py:1084](../server/main.py#L1084)) | Position comes from a canvas drop point instead of the avatar's position |
| Moving an object | `room:object:move` ([server/main.py:1119](../server/main.py#L1119)) | Emitted from a drag gesture (throttled), not a text input's `input` event |
| Resizing / rotating | `room:object:resize` / `room:object:rotate` ([server/main.py:1140](../server/main.py#L1140), [:1161](../server/main.py#L1161)) | Emitted from on-canvas resize/rotate handles |
| Recoloring / re-material-ing | `room:object:style` ([server/main.py:1182](../server/main.py#L1182)) | Emitted from an on-canvas swatch popover instead of the configure panel's dropdowns |
| Deleting | `room:object:delete` ([server/main.py:2013](../server/main.py#L2013)) | Emitted from a handle on the selection box or the Delete key |
| Deep per-type editing (books, playlists, dialogue, puzzle wiring) | The existing `#configure-controls` type-specific sections ([client/js/main.js:2329](../client/js/main.js#L2329)) | Unchanged — opened from the new floating inspector's "Edit Details…" action |
| Tile add/clone/delete | `room:tile:add/clone/delete` ([client/js/main.js:628-637](../client/js/main.js#L628-L637)) | Unchanged |
| Knowing which tiles exist | `state.roomTiles` / `state.currentTile`, already populated by the `room:tiles` handler ([client/js/main.js:1693](../client/js/main.js#L1693)) and already consumed by `buildMiniMapCells` ([src/world-map.js:11](../src/world-map.js#L11)) | A new pure helper deriving per-edge neighbor booleans from the same data (§10.2) |
| Tile-to-tile movement physics | `detect_edge_transition` / `transition_player_tile_if_needed` ([tile_navigation.py:35](../server/game/tile_navigation.py#L35), [rooms_registry.py:313](../server/game/rooms_registry.py#L313)) | **Unchanged.** Doorway graphics are cosmetic; they render where a transition already works, they never gate one |
| Ambient room look | `ROOM_STYLES` presets ([room-styles.js](../client/js/room-styles.js), [room_styles.py](../server/game/room_styles.py)) | New: exposed as an editable Build Mode section + a small `set_room_style` mutator (§11) |
| M3 visual language | `--md-*` tokens ([styles.css:11-84](../client/css/styles.css#L11-L84)), `.builder-*` classes | New components (`.builder-catalog-*`, `.canvas-selection-*`) built from the same tokens |
| Iconography | `material-symbols-outlined` font, already used app-wide (e.g. `client/index.html:158,392`) | Named glyphs only — `rotate_right`, `palette`, `tune`, `delete`, `grid_on`/`grid_off` — never emoji or bespoke SVG |

## 6. Redesigned Build Panel Layout

### 6.1 Three tabs, not seven sections — and not five either
The single long scrolling sidebar becomes a **tabbed panel**, but per the minimalism goal (§4.6) this design deliberately does *not* turn all seven of today's sections into seven (or even five) permanently-visible tabs — that would just relocate the clutter instead of removing it. Everyday furnishing work needs exactly two tabs; everything a casual builder rarely touches collapses into one:

```
┌ Room Builder ─────────────────────┐
│  Furniture   Room & Doors   More  │  ← M3 Tabs (active-indicator underline,
├────────────────────────────────────┤     not styled buttons — see below)
│  (active tab's content, scrollable) │
└────────────────────────────────────┘
```

- **Furniture** (default tab) — the catalog grid (§7) plus, only while something is selected, a compact read-out of what's selected (name/type) with an "Edit Details…" entry point when applicable (§8.4). This is the tab a builder lands on almost every time they open Build Mode.
- **Room & Doors** — today's Tiles section merged with the new doorway/rail legend (§10) and the Room Style picker (§11) — these are all "what does the room itself look like / how is it shaped" concerns, so they share one tab instead of two.
- **More** — a single overflow entry that expands into an **accordion**, collapsed by default, containing today's Zones, Triggers, Escape Room, Room Admin, and Versions sections as five collapsed rows the builder can individually expand. Nothing here is hidden or removed — it is one click further away than it is today, in exchange for not competing with everyday furnishing for the first thing a builder sees.

This is a real, if small, behavior change from today (where every section is simultaneously visible in one long scroll) and is called out explicitly since the rest of this document otherwise reuses events/engines verbatim: the *content* of every section is unchanged, only how many clicks away it starts.

### 6.2 Component mapping
Every new panel element maps to a specific M3 component, not a generic styled `<div>`:

| UI element | M3 component | Notes |
| --- | --- | --- |
| Furniture / Room & Doors / More | Tabs (with animated active-indicator, `aria-selected`) | Not `.builder-secondary-btn` styled as tabs — a real tab strip so assistive tech announces tab semantics |
| Zones/Triggers/Escape Room/Admin/Versions inside "More" | Accordion (expand/collapse, independently) | Built from `--md-surface-container-low` rows + `--md-outline-variant` dividers, collapsed by default |
| Catalog category selection (§7.1) | Filter chips | New primitive, built from `--md-shape-full` + `--md-secondary-container`; not the existing `.builder-checkbox-field` |
| Catalog cards (§7.1, §9) | Elevated cards | `--md-surface-container` + `--md-elevation-1`, `--md-elevation-2` on hover/drag |
| On-canvas selection toolbar (§8.1) | Icon button row on a small elevated surface | `--md-elevation-2`, `--md-shape-full` pill, each icon button needs a visible tooltip + `aria-label` (§13) |
| Snap-to-grid control (§12) | Icon button (toggle/pressed state), not a checkbox | Single glyph (`grid_on`/`grid_off`), lives in the canvas header, not inside a tab (see §12) |
| Room Style swatches (§11) | Elevated cards, same shape as catalog cards | Reuses the §9 thumbnail-rendering approach |

## 7. Furniture Catalog & Drag-to-Place

### 7.1 Catalog grid
Replace the `object-type-select` + preset dropdowns with a scrollable grid of catalog cards, one per `(objectType, colorPreset)` combination most commonly placed (default color per type shown; color/material become an on-canvas swatch choice after placement, §8.3, so the palette doesn't need a combinatorial explosion of cards). Each card:
```
┌──────────────┐
│  [thumbnail] │  ← canvas-rendered preview (§9), matches in-room look exactly
│   Bookshelf  │
└──────────────┘
```
There is only **one** catalog grid, not a duplicated one per tab. Cards are grouped by `OBJECT_TYPE_CATALOG`'s existing `category` field ("Furniture" for table/chair/bar/sofa, "Interactive" for bookshelf/tv/music_player/ai_character, "Escape Room" for escape_door/hidden_item), and a row of **filter chips** (Tier 2, §4.1 — only shown once the grid is populated, i.e. essentially always, but visually secondary to the grid itself) lets a builder narrow to one category, including Escape Room objects, without ever leaving the Furniture tab or standing up a second catalog implementation. Default state is "All categories, no filter" — the least surprising starting point. A search field inside the same filter row narrows by label; both filter mechanisms operate over the same in-memory card list and emit the identical `room:object:create` event regardless of which chip was active.

### 7.2 Drag from palette to canvas
Each catalog card is made draggable (pointer-based drag, consistent with how canvas object dragging works in §8.2, rather than the HTML5 native DnD API, so both gestures share one implementation and one set of snapping/preview code):
- `pointerdown` on a card starts tracking; once the pointer moves past a small threshold, a translucent preview of the object (the same thumbnail bitmap from §9, at 60% opacity) follows the cursor, hit-tested against the room canvas.
- While the preview is over the canvas, it snaps to the grid if snapping is on (§12). **Correction from an earlier draft of this design:** there is no server-side check today that rejects overlapping objects (confirmed — [room_builder.py](../server/game/room_builder.py) only enforces `MAX_OBJECTS_PER_TILE = 40` per tile, [line 42](../server/game/room_builder.py#L42)/[line 182](../server/game/room_builder.py#L182)), so a red/green "can't place it here" tint would be advertising a rule that doesn't exist. Instead: the preview shows an amber tint only when the destination tile is at or within a few objects of its `MAX_OBJECTS_PER_TILE` budget (a real, existing limit worth surfacing) and otherwise never blocks a drop purely for visually overlapping another object — decoration is allowed to overlap today, and this design doesn't change that.
- On `pointerup` over the canvas: emit `room:object:create` with `{ objectType, x: dropX, y: dropY, sizePreset: <catalog card's default>, color: <catalog card's default>, editPermission }` — same event and payload shape as today ([server/main.py:1084](../server/main.py#L1084)), only the `x`/`y` source changes (drop point instead of avatar position) and `objectType`/`color` come from which card was dragged instead of a `<select>`'s value. If the server rejects the drop (tile budget actually exceeded), the existing `error` event handling applies unchanged.
- On `pointerup` outside the canvas (dropped back onto the palette or missed): cancel, no event emitted.
- Keyboard/accessibility fallback: a card also remains focusable and Enter-activatable, which places the object at the current tile's center point (matching today's avatar-position default when the avatar itself is roughly centered, and well-defined even though this app has no pannable/zoomable "viewport" to speak of) — so nothing is lost for a non-pointer user.

## 8. On-Canvas Selection & Direct Manipulation

### 8.1 Selecting
Clicking an object in build mode still calls into the same hit-testing as today ([`getBuilderObjectAtPoint`](../src/builder-objects.js#L56-L59)), but selecting it now does two things instead of one: it opens the existing type-specific `#configure-controls` section **only when the user asks for it** (an "Edit Details…" button, §8.4), and — new — it draws a **selection overlay directly on the canvas**. Per the minimalism goal (§4.6), this is deliberately *one* small floating toolbar plus the four resize handles a direct-manipulation box needs — not a handle scattered at every corner of the object:
```
         ┌───────────────────────────────────┐
         │ rotate_right  palette  tune  delete │   ← one small pill-shaped
         └───────────────────────────────────┘        M3 toolbar (§6.2), offset
  ┌───┬───────────────────┬───┐                        above the selection box
  │ □ │                   │ □ │  ← corner resize handles (drag directly, no icon needed)
  │   │      (object)     │   │
  │ □ │                   │ □ │
  └───┴───────────────────┴───┘
```
Each toolbar icon is a real `material-symbols-outlined` glyph (`rotate_right`, `palette`, `tune`, `delete` — §3.7), each with a tooltip and `aria-label` (§13), and `tune` (which opens "Edit Details…") only renders for object types that actually have non-spatial config (§8.4) — for a plain `table`/`chair`/`bar`/`sofa` the toolbar is three icons, not four. This overlay is drawn each frame in `client/js/room-renderer.js` (a new `drawSelectionOverlay(ctx, selectedObject)` called after `drawBuilderObjects`) for the resize handles and object outline; the icon toolbar itself is a small absolutely-positioned HTML element (so it can use real DOM tooltips/`aria-label`s rather than being painted into the canvas), repositioned each frame to track the selected object's canvas coordinates. Both are keyed off a `state.selectedBuilderObjectId` the click handler sets — analogous to how `state.currentTile` already drives conditional rendering.

### 8.2 Moving
`pointerdown` inside the selection box (not on a handle) starts a drag: the object's rendered position follows the pointer in real time (purely client-side, instant feedback, no network round-trip needed to *see* the move), snapping to the grid if enabled (§12), and on `pointerup` a single `room:object:move` is emitted with the final position — replacing the current model where every keystroke into an x/y text input fires its own `room:object:move` ([client/js/main.js:800-816](../client/js/main.js#L800-L816)). This is strictly less network traffic than today's per-keystroke emits, not more.

### 8.3 Resizing, rotating, recoloring
- Dragging a **corner handle** live-updates width/height (holding a modifier key, e.g. Shift, preserves aspect ratio); on release, emits `room:object:resize` — same event as today, sourced from a drag instead of two separate number inputs.
- Clicking the toolbar's **`rotate_right`** icon arms a rotate-drag on the object (drag anywhere on the canvas to spin it around its center, live); on release, emits `room:object:rotate` — same event as today.
- Clicking the toolbar's **`palette`** icon opens a small popover showing the 8 color presets and 5 material presets as clickable swatches (reusing `COLOR_PRESETS`/`MATERIAL_PRESETS` from [room_object_catalog.py](../server/game/room_object_catalog.py#L27-L33)) and emits `room:object:style` on click — same event the configure panel already uses ([server/main.py:1182](../server/main.py#L1182)), just triggered from a swatch instead of a dropdown.
- Clicking the toolbar's **`delete`** icon, or pressing Delete/Backspace while an object is selected, emits `room:object:delete` — same event and same `KeyError`/`PermissionError` handling already fixed on the server side.

### 8.4 "Edit Details…" for non-spatial config
Position/size/rotation/color move to the canvas as described above, but content that was never spatial to begin with — which books are on a bookshelf, which video a TV plays, an AI character's dialogue tree, an escape door's unlock rules — has no natural on-canvas representation and stays exactly where it is today: the existing `#configure-controls` type-specific sections ([client/js/main.js:2329](../client/js/main.js#L2329)), reached via the toolbar's **`tune`** icon instead of being auto-opened on every click. Per the progressive-disclosure ladder (§4.1, Tier 3), this icon is only rendered in the toolbar for the object types that actually have such a section today (`bookshelf`, `tv`, `music_player`, `ai_character`, `escape_door`, `hidden_item`) — selecting a plain `table`/`chair`/`bar`/`sofa` never shows a `tune` icon that would just open an empty panel. This is a pure trigger change; none of that panel's markup, fields, or event wiring changes.

### 8.5 Locked / no-permission objects
`isLocked` objects and objects the current user lacks `editPermission` for (existing rules, unchanged) render their selection outline in a muted/disabled style (using `--md-on-surface-variant` at reduced opacity) with the resize handles hidden and the toolbar reduced to just `tune` (read-only "View Details") — consistent with the existing server-side permission checks that would reject the mutation anyway; this simply avoids offering an affordance that would just bounce off an `error` event.

## 9. Catalog & Object Thumbnails

For a card's thumbnail to "look like the thing you're about to place" (§2 principle 1), it should be generated from the **same drawing code** that renders the object in the room, not a hand-drawn icon that could drift out of sync. Concretely: a small offscreen `<canvas>` (created once per distinct `objectType`+`color`+`material` combination and cached) is rendered through the existing per-object drawing path inside `drawBuilderObjects` ([room-renderer.js](../client/js/room-renderer.js)), refactored just enough to accept an arbitrary target context/size instead of assuming the full room canvas — the object-drawing logic itself does not change. The resulting `<canvas>`'s `toDataURL()`/`drawImage` output backs the palette card's `<img>`/`<canvas>` thumbnail. This guarantees the catalog can never show a stale or mismatched preview, at the cost of a small one-time refactor to parameterize the existing draw function's target/scale — flagged as its own checklist item in §16 since it's the one piece of this design touching a shared render function rather than purely adding new code.

## 10. Doorways Instead of Invisible Edges

### 10.1 What this is not
This is **not** the escape-room `escape_door` object type ([room_object_catalog.py:113-121](../server/game/room_object_catalog.py#L113-L121)), which is a *puzzle-gameplay* lock a creator explicitly places and configures with unlock conditions. This design adds a separate, purely cosmetic concept — call it a **tile doorway** — that exists automatically on every edge of every tile wherever a neighboring tile already exists, with zero authoring required. A room can have both: an ordinary tile doorway you always walk through freely between two tiles, and, elsewhere in the room, a builder-placed `escape_door` object that happens to also sit near a tile edge and is puzzle-gated. The two are unrelated and never share code paths.

### 10.2 Computing per-edge neighbor state
A new pure helper, colocated with the existing tile-set logic in [src/world-map.js](../src/world-map.js) (mirrored to `client/js/world-map.js` per this codebase's established `src/` ↔ `client/js/` duplication convention):
```javascript
export function neighborTileFlags(tiles, currentTile) {
  const active = new Set(normalizeTileList(tiles).map(tileKey));
  const { x, y } = currentTile;
  return {
    top:    active.has(tileKey({ x, y: y - 1 })),
    bottom: active.has(tileKey({ x, y: y + 1 })),
    left:   active.has(tileKey({ x: x - 1, y })),
    right:  active.has(tileKey({ x: x + 1, y })),
  };
}
```
This is the exact same `state.roomTiles`/`state.currentTile` pairing `buildMiniMapCells` ([src/world-map.js:11](../src/world-map.js#L11)) already consumes, so no new event or payload is needed — `room-renderer.js`'s draw call simply gains a `neighbors` option computed from data the client already has in `state`.

### 10.3 Rendering: real doors where a wall exists, capped rails where it doesn't
- **Top edge (the only edge with an actual wall today, §3.5):** when `neighbors.top` is true, `drawWall` cuts a rectangular doorway opening into the wall texture at the top-center (replacing a section of the flat wall fill with the backdrop color plus a door-frame outline and a pair of door-leaf graphics drawn slightly ajar, in the room's current style colors from `_activeStyle()`), instead of painting an unbroken wall. When `neighbors.top` is false, the wall renders exactly as it does today (solid, no opening) — a wall with no doorway is itself the correct visual: it already reads as "you can't go this way," no extra cap needed.
- **Left/right/bottom edges (currently no wall at all, §3.5):** this design adds short partial wall "jambs" framing each edge — not a full wall (the room should still read as an open, top-down/dollhouse space, matching the existing wall-only-at-the-top look) but enough painted trim at the very edge to frame an opening. Where `neighbors.<edge>` is true, the jambs frame a gap with a floor threshold strip (a doormat-style rectangle in a slightly darker floor shade, reusing `style.floorDark`) signaling "walk through here." Where `neighbors.<edge>` is false, the jambs close up into a short solid rail/skirting stub across that edge, echoing the existing skirting-board treatment already drawn under the top wall ([room-renderer.js:120-124](../client/js/room-renderer.js#L120-L124)), so a dead-end edge reads as "this is the wall of the room," not "the floor just stops."
- In all cases the doorway/rail graphics are purely decorative, driven only by `neighbors`, and never participate in collision — `detect_edge_transition`/`transition_player_tile_if_needed` (§3.5) are the sole authority on whether a player can actually cross, exactly as today; the graphics simply now agree with that authority instead of contradicting it.

### 10.4 Build-mode-only convenience
While in Build Mode specifically (not during normal play), each doorway/rail is also a clickable hotspot: clicking an existing doorway is a shortcut to walk/warp the builder's own avatar to that neighbor tile for continued editing (a thin client-side convenience using the existing tile-switch flow, not a new server capability), and clicking a **closed** rail on an edge with no neighbor tile yet opens the same "Add Tile" action the Tiles panel's directional buttons already trigger ([client/js/main.js:628](../client/js/main.js#L628)) — so "there's a wall here, want to build a room beyond it?" becomes a single click at the exact spot instead of a disconnected sidebar button. This is presented as an enhancement, not a replacement — the four directional Add-Tile buttons in the Room & Doors tab (§6.1) remain for keyboard/no-canvas-click access.

## 11. Room Style Picker in Build Mode

A **Room Style** section, living inside the Room & Doors tab (§6.1) rather than a tab of its own, shows the existing 5 `ROOM_STYLES` presets ([client/js/room-styles.js](../client/js/room-styles.js)) as clickable preview swatches (small canvas renders of the backdrop/wall/floor gradient combination, generated the same lightweight way as §9's thumbnails), letting a room's owner change the ambience after creation instead of only at the one-time creation dialog. This needs one small, well-scoped server addition:
- `RoomsRegistry.set_room_style(room_id, style_id, requester_id, is_room_host)` — validates via the existing `is_valid_room_style` ([room_styles.py:21](../server/game/room_styles.py#L21)), requires room-host permission (mirroring every other room-wide mutator's `_require_room_host`-equivalent check), stores the new style alongside the existing `room_meta` entry, and returns the resolved style id.
- New `room:style:set` handler in `server/main.py`, following the established handler idiom (`@sio.on(...)` → resolve room/builder → permission-checked call in a `try/except (KeyError, PermissionError, ValueError)` → broadcast → return), broadcasting the new `roomStyle` to every connected client in the room (reusing the existing `roomStyle` field already sent on join, [server/main.py:869](../server/main.py#L869)) so everyone's canvas re-renders with the new palette immediately.
- Client applies the change by re-invoking `drawRoom(canvas, { roomStyle: newStyle })` — the exact same call already made on join ([client/js/main.js:485](../client/js/main.js#L485)) — no renderer changes needed beyond what §10 already introduces.

## 12. Grid Snapping & Alignment

Snapping affects both palette drag-to-place (§7.2) *and* on-canvas dragging of already-placed objects (§8.2) — it is a canvas-wide behavior, not something specific to one tab's content. It is therefore a single toggleable **icon button** (`grid_on`/`grid_off`, default on) living in the canvas header alongside the existing Build Mode toggle, not a checkbox buried inside the Furniture tab where switching to the Room & Doors tab would hide it while a drag is still canvas-wide. When enabled, drop/move positions round to the nearest point on a light 20px grid (matching `EDGE_EPSILON`'s existing 20px unit, [tile_navigation.py:15](../server/game/tile_navigation.py#L15), so snapped positions never fight the edge-transition threshold). When disabled, placement is pixel-precise, matching today's numeric-input behavior. This is purely a client-side rounding step before the same `room:object:create`/`move` payloads are emitted — no server change.

## 13. Accessibility & Fallback Paths

Nothing pointer/drag-only is load-bearing:
- Every catalog card remains keyboard-focusable and Enter-activatable (§7.2).
- The existing numeric X/Y/width/height/rotation inputs in `#configure-controls` remain functional and visible via "Edit Details…" (§8.4) for anyone who prefers or requires precise typed values over dragging.
- Selection can be made via Tab/Enter on the object list that already exists per builder section (e.g. the puzzle/zone/trigger lists), not only by clicking the canvas.
- Color contrast for the new selection overlay, doorway graphics, and rail/skirting trims uses existing `--md-outline`/`--md-primary` tokens, which already meet the app's established contrast bar.
- Every new icon-only control (the selection toolbar's `rotate_right`/`palette`/`tune`/`delete`, §8.1, and the `grid_on`/`grid_off` snap toggle, §12) ships with both a visible tooltip and an `aria-label` — icon-only buttons with no accessible name are a real gap this design must not introduce, since none of the existing icon usages audited in §3.7 are the sole content of an *interactive* control (they all sit beside a text label).
- The "More" accordion (§6.1) uses real disclosure semantics (`aria-expanded` on each row's toggle), so collapsed content is still discoverable by assistive tech, not just visually hidden.

## 14. Event Table (New / Changed)

| Event | Direction | Payload | Notes |
| --- | --- | --- | --- |
| `room:object:create` | client → server | *(unchanged shape)* | `x`/`y` now sourced from a canvas drop point instead of the avatar's position; no server change |
| `room:object:move` | client → server | *(unchanged shape)* | Now emitted once per drag gesture (on release) instead of once per keystroke; no server change |
| `room:object:resize` / `room:object:rotate` / `room:object:style` / `room:object:delete` | client → server | *(unchanged shape)* | Now also triggerable from on-canvas handles/swatches; no server change |
| `room:style:set` | client → server | `{ styleId }` | **New.** Room-host only; validated against `ROOM_STYLE_IDS` |
| `room:style:updated` (or reuse the existing full room-state/join broadcast's `roomStyle` field) | server → room | `{ roomStyle }` | **New broadcast**, or folded into whatever existing state broadcast already carries `roomStyle` on join — implementation detail to confirm against `broadcast_builder_state`'s current payload shape when this lands |

No other new socket events are needed — everything else in this design is client-side rendering and input handling on top of events that already exist.

## 15. What Explicitly Does Not Change

- No new object types, no changes to `OBJECT_TYPE_CATALOG`, `SIZE_PRESETS`, `COLOR_PRESETS`, or `MATERIAL_PRESETS`.
- No changes to `RoomBuilderState`'s permission model (`editPermission`, `isLocked`, `_require_room_host`/`_require_edit_permission`-equivalent checks) — the new on-canvas handles simply call the same guarded methods the configure panel already calls.
- No changes to tile-transition physics (`detect_edge_transition`, `transition_player_tile_if_needed`, `warp_player_to_tile`) — §10's doorways are a rendering layer on top of an already-correct mechanic.
- No changes to the escape-room feature (`escape_door`, `hidden_item`, puzzles, inventory, sessions) — explicitly called out in §10.1 to prevent confusion between the new cosmetic tile doorway and the existing gameplay `escape_door`.
- No new database tables — room style stays in the existing in-memory `room_meta`, matching every other piece of room configuration today.

## 16. Implementation Plan (Tracked Checklist)

### Phase 1 — Visual foundation (no interaction changes yet)
- [ ] Refactor `drawBuilderObjects`' per-object drawing into a function that accepts an arbitrary target context/size, so it can render both the live room and offscreen catalog/style thumbnails (§9) without duplicating drawing code.
- [ ] Add `neighborTileFlags` to `src/world-map.js` (+ mirror to `client/js/world-map.js`) with vitest coverage.
- [ ] Implement doorway/rail rendering in `drawWall` (top edge) and new edge-jamb rendering for left/right/bottom (§10.3), driven by `neighborTileFlags`. Add a visual regression-style unit test if the codebase has a pattern for canvas-drawing tests, otherwise cover `neighborTileFlags` thoroughly and treat the draw calls as manually verified.
- [ ] Tab-ify `#build-controls` into Furniture / Room & Doors / More (§6.1) — the first two are today's content regrouped, "More" is a new collapsed-by-default accordion wrapping Zones, Triggers, Escape Room, Room Admin, and Versions. Pure markup/CSS/JS-toggle change, no behavior change to any contained section.

### Phase 2 — Catalog & drag-to-place
- [ ] Build the single catalog grid UI (§7.1) sourced from the existing client-side type/preset mirror, replacing the type/size/color/material dropdown stack in the Furniture tab, with filter chips (including an "Escape Room" chip) rather than a second, duplicated catalog.
- [ ] Implement pointer-based drag-to-place from a catalog card to the canvas (§7.2), including the placement-preview ghost and the tile-object-budget warning tint (not an overlap-blocking tint — §7.2 correction), emitting the existing `room:object:create` event.
- [ ] Implement the keyboard/Enter fallback placement path (§7.2, §13).

### Phase 3 — On-canvas selection & manipulation
- [ ] Add `state.selectedBuilderObjectId`, `drawSelectionOverlay` (resize handles + outline, §8.1), and the small floating icon-button toolbar (`rotate_right`/`palette`/`tune`/`delete`, conditionally rendered per §8.1/§8.4).
- [ ] Implement drag-to-move on a selected object, emitting `room:object:move` on release (§8.2).
- [ ] Implement resize handles + toolbar-armed rotate drag, emitting `room:object:resize`/`room:object:rotate` on release (§8.3).
- [ ] Implement the swatch popover from the toolbar's `palette` icon, emitting `room:object:style` (§8.3).
- [ ] Implement the toolbar's `delete` icon + Delete/Backspace key, emitting `room:object:delete` (§8.3).
- [ ] Wire the toolbar's `tune` icon to open the existing `#configure-controls` type-specific section unchanged, only for types that have one (§8.4).
- [ ] Muted/disabled selection + reduced-to-`tune`-only toolbar for locked/no-permission objects (§8.5).
- [ ] Tooltips + `aria-label`s on every new icon button (§13).

### Phase 4 — Room Style picker
- [ ] `RoomsRegistry.set_room_style` + `room:style:set` handler, TDD with the same `FakeSio`/`isolate_registry` harness used throughout `tests_python`.
- [ ] Room Style swatch cards inside the Room & Doors tab (§6.1, §11), wired to the new event.

### Phase 5 — Polish
- [ ] Grid snapping icon toggle in the canvas header (§12).
- [ ] Build-mode doorway/rail click shortcuts (§10.4).
- [ ] Catalog filter chips + search field (§7.1).

## 17. Open Questions

1. **Q1 — Broadcast shape for room style changes.** Should `room:style:set` get its own dedicated broadcast event, or should the new style simply flow through whatever event already re-syncs `roomStyle` on join? Needs a look at `broadcast_builder_state`'s current payload at implementation time (§14).
2. **Q2 — Diagonal/other room shapes.** This design keeps the existing strictly-orthogonal 5×5 tile grid (§3.5, `TILE_LIMIT`); it does not add diagonal doorways or non-rectangular rooms. Out of scope unless a future design revisits the tile grid itself.
3. **Q3 — Per-color catalog card explosion.** §7.1 shows one default-colored card per object type and moves color choice to post-placement (§8.3) to avoid a combinatorial catalog. If user feedback wants color visible in the palette itself, the catalog grid would need per-type color sub-swatches — deferred until real usage data exists.
4. **Q4 — Multi-select / group move.** Sims-style building tools often support box-select and moving several objects at once. Not included here; flagged as a natural Phase 6 if single-object drag-and-drop lands well.
5. **Q5 — Undo/redo.** The existing Versions tab (save draft / publish) is the closest existing concept to undo today. A finer-grained per-action undo stack for the new drag interactions is out of scope for this design but would pair naturally with it later.
6. **Q6 — Does the "More" accordion remember which rows were last expanded?** §6.1 collapses Zones/Triggers/Escape Room/Admin/Versions by default on every Build Mode entry for the least-surprising default; a builder actively authoring a puzzle across multiple sessions might prefer their last-expanded row to persist (e.g. in `localStorage`). Deferred — start with always-collapsed and revisit if it proves annoying in practice.
