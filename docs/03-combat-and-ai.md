# Combat, Stamina, and AI Bot Behavior

Combat in OmniLaunge has three coordinated layers: client-side input and animation start, server-side authority and validation, and client-side reconciliation through events. This keeps controls responsive while preserving deterministic multiplayer outcomes.

Users can trigger punch, kick, and block from keyboard shortcuts. Punch and kick begin immediately as local animation, including air attacks when no valid target is in range. The server decides whether a hit exists and whether damage should be applied. Blocking state is represented continuously while the key is held.

Stamina and damage rules are defined on the backend. Punch and kick have distinct damage values, stamina costs, ranges, and cooldown windows. Blocking reduces incoming damage. When stamina reaches zero, the target enters a stun state for a long duration and cannot move or attack until the stun window expires.

The animation layer uses curve-driven limb rotation with directional awareness. Punches and kicks use phase curves so movement feels like wind-up, extension, and retract rather than binary pose swaps. A key implementation detail is that SVG limb swing direction depends on sign convention around top pivots, and this is now explicitly tested to prevent inverted motion regressions.

RoboFighter, the AI bot, is integrated into the same authoritative game loop and follows practical combat heuristics. It chooses nearest targets, approaches when outside attack range, blocks with probability, and chooses punch versus kick using weighted randomness. It can also send periodic taunt messages when near players.

```mermaid
sequenceDiagram
  participant U as User Input
  participant C as Client Combat UI
  participant S as Server Combat Handler
  participant R as Client Renderer
  participant A as AI Bot

  U->>C: Space/Ctrl/Cmd/B
  C->>R: Start local attack or block animation
  C->>S: combat:attack or combat:block
  S->>S: Validate stun/range/cooldown/stamina
  alt Valid hit
    S-->>R: combat:hit event
    R->>R: Update stamina bars and hit/KO states
  else No valid hit
    S-->>R: No combat:hit emitted
    R->>R: Local animation completes only
  end

  loop game tick
    S->>A: tick(players, now)
    A-->>S: optional attack intent
    S->>S: apply AI combat rules
    S-->>R: room:state + combat:hit if any
  end
```

Because combat spans both prediction-like local animation and strict server validation, contributors should always test both gameplay correctness and visual directionality when touching these modules.