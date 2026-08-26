# Educational Room Builder and Story World Feature Design

## 1. Product Intent
This feature set turns OmniLaunge into an educational world-building platform where users can:
- Create an avatar and identity.
- Join live rooms created by others.
- Create custom, multi-screen educational spaces.
- Add interactive media and AI story characters.
- Learn by exploring, reading, watching, listening, and conversing.

The core design principle is spatial learning: content is not just listed, it is placed in an environment and discovered through movement.

## 2. Experience Principles
- Learn by exploration, not only by menus.
- Build first, polish later: creators should publish fast.
- Keep interactions readable and simple for first-time users.
- Make educational intent explicit through templates, tags, and guided NPCs.
- Preserve social feel: users should be able to explore together.

## 3. Primary Personas
### 3.1 Room Creator (Teacher / Community Host)
Wants to build a topic-focused environment quickly and update it over time.

### 3.2 Learner / Visitor
Wants to join a room, understand where to go, and consume content with minimal friction.

### 3.3 Story Designer
Wants to place AI characters that guide learners through a predefined narrative or quest.

## 4. End-to-End Journey
1. User enters app.
2. User creates avatar and display name.
3. User lands in lobby chooser.
4. User selects one of two routes:
   - Join Existing Room
   - Create New Room
5. In room, user can move, interact with objects, and follow AI stories.
6. If creator mode, user can edit, save draft, publish, and iterate.

## 5. Entry and Lobby UX
### 5.1 Avatar Creation
Required:
- Display name
- Avatar visual traits

Optional:
- Bio
- Preferred learning topics

Design notes:
- Keep this step under 60 seconds for first-time users.
- Allow randomize button and preset styles.

### 5.2 Lobby Decision Screen
Primary actions:
- Create New Room
- Join Existing Room

Room card fields:
- Room name
- Topic tags
- Host name
- Active users
- Privacy (Public / Invite)
- Estimated duration (optional)

Sorting/filtering:
- Most active
- Newest
- Topic
- Beginner-friendly

## 6. Room Architecture: Multi-Screen World Grid
Each room is a connected grid of screens (tiles). A tile is a playable area with objects and NPCs.

### 6.1 Coordinate Model
- Tile coordinate: (x, y)
- Default spawn tile: (0, 0)
- Neighboring tiles can exist in all directions

### 6.2 Edge Transition Behavior
- Crossing near a tile edge triggers transition if a neighboring tile exists.
- Avatar is moved to opposite edge of destination tile.
- Camera follows to destination tile.

Example:
- Right edge of (0,0) -> left edge of (1,0)
- Bottom edge of (0,0) -> top edge of (0,1)

### 6.3 Transition Styles
- Slide (default)
- Fade
- Narrative card ("Entering Library Wing")

### 6.4 Navigation Aids
- Optional mini-map
- Current tile label
- Objective marker (for story steps)

## 7. Room Builder UX and Authoring Flow
### 7.1 Build Mode vs Play Mode
Build mode:
- Place/edit objects
- Configure media
- Define NPC stories

Play mode:
- Simulate learner experience
- Validate interactions
- Preview transitions

### 7.2 Builder Panels
- Layout panel: tile map editing
- Object panel: furniture and interactives
- Content panel: books/videos/music
- NPC panel: AI character configuration
- Publish panel: metadata, access, version notes

### 7.3 Tile Operations
- Add tile in a direction
- Clone tile
- Delete tile
- Set tile background and ambiance
- Set tile purpose tag (intro, lesson, quiz, lounge)

### 7.4 Object Placement Model
Common object fields:
- id
- type
- tileId
- x, y
- width, height
- rotation
- zIndex
- isLocked
- interactionRadius

Editor controls:
- Snap to grid
- Align/distribute
- Layer up/down
- Duplicate

## 8. Object Catalog and Educational Interactions
### 8.1 Static Furniture
- Tables
- Chairs
- Bars
- Sofas
- Decorative shelves/plants/posters

Primary value: world readability and atmosphere.

### 8.2 Interactive Furniture
- Bookshelf
- TV
- Music Player
- AI Character stands/markers

### 8.3 Style and Dimensions
For each object:
- Preset sizes (S, M, L)
- Custom dimensions
- Color/material presets
- Optional label text

## 9. Content Systems
### 9.1 Bookshelf: Readable Learning Content
Bookshelf supports a collection of books/articles.

Book fields:
- id
- title
- author
- coverUrl
- summary
- readingLevel
- contentType (inline, markdown, external)
- contentBody or externalUrl
- estReadMinutes

Reader behavior:
- Open inline modal or full-screen panel
- Save per-user progress
- "Resume reading" quick action

### 9.2 TV: YouTube Educational Video Embeds
TV supports single videos and playlists.

Video fields:
- id
- title
- youtubeVideoId or youtubeUrl
- playlistId (optional)
- startAtSeconds (optional)
- captionsLang
- isSynchronized

Interaction:
- Open player overlay
- Optional room-synced watch mode
- Optional host controls in live sessions

### 9.3 Music Player: Audio Lessons and Ambience
Music player supports educational audio and ambient context.

Track fields:
- id
- title
- sourceType (youtube, direct)
- sourceUrl
- category (lesson, pronunciation, ambient, story)
- durationSec
- isLooped

Interaction:
- Play/pause
- Playlist navigation
- Optional shared playback state

## 10. AI Characters with Predefined Storytelling
### 10.1 Character Placement and Role
Creators place AI characters per tile and define their role:
- Guide
- Quiz master
- Narrator
- Historical persona
- Mentor

### 10.2 Story Model
Stories are authored as node-based flows.

Story node fields:
- nodeId
- characterLine
- userChoices[]
- nextNodeId per choice
- completionFlag
- optional knowledgeCheck

### 10.3 Conversation UX
- User initiates via click or proximity.
- Dialogue panel opens with character portrait and text.
- User chooses responses or types free text (if enabled).
- Progress is saved.

### 10.4 Educational Patterns
- Museum tour: sequential story path
- Language tutor: practice prompts + corrections
- Mission mode: fetch information from multiple tiles
- Branching dilemma: explain reasoning at checkpoints

## 11. Interaction and Control Model
### 11.1 Object Interaction Contract
Every interactive object should expose:
- interactLabel
- interactionType
- interactionPayload
- cooldown or availability rules

### 11.2 Context Menus
Examples:
- Bookshelf: Browse Books, Continue Reading
- TV: Watch Lesson, Open Playlist
- Music Player: Play Track, View Playlist
- AI Character: Talk, Ask Hint, Start Mission

## 12. Room Creation and Publishing Lifecycle
### 12.1 Draft States
- Draft
- Published
- Archived

### 12.2 Creator Workflow
1. Create room shell.
2. Build tile layout.
3. Place objects.
4. Attach content.
5. Add AI story character(s).
6. Validate in play mode.
7. Publish.

### 12.3 Versioning
- Save snapshot on publish.
- Allow rollback to previous version.
- Show changelog note for collaborators.

## 13. Collaboration, Roles, and Moderation
Roles:
- Owner
- Co-editor
- Moderator
- Participant

Permissions:
- Layout edit
- Content edit
- NPC story edit
- Publish rights
- User moderation rights

Moderation controls:
- Kick/mute/ban in room
- Report content
- Restrict external links

## 14. Functional Requirements
### 14.1 Core
- Avatar creation and persistence
- Room browse, create, join
- Multi-tile movement with edge transitions
- Real-time presence and movement sync

### 14.2 Builder
- Tile graph editing
- Object placement and styling
- Content assignment per object
- Story authoring for AI characters

### 14.3 Learning
- Book reading with progress tracking
- Video and audio playback
- Story progression and completion flags

## 15. Non-Functional Requirements
- Smooth movement and transitions at room scale.
- Builder interactions should feel immediate.
- Safe media embedding and URL validation.
- Persist large rooms without noticeable lag.
- Basic accessibility for reading and interaction panels.

## 16. High-Level Data Domains
- User
- AvatarProfile
- Room
- RoomVersion
- Tile
- RoomObject
- ContentResource (book/video/audio)
- StoryCharacter
- StoryGraphNode
- UserRoomProgress
- Membership / Role

## 17. Metrics and Evaluation
Activation metrics:
- Avatar completion rate
- First room entry rate

Creator metrics:
- % users creating rooms
- Time to first publish
- Average tiles per room

Learning metrics:
- Book opens per session
- Video starts/completions
- Story completion rate
- Return visits to same room

## 18. Delivery Phases
### Phase 1 (MVP)
- Avatar creation
- Join/create room
- Multi-tile navigation
- Basic object placement
- Bookshelf with inline reading
- TV with single YouTube video
- Music player with basic play link
- One linear AI story character

### Phase 2
- Branching story editor
- Playlist support
- Synchronized media playback
- Room templates for educators

### Phase 3
- Analytics dashboard
- Co-editing improvements
- Advanced learning progression and achievements

## 19. Risks and Mitigations
- Risk: creator complexity overwhelms first-time users.
  - Mitigation: starter templates, guided onboarding, quick publish path.
- Risk: media misuse or broken links.
  - Mitigation: URL validation, domain allowlist, report flow.
- Risk: large tile worlds hurt performance.
  - Mitigation: lazy tile loading, object count guidance, performance budgets.

## 20. Alignment Questions for Product Direction
1. Should this feel more like a classroom platform, a social world, or a balanced hybrid?
2. Is the primary audience teachers, students, or independent creators?
3. For MVP, do you want single-screen rooms first, or directly multi-screen tile worlds?
4. Should joining a room be instant, or require room intro/permissions screen?
5. Should AI stories be strictly predefined at first, or allow some live generative answers?
6. Should all TV/music playback be synchronized for everyone in a room by default?
7. Do you want collaborative room editing in MVP, or owner-only editing first?
8. Should books support only text in MVP, or images and embedded quizzes too?
9. What is the preferred max room size for MVP (for example 3x3, 5x5, 10x10 tiles)?
10. Should room creation prioritize speed (few options) or depth (many options) in first release?

## 21. Confirmed Direction (Based on Current Alignment)
### 21.1 Product Positioning
- Experience style: balanced hybrid (social + educational).
- Primary first creators: independent creators and community hosts.
- Room creator role should map to room admin authority.

### 21.2 MVP World Scale
- Maximum room size target: 5x5 tile grid.
- Rationale: supports meaningful world-building without extreme performance risk.

### 21.3 Media Playback Default
- Default behavior: personal playback (not synchronized by default).
- Optional behavior: creator can enable synchronized playback per object in future phase.

### 21.4 Builder Strategy for V1
- Builder direction: depth-first.
- V1 should include richer authoring options rather than a minimal quick builder.

### 21.5 AI Character Behavior Model
Default mode:
- Fully predefined story responses (safe and deterministic).

Optional advanced mode (creator-configured):
- Creator can provide:
  - OpenAI-compatible API base URL
  - API key
  - knowledge base content/source
- If and only if API URL + API key are provided, generative answering can be enabled.
- If missing/invalid, AI remains in predefined-only mode.

Safety and UX requirements for advanced mode:
- API key is never exposed to room visitors.
- API key is stored encrypted on backend for room admin convenience.
- Clear UI toggle: Predefined only / Generative enabled.
- Fallback behavior on API failure: continue with predefined responses.
- Knowledge base scope is character-level only in V1.

## 22. Generative AI Extension Design
### 22.1 Character Runtime Modes
- `predefined_only`
- `predefined_plus_generative`

### 22.2 Suggested Character Config Additions
- `aiMode`
- `apiBaseUrl` (encrypted at rest)
- `apiKeyRef` (secure secret reference)
- `modelName`
- `knowledgeBaseId`
- `temperature`
- `maxTokens`
- `fallbackToPredefined` (boolean)

### 22.3 Knowledge Base Shape (High-Level)
- `knowledgeBaseId`
- `title`
- `documents[]` (text, markdown, links)
- `embeddingEnabled` (future)
- `updatedAt`

### 22.4 Request Pipeline (Conceptual)
1. User asks AI character.
2. System checks character mode.
3. If predefined_only: return story-script response.
4. If predefined_plus_generative:
   - Validate API config.
   - Build prompt with story context + knowledge snippets.
   - Call creator-defined OpenAI-compatible endpoint.
   - Return answer.
   - If call fails, fallback to predefined response.

### 22.5 Moderation Baseline for Generative Mode
- Creator-visible warning when enabling custom API mode.
- Output guardrails (length, topic bounds, blocked terms where applicable).
- Logging for debugging (without exposing secrets).

## 23. Follow-Up Questions to Finalize the Spec
1. Should generative mode be available to all creators, or only verified/approved creators?
2. Do you want API keys stored in OmniLaunge backend (encrypted secrets), or entered per session and never stored?
3. Should knowledge base be room-level shared data, character-level isolated data, or both?
4. For the 5x5 limit, should every room start at 1x1 and expand manually, or choose initial size upfront?
5. In depth-first builder V1, which advanced controls are mandatory at launch: layering, collision zones, scripted triggers, or timeline sequencing?
6. Should visitors see an indicator when a character is in predefined mode vs generative mode?
7. For personal media playback default, should there be a "watch/listen together" button users can opt into live?

## 24. Finalized Decisions (Current)
### 24.1 Roles and Admin Model
- Room creator is room admin.
- Room admin owns advanced AI configuration for that room.

### 24.2 Secrets and API Configuration
- OpenAI-compatible API keys are stored encrypted on backend.
- API keys are never sent to clients beyond secure server-side use.

### 24.3 Knowledge Base Scope
- V1 generative context uses character-level knowledge bases only.
- No shared room-level KB in V1.

### 24.4 Depth-First MVP Builder Priorities
Mandatory advanced features for V1:
- Layering and z-index editor.
- Collision and interaction zones.
- Scripted triggers (for example: entering an area triggers event/dialogue).

Deferred from mandatory MVP:
- Timeline sequencing for choreographed events.

### 24.5 Media Interaction Mode
- Default is personal playback.
- Include opt-in synchronized mode via "Watch/Listen together" action.

## 25. Implementation Plan Checklist

Use this section as the delivery tracker. Mark each item complete as work lands in code, tests, and deployment.

### Phase A: Foundation and Data Model
- [x] Create DB schema updates for rooms, tiles, room objects, content resources, story nodes, and role mappings.
- [x] Add room versioning tables and publish snapshot support.
- [x] Add secure secrets storage for room-admin AI API configuration.
- [x] Add migrations and rollback scripts for all new schema changes.
- [x] Add backend validation models for object placement, tile boundaries, and content payloads.

### Phase B: Entry Flow and Room Discovery
- [x] Implement avatar-first entry flow with create avatar and continue actions.
- [x] Implement lobby chooser with Create New Room and Join Existing Room.
- [x] Implement room list API with filtering (topic, activity, access type).
- [x] Implement room join flow (public and invite/private).
- [x] Add client-side room cards with host, tags, users, and privacy indicators.

### Phase C: Multi-Tile World Navigation (5x5 MVP)
- [x] Implement tile coordinate model and room spawn tile handling.
- [x] Implement edge transition detection (left, right, top, bottom).
- [x] Implement transition to neighbor tile and opposite-edge spawn.
- [x] Enforce MVP max world size of 5x5 tiles.
- [x] Add mini-map and current tile indicator in UI.
- [x] Add tests for tile transitions, invalid neighbors, and boundary behavior.

### Phase D: Depth-First Room Builder
- [x] Build mode and play mode toggle with clear UI separation.
- [x] Add tile graph editor: add, clone, delete, and configure tile visuals.
- [x] Add object placement tools with drag, resize, rotate, duplicate, and lock.
      (Move/resize/rotate use accessible numeric form controls in the builder
      panel rather than mouse drag, for a tractable, HIG-consistent MVP.)
- [x] Add layering and z-index controls (mandatory MVP feature).
- [x] Add collision and interaction zone editor (mandatory MVP feature).
- [x] Add scripted trigger editor for area-enter events (mandatory MVP feature).
      (Authoring/CRUD only in the builder panel; runtime firing during live
      gameplay movement is deferred to Phase H, AI Characters and Story Engine.)
- [x] Add save draft, publish, and rollback to previous snapshot actions.

### Phase E: Interactive Educational Objects
- [x] Implement object types: tables, chairs, bars, bookshelves, sofas, TVs, music players.
- [x] Implement object style settings: size presets, custom size, and color/material choices.
- [x] Implement contextual interaction menus per object type.
- [x] Add object-level permissions for edit and interaction configuration.
      (Lightweight owner/anyone edit permission + room-host override; full
      RBAC with owner/editor/moderator/viewer roles is deferred to Phase I.)
- [x] Add tests for object CRUD, render placement, and interaction payloads.

### Phase F: Bookshelf Learning System
- [x] Implement book resource model (title, author, summary, content source, read progress).
- [x] Implement reader UI (inline modal; scroll-tracked progress bar). Full-screen mode deferred — the modal is scoped to MVP reading needs.
- [x] Implement per-user reading progress tracking and resume behavior.
- [x] Add validation for allowed content types (inline and markdown for MVP).
- [x] Add tests for read progress persistence and reader navigation.

### Phase G: TV and Music Learning Media
- [x] Implement TV content model with YouTube video support.
- [x] Implement music player content model with linked educational tracks.
- [x] Implement personal playback as default mode.
- [x] Implement opt-in Watch/Listen together synchronization flow.
- [x] Add moderation and URL validation for media sources (server-side YouTube-id regex is the enforced boundary; MVP restricts sources to YouTube only, client-side URL parsing gives immediate feedback but is not trusted).
- [x] Add tests for playback controls and sync opt-in behavior.

### Phase H: AI Characters and Story Engine
- [x] Implement AI character placement and role assignment per tile.
- [x] Implement predefined story graph runtime (nodes, choices, next-step routing).
- [x] Implement character-level knowledge base model and editor.
- [x] Implement default predefined-only runtime mode.
- [x] Implement optional generative mode gated by room-admin API URL and key.
- [x] Implement server-side secure call flow to OpenAI-compatible endpoint.
- [x] Implement fallback to predefined responses on API failure.
- [x] Add clear UI indicator of character mode (predefined vs generative).
- [x] Add tests for story progression, fallback behavior, and permissions.

### Phase I: Roles, Permissions, and Moderation
- [x] Implement room-admin role assignment to room creator.
- [x] Implement co-editor, moderator, participant role capabilities.
- [x] Restrict AI API settings management to room admin.
- [x] Implement moderation tools: mute, kick, ban, and content reporting.
- [x] Add policy controls for external content restrictions.
- [x] Add audit logs for critical admin and moderation actions.

### Phase J: Non-Functional Hardening
- [x] Add performance budgets for tile/object counts and render cost.
- [ ] Implement lazy tile/object loading where needed.
- [x] Add accessibility pass for reader, dialog, and builder controls.
- [x] Add rate limiting and abuse protections for generative requests.
- [ ] Add observability dashboards for latency, errors, and usage metrics.

### Phase K: QA, UAT, and Release
- [ ] Expand automated tests across frontend, backend, and integration paths.
- [ ] Run end-to-end scenarios for creator and learner journeys.
- [ ] Validate migration safety in staging with rollback drills.
- [ ] Run security review for secrets handling and external API proxying.
- [ ] Conduct beta with selected creators and collect feedback.
- [ ] Apply launch fixes and publish MVP release notes.

### Ongoing Tracking Fields
- [ ] Assign owner for each phase (engineering/design/product).
- [ ] Add target milestone date for each phase.
- [ ] Add weekly status update cadence.
- [ ] Track blockers and dependency risks.
