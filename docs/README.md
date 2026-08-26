# OmniLaunge Documentation Index

This folder is the main documentation hub for OmniLaunge. It is intentionally split by feature area and by system functionality so that product readers, contributors, and maintainers can find the right depth quickly without scanning one huge file.

If you are new to the project, start with the user journey document and then move to architecture and runtime internals. If you are preparing to modify behavior, read the feature-specific document first, then the event and persistence references.

## Reading Paths

The first path is for product and UX understanding. Read [01-user-experience.md](01-user-experience.md), then [02-room-interactions.md](02-room-interactions.md), and then [03-combat-and-ai.md](03-combat-and-ai.md).

The second path is for technical implementation and contribution work. Read [04-system-architecture.md](04-system-architecture.md), then [05-backend-runtime.md](05-backend-runtime.md), and then [06-data-events-and-storage.md](06-data-events-and-storage.md).

The third path is for quality and operations work. Read [07-testing-operations-and-release.md](07-testing-operations-and-release.md).

## Full Index

- [01-user-experience.md](01-user-experience.md)
- [02-room-interactions.md](02-room-interactions.md)
- [03-combat-and-ai.md](03-combat-and-ai.md)
- [04-system-architecture.md](04-system-architecture.md)
- [05-backend-runtime.md](05-backend-runtime.md)
- [06-data-events-and-storage.md](06-data-events-and-storage.md)
- [07-testing-operations-and-release.md](07-testing-operations-and-release.md)

## Scope Note

These docs describe the currently implemented OmniLaunge runtime and also clarify boundaries between implemented behavior and roadmap design artifacts. For future educational world-builder expansion plans, see [feature_designs/educational_rooms_feature_design.md](../feature_designs/educational_rooms_feature_design.md).

Current implementation status has advanced beyond a single fixed lobby. Basic multi-room foundation now exists in the backend with create/list/join events, server-side join guards (room full and invite-code checks), and room list filtering by topic, access, and activity/newest sorting. The client now includes a room chooser overlay with create/join flows and filter controls.

Phase A foundation is now in place in the data layer: schema tables for rooms/tiles/objects/resources/story nodes/roles, versioning and publish snapshots, room-admin secret storage, and paired up/down migration scripts. Runtime movement reliability was also improved by making avatar spawn choose non-obstacle positions.

Runtime movement/state broadcast is now room-aware instead of lobby-only, which fixes the issue where users could still perform combat actions but not move after switching out of lobby contexts. Phase C foundational tile-navigation utilities are also implemented and tested (edge detection, neighbor transitions, and 5x5 world bounds enforcement).

Phase C is now visible in the player HUD through a current tile indicator and mini-map. Phase D has started with a build-mode toggle and directional tile-add controls, backed by server events and room tile graph updates.