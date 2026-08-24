# User Experience and Player Journey

OmniLaunge currently delivers a complete single-room social experience that starts with identity creation and quickly transitions into shared real-time interaction. The first contact is the avatar creator, where users choose a display name and visual traits including skin tone, hair style, beard style, glasses, clothes, and accessory options. The preview is live-rendered, so what users see in the creator is a faithful representation of their in-room appearance.

Once users enter the lounge, they now see a room chooser overlay that supports two core pathways: creating a new room and joining an existing room discovered from the server. If the user chooses not to switch immediately, they can continue in the default lobby. This gives the experience a transitional step toward the educational multi-room future while keeping the current social flow intact.

After room selection, users move from setup into active multiplayer presence. The room conveys social activity through movement, layered avatar rendering, and chat visibility. Public messages appear in the chat panel and as short-lived speech bubbles above avatars, while private messages preserve one-to-one visibility.

Movement supports two equally valid patterns. One pattern is directional movement using arrow keys for continuous control. The other pattern is click-to-walk, which lets users place intent targets in room space and watch the avatar move there with collision-aware path behavior. This duality supports both game-like control and relaxed social navigation.

The room also has interaction affordances that feel embedded in the space rather than abstracted into global menus. Clicking an interactive object opens a radial context wheel at the interaction point. The available actions are object-specific, so users can sit on sofas, lounge, dance near the DJ deck, or climb onto the table where the object behavior permits teleport-style positioning. The experience is expressive because actions are attached to physical room context and avatar state.

Combat is integrated as an optional interaction mode rather than a separate game screen. Users can punch with Space, kick with Ctrl or Cmd, and hold block with B. The visual layer shows attack and defense motion immediately, while gameplay outcomes are computed by the server based on range, cooldown, stamina, and stun conditions. This produces a responsive feel without sacrificing multiplayer fairness.

The AI bot adds activity when the room has low human traffic. RoboFighter can move, taunt in public chat, block, and attack. This gives solo users a way to test mechanics and keeps the room from feeling empty.

From a user perspective, the core value already present in OmniLaunge is this combination of social presence, expressive avatar behavior, lightweight action systems, and now early room-level discovery/selection in a single coherent loop.