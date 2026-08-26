import { io } from 'socket.io-client';
import { AVATAR_OPTIONS, renderAvatarSVG } from './avatar-renderer.js';
import { drawRoom, canvasToRoomCoords, setBuilderObjects } from './room-renderer.js';
import { advanceWalkPhase } from './animation.js';
import { getObjectAtPoint } from './room-objects.js';
import { getBuilderObjectAtPoint, buildInteractionActions, objectTypeIcon } from './builder-objects.js';
import { showRadialMenu, dismissRadialMenu, hasActiveMenu } from './radial-menu.js';
import { initCombat, destroyCombat, isBlocking } from './combat-ui.js';
import { ATTACK_DURATIONS, computeAttackPhase, getPunchAngles, getKickAngles, getBlockAngles } from './attack-anim.js';
import { normalizeRooms, buildRoomMetaLine, canJoinRoom, normalizeRoomFilters } from './room-discovery.js';
import { buildMiniMapCells, normalizeTileList } from './world-map.js';
import { clampProgress, computeScrollProgress, formatEstReadTime, renderBookContent, truncateSummary } from './reader.js';
import { extractYoutubeVideoId, computeSyncPosition, formatDuration, sessionAppliesToItem } from './media.js';
import { formatModeLabel, parseChoicesInput, resolveCharacterMode } from './story.js';
import { ASSIGNABLE_ROLES, formatRoleLabel, canAssignRoles, canModerate } from './moderation.js';

const BUBBLE_DURATION = 6000;

const state = {
  avatar: {
    username: '',
    skinColor: AVATAR_OPTIONS.skinColors[0],
    gender: AVATAR_OPTIONS.gender[0],
    hair: AVATAR_OPTIONS.hair[0],
    beard: 'none',
    glasses: 'none',
    clothes: AVATAR_OPTIONS.clothes[0],
    accessory: 'none',
  },
  playerId: null,
  players: new Map(),
  activeBubbles: new Map(),
  walkPhases: new Map(),   // playerId → { phase, lastX, lastY }
  talkingUntil: new Map(), // playerId → timestamp ms
  blinkDelay: new Map(),   // playerId → css delay string
  actionStates: new Map(), // playerId → actionState string|null
  playerStamina: new Map(), // playerId → number 0-100
  playerBlocking: new Map(), // playerId → bool
  playerStunned: new Map(),  // playerId → stunnedUntil ms
  hitFlash: new Map(),       // playerId → expiry ms
  attackAnim: new Map(),     // playerId → { type, startMs, duration, facingRight }
  blockAnim: new Map(),      // playerId → { phase, entering, startMs }
  wasStunned: new Map(),     // playerId → bool (previous frame)
  wakingUpUntil: new Map(),  // playerId → timestamp ms
  chatMode: 'public',
  roomList: [],
  roomFilters: { topic: '', access: 'all', sort: 'newest' },
  currentRoomId: 'lobby',
  currentTile: { x: 0, y: 0 },
  roomTiles: [{ x: 0, y: 0 }],
  buildMode: false,
  builderState: { tiles: [], objects: [], zones: [], triggers: [] },
  builderVersions: [],
  builderBooks: {},       // objectId → books[]
  readerModalObjectId: null,
  readerCurrentBook: null,
  readerCurrentProgress: 0,
  suppressReaderModalForBrowse: false,
  builderVideos: {},      // objectId → videos[]
  builderTracks: {},      // objectId → tracks[]
  mediaModalObjectId: null,
  mediaModalObjectType: null, // 'tv' | 'music_player'
  mediaCurrentItem: null,
  mediaSyncSession: null,
  suppressMediaModalForBrowse: false,
  builderCharacters: {},  // objectId → character config
  builderStoryNodes: {},  // objectId → nodes[]
  dialogueModalObjectId: null,
  dialogueCurrentNode: null,
  roomHostId: null,
  myRoomRole: 'participant',
  playerRoles: new Map(),  // playerId → role (populated via room:role:updated)
  mutedPlayers: new Set(), // playerId set (populated via room:moderation:muted)
  socket: null,
  keys: { ArrowUp: false, ArrowDown: false, ArrowLeft: false, ArrowRight: false },
  gameLoopId: null,
};

const creatorScreen = document.getElementById('creator-screen');
const gameScreen = document.getElementById('game-screen');
const themeToggleBtn = document.getElementById('theme-toggle');
const avatarPreview = document.getElementById('avatar-preview');
const usernameInput = document.getElementById('username-input');
const enterRoomBtn = document.getElementById('enter-room-btn');
const roomCanvas = document.getElementById('room-canvas');
const playersLayer = document.getElementById('players-layer');
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const recipientSelect = document.getElementById('recipient-select');
const recipientDropdown = document.getElementById('recipient-dropdown');
const onlineCount = document.getElementById('online-count');
const roomChooser = document.getElementById('room-chooser');
const roomChooserClose = document.getElementById('room-chooser-close');
const roomListEl = document.getElementById('room-list');
const roomCreateName = document.getElementById('room-create-name');
const roomCreateTags = document.getElementById('room-create-tags');
const roomCreateBtn = document.getElementById('room-create-btn');
const roomRefreshBtn = document.getElementById('room-refresh-btn');
const roomFilterTopic = document.getElementById('room-filter-topic');
const roomFilterAccess = document.getElementById('room-filter-access');
const roomFilterSort = document.getElementById('room-filter-sort');
const roomInviteCode = document.getElementById('room-invite-code');
const currentTileLabel = document.getElementById('current-tile-label');
const miniMapEl = document.getElementById('mini-map');
const buildModeToggle = document.getElementById('build-mode-toggle');
const buildControls = document.getElementById('build-controls');
const tileCloneBtn = document.getElementById('tile-clone-btn');
const tileDeleteBtn = document.getElementById('tile-delete-btn');
const tileLabelInput = document.getElementById('tile-label-input');
const tilePurposeSelect = document.getElementById('tile-purpose-select');
const tileConfigureBtn = document.getElementById('tile-configure-btn');
const objectTypeSelect = document.getElementById('object-type-select');
const objectSizeSelect = document.getElementById('object-size-select');
const objectColorSelect = document.getElementById('object-color-select');
const objectMaterialSelect = document.getElementById('object-material-select');
const objectEditAnyoneInput = document.getElementById('object-edit-anyone-input');
const objectAddBtn = document.getElementById('object-add-btn');
const objectListEl = document.getElementById('object-list');
const zoneTypeSelect = document.getElementById('zone-type-select');
const zoneMinX = document.getElementById('zone-min-x');
const zoneMinY = document.getElementById('zone-min-y');
const zoneMaxX = document.getElementById('zone-max-x');
const zoneMaxY = document.getElementById('zone-max-y');
const zoneAddBtn = document.getElementById('zone-add-btn');
const zoneListEl = document.getElementById('zone-list');
const triggerZoneSelect = document.getElementById('trigger-zone-select');
const triggerEventInput = document.getElementById('trigger-event-input');
const triggerRepeatableInput = document.getElementById('trigger-repeatable-input');
const triggerAddBtn = document.getElementById('trigger-add-btn');
const triggerListEl = document.getElementById('trigger-list');
const versionSaveBtn = document.getElementById('version-save-btn');
const versionPublishBtn = document.getElementById('version-publish-btn');
const versionListEl = document.getElementById('version-list');
const moderationSection = document.getElementById('moderation-section');
const externalLinksField = document.getElementById('external-links-field');
const externalLinksInput = document.getElementById('external-links-input');
const moderationPlayerListEl = document.getElementById('moderation-player-list');
const auditLogBtn = document.getElementById('audit-log-btn');
const auditLogListEl = document.getElementById('audit-log-list');
const bookShelfSelect = document.getElementById('book-shelf-select');
const bookTitleInput = document.getElementById('book-title-input');
const bookAuthorInput = document.getElementById('book-author-input');
const bookSummaryInput = document.getElementById('book-summary-input');
const bookContentTypeSelect = document.getElementById('book-content-type-select');
const bookContentInput = document.getElementById('book-content-input');
const bookAddBtn = document.getElementById('book-add-btn');
const bookListEl = document.getElementById('book-list');
const readerModal = document.getElementById('reader-modal');
const readerModalTitle = document.getElementById('reader-modal-title');
const readerModalClose = document.getElementById('reader-modal-close');
const readerBookListView = document.getElementById('reader-book-list-view');
const readerBookList = document.getElementById('reader-book-list');
const readerBookView = document.getElementById('reader-book-view');
const readerBackBtn = document.getElementById('reader-back-btn');
const readerBookTitle = document.getElementById('reader-book-title');
const readerBookMeta = document.getElementById('reader-book-meta');
const readerBookProgressFill = document.getElementById('reader-book-progress-fill');
const readerBookContent = document.getElementById('reader-book-content');
const videoTvSelect = document.getElementById('video-tv-select');
const videoTitleInput = document.getElementById('video-title-input');
const videoYoutubeInput = document.getElementById('video-youtube-input');
const videoDescriptionInput = document.getElementById('video-description-input');
const videoAddBtn = document.getElementById('video-add-btn');
const videoListEl = document.getElementById('video-list');
const trackPlayerSelect = document.getElementById('track-player-select');
const trackTitleInput = document.getElementById('track-title-input');
const trackArtistInput = document.getElementById('track-artist-input');
const trackYoutubeInput = document.getElementById('track-youtube-input');
const trackAddBtn = document.getElementById('track-add-btn');
const trackListEl = document.getElementById('track-list');
const mediaModal = document.getElementById('media-modal');
const mediaModalTitle = document.getElementById('media-modal-title');
const mediaModalClose = document.getElementById('media-modal-close');
const mediaPlaylistView = document.getElementById('media-playlist-view');
const mediaPlaylistList = document.getElementById('media-playlist-list');
const mediaPlayerView = document.getElementById('media-player-view');
const mediaBackBtn = document.getElementById('media-back-btn');
const mediaItemTitle = document.getElementById('media-item-title');
const mediaItemMeta = document.getElementById('media-item-meta');
const mediaVideoFrame = document.getElementById('media-video-frame');
const mediaSyncStatus = document.getElementById('media-sync-status');
const mediaSyncToggleBtn = document.getElementById('media-sync-toggle-btn');
const characterNpcSelect = document.getElementById('character-npc-select');
const characterNameInput = document.getElementById('character-name-input');
const characterRoleSelect = document.getElementById('character-role-select');
const characterStartNodeInput = document.getElementById('character-start-node-input');
const characterPortraitInput = document.getElementById('character-portrait-input');
const characterConfigureBtn = document.getElementById('character-configure-btn');
const characterKnowledgeBaseInput = document.getElementById('character-knowledge-base-input');
const characterKnowledgeBaseBtn = document.getElementById('character-knowledge-base-btn');
const characterApiUrlInput = document.getElementById('character-api-url-input');
const characterApiKeyInput = document.getElementById('character-api-key-input');
const characterGenerativeBtn = document.getElementById('character-generative-btn');
const storyNodeIdInput = document.getElementById('story-node-id-input');
const storyNodeLineInput = document.getElementById('story-node-line-input');
const storyNodeChoicesInput = document.getElementById('story-node-choices-input');
const storyNodeAddBtn = document.getElementById('story-node-add-btn');
const storyNodeListEl = document.getElementById('story-node-list');
const dialogueModal = document.getElementById('dialogue-modal');
const dialogueModalTitle = document.getElementById('dialogue-modal-title');
const dialogueModalClose = document.getElementById('dialogue-modal-close');
const dialogueModeIndicator = document.getElementById('dialogue-mode-indicator');
const dialogueCharacterLine = document.getElementById('dialogue-character-line');
const dialogueChoiceList = document.getElementById('dialogue-choice-list');
const dialogueAskForm = document.getElementById('dialogue-ask-form');
const dialogueAskInput = document.getElementById('dialogue-ask-input');
const dialogueAnswer = document.getElementById('dialogue-answer');
const dialogueRestartBtn = document.getElementById('dialogue-restart-btn');

function initCreator() {
  buildColorSwatches();
  buildOptionButtons('gender-options', AVATAR_OPTIONS.gender, 'gender');
  buildOptionButtons('hair-options', AVATAR_OPTIONS.hair, 'hair');
  buildOptionButtons('beard-options', AVATAR_OPTIONS.beards, 'beard');
  buildOptionButtons('glasses-options', AVATAR_OPTIONS.glasses, 'glasses');
  buildOptionButtons('clothes-options', AVATAR_OPTIONS.clothes, 'clothes');
  buildOptionButtons('accessory-options', AVATAR_OPTIONS.accessories, 'accessory');

  usernameInput.addEventListener('input', () => {
    state.avatar.username = usernameInput.value.trim();
    enterRoomBtn.disabled = state.avatar.username.length === 0;
  });

  enterRoomBtn.addEventListener('click', enterRoom);
  updateAvatarPreview();
}

function buildColorSwatches() {
  const container = document.getElementById('skin-colors');
  AVATAR_OPTIONS.skinColors.forEach(color => {
    const swatch = document.createElement('button');
    swatch.className = 'color-swatch' + (color === state.avatar.skinColor ? ' selected' : '');
    swatch.style.backgroundColor = color;
    swatch.title = color;
    swatch.addEventListener('click', () => {
      state.avatar.skinColor = color;
      container.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('selected'));
      swatch.classList.add('selected');
      updateAvatarPreview();
    });
    container.appendChild(swatch);
  });
}

function buildOptionButtons(containerId, options, field) {
  const container = document.getElementById(containerId);
  options.forEach(option => {
    const btn = document.createElement('button');
    btn.className = 'option-btn' + (option === state.avatar[field] ? ' selected' : '');
    btn.textContent = option;
    btn.addEventListener('click', () => {
      state.avatar[field] = option;
      container.querySelectorAll('.option-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      updateAvatarPreview();
    });
    container.appendChild(btn);
  });
}

function updateAvatarPreview() {
  avatarPreview.innerHTML = renderAvatarSVG(state.avatar, 'large');
}

function enterRoom() {
  if (!state.avatar.username) return;
  creatorScreen.classList.remove('active');
  gameScreen.classList.add('active');
  initGame();
  connectSocket();
}

function initGame() {
  drawRoom(roomCanvas);
  updateBuildModeUi();
  renderMiniMap();
  updateCurrentTileLabel();

  roomCanvas.addEventListener('click', (e) => {
    const coords = canvasToRoomCoords(roomCanvas, e.clientX, e.clientY);

    // If clicking on a hardcoded interactive lobby object, show its radial menu
    const obj = getObjectAtPoint(coords.x, coords.y);
    if (obj) {
      showRadialMenu(playersLayer, coords.x, coords.y, obj, (action) => {
        state.socket?.emit('player:action', {
          actionState: action.actionState,
          target: action.target,
          teleport: action.actionState === 'on-table',
        });
      });
      return;  // don't move player
    }

    // If clicking on a builder-placed object, show its interaction menu (Phase E)
    const builderObj = getBuilderObjectAtPoint(currentTileBuilderObjects(), coords.x, coords.y);
    if (builderObj && builderObj.isInteractable && builderObj.interactions?.length) {
      const menuObj = {
        icon: objectTypeIcon(builderObj.objectType),
        label: builderObj.objectType,
        actions: buildInteractionActions(builderObj.interactions),
      };
      showRadialMenu(playersLayer, coords.x, coords.y, menuObj, (action) => {
        state.socket?.emit('room:object:interact', {
          objectId: builderObj.objectId,
          interactionType: action.interactionType,
        });
      });
      return;  // don't move player
    }

    // Otherwise move the player
    dismissRadialMenu();
    state.socket?.emit('player:move', coords);
    clearKeyboardDirection();
    spawnClickMarker(coords.x, coords.y);
  });

  // Escape dismisses the menu
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') dismissRadialMenu();
  });

  document.getElementById('mode-public').addEventListener('click', () => setChatMode('public'));
  document.getElementById('mode-private').addEventListener('click', () => setChatMode('private'));
  chatForm.addEventListener('submit', (e) => { e.preventDefault(); sendMessage(); });

  chatMessages.addEventListener('click', (evt) => {
    const btn = evt.target.closest('button.chat-report-btn');
    if (!btn) return;
    const messageId = btn.getAttribute('data-message-id');
    if (!messageId) return;
    const reason = window.prompt('Report this message. Reason (optional):', '') || '';
    state.socket?.emit('room:moderation:report', { targetType: 'chat_message', targetId: messageId, reason });
  });

  // Show talking animation while typing in chat box
  chatInput.addEventListener('input', () => {
    if (state.playerId && chatInput.value.trim()) {
      state.talkingUntil.set(state.playerId, Date.now() + 1500);
    }
  });

  roomChooserClose.addEventListener('click', () => {
    roomChooser.classList.add('hidden');
  });

  roomCreateBtn.addEventListener('click', () => {
    const name = roomCreateName.value.trim();
    if (!name) return;
    const topicTags = roomCreateTags.value
      .split(',')
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    state.socket?.emit('room:create', {
      name,
      topicTags,
      access: 'public',
      maxUsers: 30,
    });
  });

  roomRefreshBtn.addEventListener('click', () => {
    requestRoomList();
  });

  roomFilterTopic?.addEventListener('input', () => requestRoomList());
  roomFilterAccess?.addEventListener('change', () => requestRoomList());
  roomFilterSort?.addEventListener('change', () => requestRoomList());

  buildModeToggle?.addEventListener('click', () => {
    state.buildMode = !state.buildMode;
    updateBuildModeUi();
    if (state.buildMode) {
      state.socket?.emit('room:builder:request', {});
    }
  });

  buildControls?.querySelectorAll('button[data-dir]').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (!state.buildMode) return;
      const direction = btn.getAttribute('data-dir');
      if (!direction) return;
      state.socket?.emit('room:tile:add', { direction });
    });
  });

  tileCloneBtn?.addEventListener('click', () => {
    state.socket?.emit('room:tile:clone', { direction: 'right' });
  });

  tileDeleteBtn?.addEventListener('click', () => {
    state.socket?.emit('room:tile:delete', { x: state.currentTile.x, y: state.currentTile.y });
  });

  tileConfigureBtn?.addEventListener('click', () => {
    state.socket?.emit('room:tile:configure', {
      x: state.currentTile.x,
      y: state.currentTile.y,
      label: tileLabelInput?.value || undefined,
      purposeTag: tilePurposeSelect?.value || undefined,
    });
  });

  objectAddBtn?.addEventListener('click', () => {
    const me = state.players.get(state.playerId);
    const x = me?.position?.x ?? 400;
    const y = me?.position?.y ?? 300;
    state.socket?.emit('room:object:create', {
      objectType: objectTypeSelect?.value || 'table',
      x,
      y,
      sizePreset: objectSizeSelect?.value || undefined,
      color: objectColorSelect?.value || undefined,
      material: objectMaterialSelect?.value || undefined,
      editPermission: objectEditAnyoneInput?.checked ? 'anyone' : 'owner_only',
    });
  });

  zoneAddBtn?.addEventListener('click', () => {
    state.socket?.emit('room:zone:create', {
      zoneType: zoneTypeSelect?.value || 'collision',
      minX: Number(zoneMinX?.value ?? 0),
      minY: Number(zoneMinY?.value ?? 0),
      maxX: Number(zoneMaxX?.value ?? 0),
      maxY: Number(zoneMaxY?.value ?? 0),
    });
  });

  zoneListEl?.addEventListener('click', (evt) => {
    const btn = evt.target.closest('button[data-action="delete"]');
    if (!btn) return;
    const zoneId = btn.getAttribute('data-zone-id');
    if (!zoneId) return;
    state.socket?.emit('room:zone:delete', { zoneId });
  });

  triggerAddBtn?.addEventListener('click', () => {
    const zoneId = triggerZoneSelect?.value;
    if (!zoneId) return;
    state.socket?.emit('room:trigger:create', {
      zoneId,
      eventType: triggerEventInput?.value || 'custom_event',
      repeatable: !!triggerRepeatableInput?.checked,
    });
  });

  triggerListEl?.addEventListener('click', (evt) => {
    const btn = evt.target.closest('button[data-action="delete"]');
    if (!btn) return;
    const triggerId = btn.getAttribute('data-trigger-id');
    if (!triggerId) return;
    state.socket?.emit('room:trigger:delete', { triggerId });
  });

  versionSaveBtn?.addEventListener('click', () => {
    state.socket?.emit('room:version:save', {});
  });

  versionPublishBtn?.addEventListener('click', () => {
    const latest = state.builderVersions[0];
    if (!latest) return;
    state.socket?.emit('room:version:publish', { versionNumber: latest.versionNumber });
  });

  externalLinksInput?.addEventListener('change', () => {
    state.socket?.emit('room:moderation:external_links:set', { allowed: !!externalLinksInput.checked });
  });

  moderationPlayerListEl?.addEventListener('change', (evt) => {
    const select = evt.target.closest('select.mod-role-select');
    if (!select) return;
    const targetId = select.getAttribute('data-player-id');
    if (!targetId) return;
    state.socket?.emit('room:role:assign', { targetId, role: select.value });
  });

  moderationPlayerListEl?.addEventListener('click', (evt) => {
    const btn = evt.target.closest('button[data-player-id]');
    if (!btn) return;
    const targetId = btn.getAttribute('data-player-id');
    if (!targetId) return;
    if (btn.classList.contains('mod-mute-btn')) {
      const event = state.mutedPlayers.has(targetId) ? 'room:moderation:unmute' : 'room:moderation:mute';
      state.socket?.emit(event, { targetId });
    } else if (btn.classList.contains('mod-kick-btn')) {
      state.socket?.emit('room:moderation:kick', { targetId });
    } else if (btn.classList.contains('mod-ban-btn')) {
      state.socket?.emit('room:moderation:ban', { targetId });
    }
  });

  auditLogBtn?.addEventListener('click', () => {
    if (auditLogListEl && !auditLogListEl.classList.contains('hidden')) {
      auditLogListEl.classList.add('hidden');
      return;
    }
    state.socket?.emit('room:moderation:audit_log:request', {}, (log) => {
      if (!auditLogListEl) return;
      const entries = Array.isArray(log) ? log : [];
      auditLogListEl.innerHTML = entries.length
        ? entries.map((entry) => `<li>${escapeHtml(entry.actorId)} → ${escapeHtml(entry.action)}${entry.targetId ? ` (${escapeHtml(entry.targetId)})` : ''}</li>`).join('')
        : '<li>No audit log entries yet.</li>';
      auditLogListEl.classList.remove('hidden');
    });
  });

  objectListEl?.addEventListener('click', (evt) => {
    const btn = evt.target.closest('button[data-action]');
    if (!btn) return;
    const objectId = btn.getAttribute('data-object-id');
    const action = btn.getAttribute('data-action');
    if (!objectId || !action) return;
    if (action === 'lock') {
      const locked = btn.getAttribute('data-locked') === 'true';
      state.socket?.emit('room:object:lock', { objectId, locked: !locked });
    } else if (action === 'duplicate') {
      state.socket?.emit('room:object:duplicate', { objectId });
    } else if (action === 'delete') {
      state.socket?.emit('room:object:delete', { objectId });
    } else if (action === 'front' || action === 'back') {
      state.socket?.emit('room:object:layer', { objectId, action });
    }
  });

  objectListEl?.addEventListener('change', (evt) => {
    const input = evt.target.closest('input[data-field]');
    if (!input) return;
    const row = input.closest('[data-object-id]');
    const objectId = row?.getAttribute('data-object-id');
    const field = input.getAttribute('data-field');
    if (!objectId) return;
    if (field === 'editPermission') {
      state.socket?.emit('room:object:permission', {
        objectId,
        editPermission: input.checked ? 'anyone' : 'owner_only',
      });
      return;
    }
    const value = Number(input.value);
    if (Number.isNaN(value)) return;
    if (field === 'x' || field === 'y') {
      const other = row.querySelector(`input[data-field="${field === 'x' ? 'y' : 'x'}"]`);
      const x = field === 'x' ? value : Number(other?.value ?? 0);
      const y = field === 'y' ? value : Number(other?.value ?? 0);
      state.socket?.emit('room:object:move', { objectId, x, y });
    } else if (field === 'width' || field === 'height') {
      const other = row.querySelector(`input[data-field="${field === 'width' ? 'height' : 'width'}"]`);
      const width = field === 'width' ? value : Number(other?.value ?? 1);
      const height = field === 'height' ? value : Number(other?.value ?? 1);
      state.socket?.emit('room:object:resize', { objectId, width, height });
    } else if (field === 'rotation') {
      state.socket?.emit('room:object:rotate', { objectId, rotation: value });
    }
  });

  versionListEl?.addEventListener('click', (evt) => {
    const btn = evt.target.closest('button[data-action="rollback"]');
    if (!btn) return;
    const versionNumber = Number(btn.getAttribute('data-version'));
    if (Number.isNaN(versionNumber)) return;
    state.socket?.emit('room:version:rollback', { versionNumber });
  });

  bookShelfSelect?.addEventListener('change', () => {
    const objectId = bookShelfSelect.value;
    if (!objectId) {
      renderBuilderBookList();
      return;
    }
    state.suppressReaderModalForBrowse = true;
    state.socket?.emit('room:object:interact', { objectId, interactionType: 'browse_books' });
  });

  bookAddBtn?.addEventListener('click', () => {
    const objectId = bookShelfSelect?.value;
    if (!objectId) return;
    const title = bookTitleInput?.value?.trim();
    const contentBody = bookContentInput?.value?.trim();
    if (!title || !contentBody) return;
    const bookId = `book-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    state.socket?.emit('room:book:add', {
      objectId,
      bookId,
      title,
      author: bookAuthorInput?.value || undefined,
      summary: bookSummaryInput?.value || undefined,
      contentType: bookContentTypeSelect?.value || 'inline',
      contentBody,
    }, (book) => {
      if (!book) return;
      state.builderBooks[objectId] = [...(state.builderBooks[objectId] || []), book];
      renderBuilderBookList();
    });
    if (bookTitleInput) bookTitleInput.value = '';
    if (bookAuthorInput) bookAuthorInput.value = '';
    if (bookSummaryInput) bookSummaryInput.value = '';
    if (bookContentInput) bookContentInput.value = '';
  });

  bookListEl?.addEventListener('click', (evt) => {
    const btn = evt.target.closest('button[data-action="remove-book"]');
    if (!btn) return;
    const objectId = bookShelfSelect?.value;
    const bookId = btn.getAttribute('data-book-id');
    if (!objectId || !bookId) return;
    state.socket?.emit('room:book:remove', { objectId, bookId }, (removed) => {
      if (!removed) return;
      state.builderBooks[objectId] = (state.builderBooks[objectId] || []).filter((b) => b.bookId !== bookId);
      renderBuilderBookList();
    });
  });

  readerModalClose?.addEventListener('click', closeReaderModal);

  readerBackBtn?.addEventListener('click', () => {
    saveCurrentReadingProgress();
    readerBookView?.classList.add('hidden');
    readerBookListView?.classList.remove('hidden');
    if (readerModalTitle) readerModalTitle.textContent = 'Bookshelf';
    state.readerCurrentBook = null;
  });

  readerBookList?.addEventListener('click', (evt) => {
    const li = evt.target.closest('li[data-book-id]');
    if (!li || !state.readerModalObjectId) return;
    const objectId = state.readerModalObjectId;
    const books = state.builderBooks[objectId] || [];
    const book = books.find((b) => b.bookId === li.getAttribute('data-book-id'));
    if (book) openReaderBookView(objectId, book, book.progress ?? 0);
  });

  videoTvSelect?.addEventListener('change', () => {
    const objectId = videoTvSelect.value;
    if (!objectId) {
      renderBuilderVideoList();
      return;
    }
    state.suppressMediaModalForBrowse = true;
    state.socket?.emit('room:object:interact', { objectId, interactionType: 'open_playlist' });
  });

  videoAddBtn?.addEventListener('click', () => {
    const objectId = videoTvSelect?.value;
    if (!objectId) return;
    const title = videoTitleInput?.value?.trim();
    const youtubeVideoId = extractYoutubeVideoId(videoYoutubeInput?.value?.trim());
    if (!title || !youtubeVideoId) {
      addSystemMessage('Enter a title and a valid YouTube URL or video ID.');
      return;
    }
    const videoId = `video-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    state.socket?.emit('room:media:video:add', {
      objectId, videoId, title, youtubeVideoId, description: videoDescriptionInput?.value || undefined,
    }, (video) => {
      if (!video) return;
      state.builderVideos[objectId] = [...(state.builderVideos[objectId] || []), video];
      renderBuilderVideoList();
    });
    if (videoTitleInput) videoTitleInput.value = '';
    if (videoYoutubeInput) videoYoutubeInput.value = '';
    if (videoDescriptionInput) videoDescriptionInput.value = '';
  });

  videoListEl?.addEventListener('click', (evt) => {
    const btn = evt.target.closest('button[data-action="remove-video"]');
    if (!btn) return;
    const objectId = videoTvSelect?.value;
    const videoId = btn.getAttribute('data-video-id');
    if (!objectId || !videoId) return;
    state.socket?.emit('room:media:video:remove', { objectId, videoId }, (removed) => {
      if (!removed) return;
      state.builderVideos[objectId] = (state.builderVideos[objectId] || []).filter((v) => v.videoId !== videoId);
      renderBuilderVideoList();
    });
  });

  trackPlayerSelect?.addEventListener('change', () => {
    const objectId = trackPlayerSelect.value;
    if (!objectId) {
      renderBuilderTrackList();
      return;
    }
    state.suppressMediaModalForBrowse = true;
    state.socket?.emit('room:object:interact', { objectId, interactionType: 'view_playlist' });
  });

  trackAddBtn?.addEventListener('click', () => {
    const objectId = trackPlayerSelect?.value;
    if (!objectId) return;
    const title = trackTitleInput?.value?.trim();
    const youtubeVideoId = extractYoutubeVideoId(trackYoutubeInput?.value?.trim());
    if (!title || !youtubeVideoId) {
      addSystemMessage('Enter a title and a valid YouTube URL or video ID.');
      return;
    }
    const trackId = `track-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    state.socket?.emit('room:media:track:add', {
      objectId, trackId, title, youtubeVideoId, artist: trackArtistInput?.value || undefined,
    }, (track) => {
      if (!track) return;
      state.builderTracks[objectId] = [...(state.builderTracks[objectId] || []), track];
      renderBuilderTrackList();
    });
    if (trackTitleInput) trackTitleInput.value = '';
    if (trackArtistInput) trackArtistInput.value = '';
    if (trackYoutubeInput) trackYoutubeInput.value = '';
  });

  trackListEl?.addEventListener('click', (evt) => {
    const btn = evt.target.closest('button[data-action="remove-track"]');
    if (!btn) return;
    const objectId = trackPlayerSelect?.value;
    const trackId = btn.getAttribute('data-track-id');
    if (!objectId || !trackId) return;
    state.socket?.emit('room:media:track:remove', { objectId, trackId }, (removed) => {
      if (!removed) return;
      state.builderTracks[objectId] = (state.builderTracks[objectId] || []).filter((t) => t.trackId !== trackId);
      renderBuilderTrackList();
    });
  });

  mediaModalClose?.addEventListener('click', closeMediaModal);

  mediaBackBtn?.addEventListener('click', () => {
    mediaPlayerView?.classList.add('hidden');
    mediaPlaylistView?.classList.remove('hidden');
    if (mediaModalTitle) mediaModalTitle.textContent = state.mediaModalObjectType === 'tv' ? 'TV Playlist' : 'Music Playlist';
    state.mediaCurrentItem = null;
    if (mediaVideoFrame) mediaVideoFrame.innerHTML = '';
  });

  mediaPlaylistList?.addEventListener('click', (evt) => {
    const li = evt.target.closest('li[data-item-id]');
    if (!li || !state.mediaModalObjectId) return;
    const objectId = state.mediaModalObjectId;
    const objectType = state.mediaModalObjectType;
    const itemId = li.getAttribute('data-item-id');
    const items = objectType === 'tv' ? (state.builderVideos[objectId] || []) : (state.builderTracks[objectId] || []);
    const item = items.find((i) => (objectType === 'tv' ? i.videoId : i.trackId) === itemId);
    if (item) openMediaPlayerView(objectId, objectType, item, state.mediaSyncSession);
  });

  mediaSyncToggleBtn?.addEventListener('click', () => {
    const objectId = state.mediaModalObjectId;
    if (!objectId) return;
    const mode = mediaSyncToggleBtn.dataset.mode;
    if (mode === 'start') {
      if (!state.mediaCurrentItem) return;
      const itemId = state.mediaModalObjectType === 'tv' ? state.mediaCurrentItem.videoId : state.mediaCurrentItem.trackId;
      state.socket?.emit('room:media:sync:start', { objectId, itemId });
    } else if (mode === 'join') {
      state.socket?.emit('room:media:sync:join', { objectId });
    } else if (mode === 'leave') {
      state.socket?.emit('room:media:sync:leave', { objectId });
    } else if (mode === 'end') {
      state.socket?.emit('room:media:sync:end', { objectId });
    }
  });

  characterNpcSelect?.addEventListener('change', () => {
    renderCharacterConfigFields();
    renderBuilderStoryNodeList();
  });

  characterConfigureBtn?.addEventListener('click', () => {
    const objectId = characterNpcSelect?.value;
    const name = characterNameInput?.value?.trim();
    const role = characterRoleSelect?.value;
    const startNodeId = characterStartNodeInput?.value?.trim();
    if (!objectId || !name || !startNodeId) {
      addSystemMessage('Enter a name and start node ID for this character.');
      return;
    }
    state.socket?.emit('room:character:configure', {
      objectId, name, role, startNodeId, portraitUrl: characterPortraitInput?.value || undefined,
    }, (character) => {
      if (!character) return;
      state.builderCharacters[objectId] = character;
    });
  });

  characterKnowledgeBaseBtn?.addEventListener('click', () => {
    const objectId = characterNpcSelect?.value;
    const content = characterKnowledgeBaseInput?.value ?? '';
    if (!objectId) return;
    state.socket?.emit('room:character:knowledge_base:set', { objectId, content }, (character) => {
      if (!character) return;
      state.builderCharacters[objectId] = character;
    });
  });

  characterGenerativeBtn?.addEventListener('click', () => {
    const objectId = characterNpcSelect?.value;
    if (!objectId) return;
    state.socket?.emit('room:character:generative:configure', {
      objectId, apiBaseUrl: characterApiUrlInput?.value || undefined, apiKey: characterApiKeyInput?.value || undefined,
    }, (character) => {
      if (!character) return;
      state.builderCharacters[objectId] = character;
      if (characterApiKeyInput) characterApiKeyInput.value = '';
    });
  });

  storyNodeAddBtn?.addEventListener('click', () => {
    const objectId = characterNpcSelect?.value;
    const nodeId = storyNodeIdInput?.value?.trim();
    const characterLine = storyNodeLineInput?.value?.trim();
    if (!objectId || !nodeId || !characterLine) {
      addSystemMessage('Enter a node ID and character line.');
      return;
    }
    const choices = parseChoicesInput(storyNodeChoicesInput?.value);
    state.socket?.emit('room:character:node:add', {
      objectId, nodeId, characterLine, choices,
    }, (node) => {
      if (!node) return;
      state.builderStoryNodes[objectId] = [...(state.builderStoryNodes[objectId] || []), node];
      renderBuilderStoryNodeList();
    });
    if (storyNodeIdInput) storyNodeIdInput.value = '';
    if (storyNodeLineInput) storyNodeLineInput.value = '';
    if (storyNodeChoicesInput) storyNodeChoicesInput.value = '';
  });

  dialogueModalClose?.addEventListener('click', closeDialogueModal);

  dialogueChoiceList?.addEventListener('click', (evt) => {
    const btn = evt.target.closest('button[data-choice-index]');
    if (!btn || !state.dialogueModalObjectId) return;
    const choiceIndex = Number(btn.getAttribute('data-choice-index'));
    state.socket?.emit('room:character:talk', {
      objectId: state.dialogueModalObjectId, choiceIndex,
    }, (result) => {
      if (!result) return;
      renderDialogueNode(result.node, result.mode);
    });
  });

  dialogueAskForm?.addEventListener('submit', (evt) => {
    evt.preventDefault();
    const objectId = state.dialogueModalObjectId;
    const userMessage = dialogueAskInput?.value?.trim();
    if (!objectId || !userMessage) return;
    state.socket?.emit('room:character:ask', { objectId, userMessage }, (result) => {
      if (!result) return;
      if (dialogueAnswer) dialogueAnswer.textContent = result.answer;
      if (dialogueModeIndicator) {
        dialogueModeIndicator.textContent = formatModeLabel(result.mode);
        dialogueModeIndicator.classList.toggle('generative', result.mode === 'generative');
      }
    });
    if (dialogueAskInput) dialogueAskInput.value = '';
  });

  dialogueRestartBtn?.addEventListener('click', () => {
    const objectId = state.dialogueModalObjectId;
    if (!objectId) return;
    state.socket?.emit('room:object:interact', { objectId, interactionType: 'start_mission' });
  });

  let progressSaveTimer = null;
  readerBookContent?.addEventListener('scroll', () => {
    if (!state.readerModalObjectId || !state.readerCurrentBook || !readerBookContent) return;
    state.readerCurrentProgress = computeScrollProgress(
      readerBookContent.scrollTop, readerBookContent.scrollHeight, readerBookContent.clientHeight,
    );
    if (readerBookProgressFill) {
      readerBookProgressFill.style.width = `${Math.round(state.readerCurrentProgress * 100)}%`;
    }
    clearTimeout(progressSaveTimer);
    progressSaveTimer = setTimeout(saveCurrentReadingProgress, 800);
  });

  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);

  state.gameLoopId = setInterval(() => {
    renderPlayers();
    pruneExpiredBubbles();
  }, 33);
}

function onKeyDown(e) {
  if (!state.keys.hasOwnProperty(e.key)) return;
  if (isTypingContext()) return;
  e.preventDefault();
  state.keys[e.key] = true;
  emitDirection();
}

function onKeyUp(e) {
  if (!state.keys.hasOwnProperty(e.key)) return;
  if (isTypingContext()) return;
  state.keys[e.key] = false;
  emitDirection();
}

function isTypingContext() {
  const active = document.activeElement;
  if (!active) return false;
  const tag = active.tagName?.toUpperCase();
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
    return true;
  }
  return Boolean(active.isContentEditable);
}

function getDirectionFromKeys() {
  let x = 0;
  let y = 0;
  if (state.keys.ArrowLeft) x -= 1;
  if (state.keys.ArrowRight) x += 1;
  if (state.keys.ArrowUp) y -= 1;
  if (state.keys.ArrowDown) y += 1;
  return { x, y };
}

function emitDirection() {
  const dir = getDirectionFromKeys();
  state.socket?.emit('player:direction', dir);
}

function clearKeyboardDirection() {
  Object.keys(state.keys).forEach(k => { state.keys[k] = false; });
  state.socket?.emit('player:direction', { x: 0, y: 0 });
}

function setChatMode(mode) {
  state.chatMode = mode;
  document.querySelectorAll('.mode-btn').forEach(btn => {
    const isActive = btn.dataset.mode === mode;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-pressed', String(isActive));
  });
  recipientSelect.classList.toggle('hidden', mode === 'public');
}

function connectSocket() {
  state.socket = io(window.location.origin, { transports: ['websocket', 'polling'] });

  state.socket.on('connect', () => {
    state.playerId = state.socket.id;
    state.socket.emit('player:join', { avatar: state.avatar });
    requestRoomList();
    roomChooser.classList.remove('hidden');

    // Init combat bindings once socket is ready
    initCombat({
      socket:        state.socket,
      getMyId:       () => state.playerId,
      getMyPos:      () => state.players.get(state.playerId)?.position ?? null,
      getPlayers:    () => state.players,
      onAttackStart: (playerId, type, startMs, duration, facingRight) => {
        state.attackAnim.set(playerId, { type, startMs, duration, facingRight: facingRight ?? true });
      },
    });
  });

  state.socket.on('player:joined', (data) => {
    state.playerId = data.id;
    state.players.set(data.id, { id: data.id, avatar: data.avatar, position: data.position });
    state.playerStamina.set(data.id, data.stamina ?? 100);
    state.currentRoomId = 'lobby';
    state.currentTile = data.tile || { x: 0, y: 0 };
    renderMiniMap();
    updateCurrentTileLabel();
    refreshCanvasBuilderObjects();
    renderPlayers();
  });

  state.socket.on('room:list', (payload) => {
    state.roomFilters = normalizeRoomFilters(payload.filters || state.roomFilters);
    state.roomList = normalizeRooms(payload.rooms || []);
    renderRoomList();
  });

  // Another client created/joined/left a room; refresh using our own
  // current filters instead of receiving someone else's unfiltered list.
  state.socket.on('room:list:changed', () => {
    if (!roomChooser.classList.contains('hidden')) {
      requestRoomList();
    }
  });

  state.socket.on('room:created', (room) => {
    addSystemMessage(`Created room: ${room.name}`);
    state.socket?.emit('room:join', { roomId: room.id });
    requestRoomList();
  });

  state.socket.on('room:joined', (payload) => {
    state.currentRoomId = payload.roomId || 'lobby';
    state.currentTile = payload.currentTile || { x: 0, y: 0 };
    state.roomTiles = normalizeTileList(payload.tiles || [{ x: 0, y: 0 }]);
    state.roomHostId = payload.hostId || null;
    state.myRoomRole = payload.myRole || 'participant';
    state.playerRoles = new Map();
    state.mutedPlayers = new Set();
    clearSceneStateForRoomSwitch();
    addSystemMessage(`Joined room: ${state.currentRoomId}`);
    roomChooser.classList.add('hidden');
    renderMiniMap();
    updateCurrentTileLabel();
    refreshCanvasBuilderObjects();
    renderModerationPanel();
    requestRoomList();
  });

  state.socket.on('room:role:updated', (payload) => {
    if (!payload?.targetId) return;
    state.playerRoles.set(payload.targetId, payload.role);
    if (payload.targetId === state.playerId) state.myRoomRole = payload.role;
    renderModerationPanel();
  });

  state.socket.on('room:moderation:muted', (payload) => {
    if (!payload?.targetId) return;
    if (payload.muted) state.mutedPlayers.add(payload.targetId);
    else state.mutedPlayers.delete(payload.targetId);
    renderModerationPanel();
  });

  state.socket.on('room:moderation:removed', (payload) => {
    addSystemMessage(payload?.reason === 'banned' ? 'You were banned from that room.' : 'You were removed from that room.');
  });

  state.socket.on('room:moderation:external_links', (payload) => {
    if (externalLinksInput) externalLinksInput.checked = payload?.allowed !== false;
  });

  state.socket.on('room:tiles', (payload) => {
    if (payload.roomId !== state.currentRoomId) return;
    state.roomTiles = normalizeTileList(payload.tiles || []);
    renderMiniMap();
  });

  state.socket.on('room:builder:state', (payload) => {
    if (payload.roomId !== state.currentRoomId) return;
    state.builderState = {
      tiles: payload.tiles || [],
      objects: payload.objects || [],
      zones: payload.zones || [],
      triggers: payload.triggers || [],
    };
    renderBuilderObjectList();
    renderBuilderZoneList();
    renderBuilderTriggerList();
    refreshCanvasBuilderObjects();
  });

  state.socket.on('room:builder:versions', (payload) => {
    if (payload.roomId !== state.currentRoomId) return;
    state.builderVersions = payload.versions || [];
    renderBuilderVersionList();
  });

  state.socket.on('room:builder:rollback', (payload) => {
    if (payload.roomId !== state.currentRoomId) return;
    addSystemMessage(`Rolled back room to a previous saved draft.`);
  });

  state.socket.on('room:object:interacted', (payload) => {
    handleObjectInteractionResult(payload);
  });

  state.socket.on('room:media:sync:updated', (payload) => {
    if (payload.objectId !== state.mediaModalObjectId) return;
    updateMediaSyncUi(payload.session);
  });

  state.socket.on('combat:hit', (evt) => {
    const now = Date.now();
    state.playerStamina.set(evt.targetId,   evt.targetStamina);
    state.playerStamina.set(evt.attackerId, evt.attackerStamina ?? state.playerStamina.get(evt.attackerId) ?? 100);
    state.hitFlash.set(evt.targetId, now + 460);
    // Compute facingRight for remote/AI attackers from their current positions
    const attackerPos = state.players.get(evt.attackerId)?.position;
    const targetPos   = state.players.get(evt.targetId)?.position;
    const facingRight = !attackerPos || !targetPos || targetPos.x >= attackerPos.x;
    const duration = ATTACK_DURATIONS[evt.type] ?? 480;
    state.attackAnim.set(evt.attackerId, { type: evt.type, startMs: now, duration, facingRight });
    if (evt.stunnedUntil > 0) state.playerStunned.set(evt.targetId, evt.stunnedUntil);
    renderPlayers();
  });

  state.socket.on('room:state', (data) => {
    data.players.forEach(p => {
      const existing = state.players.get(p.id);
      if (existing) {
        existing.position    = p.position;
        existing.avatar      = p.avatar;
        existing.actionState = p.actionState ?? null;
        existing.tile        = p.tile ?? existing.tile ?? { x: 0, y: 0 };
      } else {
        state.players.set(p.id, p);
      }
      state.actionStates.set(p.id,   p.actionState  ?? null);
      state.playerStamina.set(p.id,  p.stamina       ?? 100);
      state.playerBlocking.set(p.id, p.blocking      ?? false);
      if (p.stunnedUntil > 0) state.playerStunned.set(p.id, p.stunnedUntil);
    });
    const me = state.players.get(state.playerId);
    if (me?.tile) {
      state.currentTile = me.tile;
      updateCurrentTileLabel();
      renderMiniMap();
      refreshCanvasBuilderObjects();
    }
    renderPlayers();
    updateOnlineCount();
    updateRecipientList();
    renderModerationPanel();
  });

  state.socket.on('player:entered', (data) => {
    state.players.set(data.id, data);
    renderPlayers();
    updateOnlineCount();
    updateRecipientList();
    addSystemMessage(`${data.avatar.username} entered the lounge`);
  });

  state.socket.on('player:left', (data) => {
    const player = state.players.get(data.id);
    if (player) addSystemMessage(`${player.avatar.username} left the lounge`);
    state.players.delete(data.id);
    state.activeBubbles.delete(data.id);
    state.walkPhases.delete(data.id);
    state.talkingUntil.delete(data.id);
    state.blinkDelay.delete(data.id);
    state.actionStates.delete(data.id);
    state.playerStamina.delete(data.id);
    state.playerBlocking.delete(data.id);
    state.playerStunned.delete(data.id);
    state.hitFlash.delete(data.id);
    state.attackAnim.delete(data.id);
    state.wasStunned.delete(data.id);
    state.wakingUpUntil.delete(data.id);
    renderPlayers();
    updateOnlineCount();
    updateRecipientList();
  });

  state.socket.on('chat:message', (msg) => {
    appendChatMessage(msg);
    showBubble(msg.senderId, msg.text, msg.type);
  });

  state.socket.on('chat:history', (messages) => {
    messages.forEach(msg => {
      appendChatMessage(msg);
      showBubble(msg.senderId, msg.text, msg.type, msg.timestamp);
    });
  });

  state.socket.on('chat:bubbles', (bubbles) => {
    bubbles.forEach(b => showBubble(b.senderId, b.text, b.type, b.timestamp));
  });

  state.socket.on('error', (err) => {
    console.error('Server error:', err.message);
    addSystemMessage(`⚠ ${err.message}`);
  });

  // Block animation for remote players
  state.socket.on('combat:block_update', (evt) => {
    if (evt.blocking) {
      state.blockAnim.set(evt.playerId, { phase: 0, entering: true, startMs: Date.now() });
    } else {
      const current = state.blockAnim.get(evt.playerId);
      if (current) {
        state.blockAnim.set(evt.playerId, { phase: current.phase, entering: false, startMs: Date.now() });
      }
    }
  });
}

function showBubble(senderId, text, type, timestamp) {
  const now = Date.now();
  state.activeBubbles.set(senderId, {
    text,
    type,
    addedAt: now,
    expiresAt: (timestamp || now) + BUBBLE_DURATION,
  });
  // Mark the sender as talking for 3 seconds
  state.talkingUntil.set(senderId, now + 3000);
  renderPlayers();
}

function spawnClickMarker(x, y) {
  const el = document.createElement('div');
  el.className = 'click-marker';
  el.style.left = `${x}px`;
  el.style.top  = `${y}px`;
  el.innerHTML = `<svg viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="18" cy="18" r="14" stroke="#ff6b9d" stroke-width="2.5" stroke-dasharray="5 3"/>
    <circle cx="18" cy="18" r="5" fill="#ff6b9d" opacity="0.85"/>
    <circle cx="18" cy="18" r="2" fill="white"/>
  </svg>`;
  playersLayer.appendChild(el);
  el.addEventListener('animationend', () => el.remove());
}

function pruneExpiredBubbles() {
  const now = Date.now();
  let changed = false;
  for (const [id, bubble] of state.activeBubbles) {
    if (bubble.expiresAt <= now) {
      state.activeBubbles.delete(id);
      changed = true;
    }
  }
  if (changed) renderPlayers();
}

function renderPlayers() {
  const sorted = [...state.players.values()].sort((a, b) => a.position.y - b.position.y);
  const now = Date.now();

  // ── remove elements for players who have left ────────────────────────────
  for (const el of [...playersLayer.querySelectorAll('.room-player')]) {
    if (!state.players.has(el.dataset.pid)) el.remove();
  }

  // ── update / create each player element in sorted z-order ────────────────
  for (let i = 0; i < sorted.length; i++) {
    const player = sorted[i];

    // walk phase
    let wt = state.walkPhases.get(player.id);
    if (!wt) {
      wt = { phase: 0, lastX: player.position.x, lastY: player.position.y };
      state.walkPhases.set(player.id, wt);
    }
    const moved = player.position.x !== wt.lastX || player.position.y !== wt.lastY;
    wt.phase = advanceWalkPhase(wt.phase, moved);
    wt.lastX = player.position.x;
    wt.lastY = player.position.y;

    const talking = (state.talkingUntil.get(player.id) || 0) > now;
    const actionState = state.actionStates.get(player.id) ?? player.actionState ?? null;

    // ── block animation phase ────────────────────────────────────────────────
    const isLocalPlayer = player.id === state.playerId;
    const isCurrentlyBlocking = isLocalPlayer ? isBlocking() : (state.playerBlocking.get(player.id) ?? false);
    // Advance block phase (200ms enter, 150ms exit)
    let ba = state.blockAnim.get(player.id);
    if (isCurrentlyBlocking && (!ba || !ba.entering)) {
      ba = { phase: ba?.phase ?? 0, entering: true, startMs: now };
      state.blockAnim.set(player.id, ba);
    } else if (!isCurrentlyBlocking && ba?.entering) {
      ba = { phase: ba.phase, entering: false, startMs: now };
      state.blockAnim.set(player.id, ba);
    }
    let blockPhase = 0;
    if (ba) {
      const elapsed = now - ba.startMs;
      if (ba.entering) {
        blockPhase = Math.min(1, ba.phase + elapsed / 200);
      } else {
        blockPhase = Math.max(0, ba.phase - elapsed / 150);
        if (blockPhase === 0) state.blockAnim.delete(player.id);
      }
      if (ba.entering) ba.phase = blockPhase; // update for next frame
    }

    if (!state.blinkDelay.has(player.id)) {
      state.blinkDelay.set(player.id, `${(Math.random() * 4).toFixed(2)}s`);
    }
    const blinkDelay = state.blinkDelay.get(player.id);

    // ── find or create the wrapper div ──────────────────────────────────────
    let el = playersLayer.querySelector(`[data-pid="${CSS.escape(player.id)}"]`);
    const isNew = !el;
    if (isNew) {
      el = document.createElement('div');
      el.dataset.pid = player.id;
    }

    el.className = 'room-player' + (player.id === state.playerId ? ' is-self' : '');
    el.style.left = `${player.position.x}px`;
    el.style.top  = `${player.position.y}px`;
    el.style.zIndex = i + 1;

    // ── bubble: only touch the DOM when content changes ─────────────────────
    const bubble = state.activeBubbles.get(player.id);
    let bubbleEl = el.querySelector('.speech-bubble');

    if (bubble) {
      const lockIcon = bubble.type === 'private' ? '<span class="bubble-lock">🔒</span>' : '';
      const desiredText = lockIcon + escapeHtml(bubble.text);

      if (!bubbleEl) {
        // First appearance — create and animate in
        bubbleEl = document.createElement('div');
        bubbleEl.className = 'speech-bubble' + (bubble.type === 'private' ? ' private' : '');
        bubbleEl.innerHTML = desiredText;
        el.insertBefore(bubbleEl, el.firstChild);
      } else if (bubbleEl.innerHTML !== desiredText) {
        // Text updated (shouldn't happen often) — update in place, no animation restart
        bubbleEl.innerHTML = desiredText;
      }
    } else if (bubbleEl) {
      // Bubble expired — fade out then remove
      bubbleEl.classList.add('fading');
      bubbleEl.addEventListener('animationend', () => bubbleEl.remove(), { once: true });
    }

    // ── avatar SVG ───────────────────────────────────────────────────────────
    const blocking    = state.playerBlocking.get(player.id) ?? false;
    const stunnedUntil = state.playerStunned.get(player.id) ?? 0;
    const stunned     = stunnedUntil > now;
    const isHit       = (state.hitFlash.get(player.id) ?? 0) > now;

    // Compute smooth attack angles from timing data
    const attackInfo = state.attackAnim.get(player.id);
    let attackAngles = null;
    if (attackInfo && !stunned) {
      const phase = computeAttackPhase(attackInfo.startMs, now, attackInfo.duration);
      if (phase < 1) {
        const facingRight = attackInfo.facingRight ?? true;
        attackAngles = attackInfo.type === 'kick'
          ? getKickAngles(phase, facingRight)
          : getPunchAngles(phase, facingRight);
      }
    }

    // If not attacking, use block angles if blocking
    if (!attackAngles && blockPhase > 0) {
      const ba_ = getBlockAngles(blockPhase);
      attackAngles = { ...ba_, leftLegAngle: 0, rightLegAngle: 0 };
    }

    // KO / wake-up class management
    const prevStunned = state.wasStunned.get(player.id) ?? false;
    state.wasStunned.set(player.id, stunned);
    if (prevStunned && !stunned) {
      state.wakingUpUntil.set(player.id, now + 800);
    }
    const isWakingUp = (state.wakingUpUntil.get(player.id) ?? 0) > now;
    if (stunned)    el.classList.add('is-ko');
    else            el.classList.remove('is-ko');
    if (isWakingUp) el.classList.add('is-waking-up');
    else            el.classList.remove('is-waking-up');

    const newSvg = renderAvatarSVG(
      player.avatar, 'normal',
      (stunned || isWakingUp) ? 0 : wt.phase,
      talking, actionState, false, attackAngles
    );
    let svgEl = el.querySelector('.avatar-svg');
    const tmp = document.createElement('div');
    tmp.innerHTML = newSvg;
    const newSvgEl = tmp.firstElementChild;
    if (!stunned && !isWakingUp) {
      newSvgEl.style.animationDelay = blinkDelay;
      newSvgEl.querySelectorAll('.eye-l, .eye-r').forEach(eye => {
        eye.style.animationDelay = blinkDelay;
        const cx = eye.querySelector('ellipse')?.getAttribute('cx') || '50%';
        const cy = eye.querySelector('ellipse')?.getAttribute('cy') || '50%';
        eye.style.transformOrigin = `${cx}px ${cy}px`;
      });
    }
    if (talking)              newSvgEl.classList.add('is-talking');
    if (isHit && !stunned)    newSvgEl.classList.add('avatar-hit');
    if (stunned)              newSvgEl.classList.add('avatar-ko-pose');

    if (svgEl) {
      el.replaceChild(newSvgEl, svgEl);
    } else {
      el.appendChild(newSvgEl);
    }

    // ── KO ♥ ZZZ indicator ─────────────────────────────────────────────────
    let zzzEl = el.querySelector('.ko-zzz');
    if (stunned && !zzzEl) {
      zzzEl = document.createElement('span');
      zzzEl.className = 'ko-zzz';
      zzzEl.textContent = '💤';
      el.appendChild(zzzEl);
    } else if (!stunned && zzzEl) {
      zzzEl.remove();
    }

    // ── stamina bar ──────────────────────────────────────────────────────────
    const stamina = state.playerStamina.get(player.id) ?? 100;
    let barWrap = el.querySelector('.stamina-bar');
    if (!barWrap) {
      barWrap = document.createElement('div');
      barWrap.className = 'stamina-bar';
      barWrap.innerHTML = '<div class="stamina-fill"></div>';
      el.appendChild(barWrap);
    }
    const fill = barWrap.querySelector('.stamina-fill');
    fill.style.width = `${Math.max(0, stamina)}%`;
    fill.style.background = stamina > 60
      ? 'var(--md-success)'
      : stamina > 25
        ? 'var(--md-warning)'
        : 'var(--md-error)';
    barWrap.title = `${Math.round(stamina)} HP`;

    // ── name tag ────────────────────────────────────────────────────────────
    let nameEl = el.querySelector('.player-name');
    if (!nameEl) {
      nameEl = document.createElement('span');
      nameEl.className = 'player-name';
      el.appendChild(nameEl);
    }
    nameEl.textContent = stunned ? `KO  ${player.avatar.username}` : player.avatar.username;

    // ── self indicator ──────────────────────────────────────────────────────
    if (player.id === state.playerId && !el.querySelector('.self-indicator')) {
      const si = document.createElement('span');
      si.className = 'self-indicator';
      el.appendChild(si);
    }

    if (isNew) playersLayer.appendChild(el);
  }
}

function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;

  const payload = { text, type: state.chatMode };
  if (state.chatMode === 'private') {
    const recipientId = recipientDropdown.value;
    if (!recipientId) return;
    payload.recipientId = recipientId;
  }

  state.socket.emit('chat:send', payload);
  chatInput.value = '';
}

function appendChatMessage(msg) {
  const el = document.createElement('div');
  el.className = 'chat-message' + (msg.type === 'private' ? ' private' : '');
  const time = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const tag = msg.type === 'private' ? '<span class="msg-tag">whisper</span>' : '';
  const reportBtn = msg.senderId !== state.playerId
    ? `<button type="button" class="chat-report-btn" data-message-id="${escapeHtml(msg.id || '')}" title="Report message">⚑</button>`
    : '';
  el.innerHTML = `<span class="msg-time">${time}</span>` +
    `<span class="msg-sender">${escapeHtml(msg.senderName)}</span>` +
    `<span class="msg-text">${escapeHtml(msg.text)}</span>${tag}${reportBtn}`;
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addSystemMessage(text) {
  const el = document.createElement('div');
  el.className = 'chat-message system';
  el.textContent = text;
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function updateOnlineCount() {
  onlineCount.textContent = `${state.players.size} online`;
}

function updateRecipientList() {
  recipientDropdown.innerHTML = '<option value="">Select player...</option>';
  for (const [id, player] of state.players) {
    if (id === state.playerId) continue;
    const opt = document.createElement('option');
    opt.value = id;
    opt.textContent = player.avatar.username;
    recipientDropdown.appendChild(opt);
  }
}

function clearSceneStateForRoomSwitch() {
  state.players.clear();
  state.activeBubbles.clear();
  state.walkPhases.clear();
  state.talkingUntil.clear();
  state.blinkDelay.clear();
  state.actionStates.clear();
  state.playerStamina.clear();
  state.playerBlocking.clear();
  state.playerStunned.clear();
  state.hitFlash.clear();
  state.attackAnim.clear();
  state.blockAnim.clear();
  state.wasStunned.clear();
  state.wakingUpUntil.clear();
  playersLayer.innerHTML = '';
  chatMessages.innerHTML = '';
}

function updateCurrentTileLabel() {
  if (!currentTileLabel) return;
  currentTileLabel.textContent = `Tile (${state.currentTile.x}, ${state.currentTile.y})`;
  renderBuilderObjectList();
  renderBuilderZoneList();
  renderBuilderTriggerList();
  renderBookShelfSelect();
  renderVideoTvSelect();
  renderTrackPlayerSelect();
  renderCharacterNpcSelect();
  renderModerationPanel();
}

function updateBuildModeUi() {
  if (!buildModeToggle || !buildControls) return;
  buildModeToggle.classList.toggle('active', state.buildMode);
  buildModeToggle.setAttribute('aria-pressed', String(state.buildMode));
  buildModeToggle.textContent = `Build Mode: ${state.buildMode ? 'On' : 'Off'}`;
  buildControls.classList.toggle('hidden', !state.buildMode);
}

function tileKey(tile) {
  if (Array.isArray(tile)) return `${tile[0]},${tile[1]}`;
  return `${tile?.x ?? 0},${tile?.y ?? 0}`;
}

function currentTileBuilderObjects() {
  const currentKey = tileKey(state.currentTile);
  return state.builderState.objects.filter((obj) => tileKey(obj.tile) === currentKey);
}

function refreshCanvasBuilderObjects() {
  setBuilderObjects(currentTileBuilderObjects());
}

function renderBuilderObjectList() {
  if (!objectListEl) return;
  const currentKey = tileKey(state.currentTile);
  const objects = state.builderState.objects.filter((obj) => tileKey(obj.tile) === currentKey);

  if (objects.length === 0) {
    objectListEl.innerHTML = '<li class="builder-empty-hint">No objects on this tile yet.</li>';
    return;
  }

  objectListEl.innerHTML = objects.map((obj) => {
    const locked = !!obj.isLocked;
    return `
      <li class="builder-object-row" data-object-id="${escapeHtml(obj.objectId)}">
        <div class="builder-object-row-header">
          <span>${escapeHtml(obj.objectType)}</span>
          <div class="builder-object-row-actions">
            <button type="button" class="builder-icon-btn ${locked ? 'active' : ''}" data-action="lock" data-object-id="${escapeHtml(obj.objectId)}" data-locked="${locked}" aria-label="Toggle lock" title="Lock/unlock">
              <span class="material-symbols-outlined" aria-hidden="true">${locked ? 'lock' : 'lock_open'}</span>
            </button>
            <button type="button" class="builder-icon-btn" data-action="front" data-object-id="${escapeHtml(obj.objectId)}" aria-label="Bring to front" title="Bring to front">
              <span class="material-symbols-outlined" aria-hidden="true">flip_to_front</span>
            </button>
            <button type="button" class="builder-icon-btn" data-action="back" data-object-id="${escapeHtml(obj.objectId)}" aria-label="Send to back" title="Send to back">
              <span class="material-symbols-outlined" aria-hidden="true">flip_to_back</span>
            </button>
            <button type="button" class="builder-icon-btn" data-action="duplicate" data-object-id="${escapeHtml(obj.objectId)}" aria-label="Duplicate" title="Duplicate">
              <span class="material-symbols-outlined" aria-hidden="true">content_copy</span>
            </button>
            <button type="button" class="builder-icon-btn" data-action="delete" data-object-id="${escapeHtml(obj.objectId)}" aria-label="Delete" title="Delete">
              <span class="material-symbols-outlined" aria-hidden="true">delete</span>
            </button>
          </div>
        </div>
        <div class="builder-object-row-meta">
          ${obj.sizePreset ? `<span class="builder-object-chip">${escapeHtml(obj.sizePreset)}</span>` : ''}
          ${obj.color ? `<span class="builder-object-chip">${escapeHtml(obj.color)}</span>` : ''}
          ${obj.material ? `<span class="builder-object-chip">${escapeHtml(obj.material)}</span>` : ''}
          <label class="builder-checkbox-field">
            <input type="checkbox" data-field="editPermission" ${obj.editPermission === 'anyone' ? 'checked' : ''} />
            <span>Anyone can edit</span>
          </label>
        </div>
        <div class="builder-object-row-fields">
          <label>X<input type="number" data-field="x" value="${obj.x}" ${locked ? 'disabled' : ''} /></label>
          <label>Y<input type="number" data-field="y" value="${obj.y}" ${locked ? 'disabled' : ''} /></label>
          <label>Rotation<input type="number" data-field="rotation" value="${obj.rotation ?? 0}" ${locked ? 'disabled' : ''} /></label>
          <label>Width<input type="number" data-field="width" value="${obj.width}" min="1" ${locked ? 'disabled' : ''} /></label>
          <label>Height<input type="number" data-field="height" value="${obj.height}" min="1" ${locked ? 'disabled' : ''} /></label>
        </div>
      </li>`;
  }).join('');
}

// ─── Phase F: Bookshelf reader ─────────────────────────────────────────────

function renderBookShelfSelect() {
  if (!bookShelfSelect) return;
  const currentKey = tileKey(state.currentTile);
  const shelves = state.builderState.objects.filter(
    (obj) => tileKey(obj.tile) === currentKey && obj.objectType === 'bookshelf',
  );
  const previousValue = bookShelfSelect.value;
  bookShelfSelect.innerHTML = shelves.length
    ? shelves.map((s) => `<option value="${escapeHtml(s.objectId)}">${escapeHtml(s.objectId)}</option>`).join('')
    : '<option value="">No bookshelves on this tile</option>';
  if (shelves.some((s) => s.objectId === previousValue)) {
    bookShelfSelect.value = previousValue;
  }
  renderBuilderBookList();
}

function renderBuilderBookList() {
  if (!bookListEl) return;
  const objectId = bookShelfSelect?.value;
  const books = objectId ? (state.builderBooks[objectId] || []) : [];
  if (books.length === 0) {
    bookListEl.innerHTML = '<li class="builder-empty-hint">No books on this shelf yet.</li>';
    return;
  }
  bookListEl.innerHTML = books.map((b) => `
    <li class="builder-object-row">
      <div class="builder-object-row-header">
        <span>${escapeHtml(b.title)}</span>
        <div class="builder-object-row-actions">
          <button type="button" class="builder-icon-btn" data-action="remove-book" data-book-id="${escapeHtml(b.bookId)}" aria-label="Remove book" title="Remove book">
            <span class="material-symbols-outlined" aria-hidden="true">delete</span>
          </button>
        </div>
      </div>
    </li>`).join('');
}

function openReaderModal(objectId) {
  state.readerModalObjectId = objectId;
  state.readerCurrentBook = null;
  readerModal?.classList.remove('hidden');
  readerBookListView?.classList.remove('hidden');
  readerBookView?.classList.add('hidden');
  if (readerModalTitle) readerModalTitle.textContent = 'Bookshelf';
}

function closeReaderModal() {
  saveCurrentReadingProgress();
  readerModal?.classList.add('hidden');
  state.readerModalObjectId = null;
  state.readerCurrentBook = null;
}

function renderReaderBookList(objectId, books) {
  if (!readerBookList) return;
  readerBookList.innerHTML = books.length
    ? books.map((b) => `
      <li class="reader-book-list-item" data-book-id="${escapeHtml(b.bookId)}">
        <div>
          <div class="reader-book-list-item-title">${escapeHtml(b.title)}</div>
          <div class="reader-book-list-item-meta">${[b.author, formatEstReadTime(b.estReadMinutes), b.progress > 0 ? `${Math.round(b.progress * 100)}% read` : null].filter(Boolean).map(escapeHtml).join(' \u00b7 ')}</div>
          ${b.summary ? `<div class="reader-book-list-item-summary">${escapeHtml(truncateSummary(b.summary))}</div>` : ''}
        </div>
      </li>`).join('')
    : '<li class="builder-empty-hint">No books on this shelf yet.</li>';
}

function openReaderBookView(objectId, book, initialProgress = 0) {
  state.readerModalObjectId = objectId;
  state.readerCurrentBook = book;
  state.readerCurrentProgress = clampProgress(initialProgress);
  readerBookListView?.classList.add('hidden');
  readerBookView?.classList.remove('hidden');
  if (readerModalTitle) readerModalTitle.textContent = book.title;
  if (readerBookTitle) readerBookTitle.textContent = book.title;
  if (readerBookMeta) {
    readerBookMeta.textContent = [book.author, formatEstReadTime(book.estReadMinutes)].filter(Boolean).join(' \u00b7 ');
  }
  if (readerBookProgressFill) {
    readerBookProgressFill.style.width = `${Math.round(state.readerCurrentProgress * 100)}%`;
  }
  if (readerBookContent) {
    readerBookContent.innerHTML = renderBookContent(book);
    readerBookContent.scrollTop = 0;
  }
}

function openReaderWithResume(objectId, resumePayload) {
  openReaderModal(objectId);
  if (resumePayload?.book) {
    openReaderBookView(objectId, resumePayload.book, resumePayload.progress ?? 0);
  } else {
    state.suppressReaderModalForBrowse = false;
    state.socket?.emit('room:object:interact', { objectId, interactionType: 'browse_books' });
  }
}

function saveCurrentReadingProgress() {
  if (!state.readerModalObjectId || !state.readerCurrentBook) return;
  state.socket?.emit('room:book:progress:save', {
    objectId: state.readerModalObjectId,
    bookId: state.readerCurrentBook.bookId,
    progress: state.readerCurrentProgress ?? 0,
  });
}

// ─── Phase G: TV / music media player ──────────────────────────────────────

function renderVideoTvSelect() {
  if (!videoTvSelect) return;
  const currentKey = tileKey(state.currentTile);
  const tvs = state.builderState.objects.filter(
    (obj) => tileKey(obj.tile) === currentKey && obj.objectType === 'tv',
  );
  const previousValue = videoTvSelect.value;
  videoTvSelect.innerHTML = tvs.length
    ? tvs.map((s) => `<option value="${escapeHtml(s.objectId)}">${escapeHtml(s.objectId)}</option>`).join('')
    : '<option value="">No TVs on this tile</option>';
  if (tvs.some((s) => s.objectId === previousValue)) {
    videoTvSelect.value = previousValue;
  }
  renderBuilderVideoList();
}

function renderBuilderVideoList() {
  if (!videoListEl) return;
  const objectId = videoTvSelect?.value;
  const videos = objectId ? (state.builderVideos[objectId] || []) : [];
  if (videos.length === 0) {
    videoListEl.innerHTML = '<li class="builder-empty-hint">No videos on this TV yet.</li>';
    return;
  }
  videoListEl.innerHTML = videos.map((v) => `
    <li class="builder-object-row">
      <div class="builder-object-row-header">
        <span>${escapeHtml(v.title)}</span>
        <div class="builder-object-row-actions">
          <button type="button" class="builder-icon-btn" data-action="remove-video" data-video-id="${escapeHtml(v.videoId)}" aria-label="Remove video" title="Remove video">
            <span class="material-symbols-outlined" aria-hidden="true">delete</span>
          </button>
        </div>
      </div>
    </li>`).join('');
}

function renderTrackPlayerSelect() {
  if (!trackPlayerSelect) return;
  const currentKey = tileKey(state.currentTile);
  const players = state.builderState.objects.filter(
    (obj) => tileKey(obj.tile) === currentKey && obj.objectType === 'music_player',
  );
  const previousValue = trackPlayerSelect.value;
  trackPlayerSelect.innerHTML = players.length
    ? players.map((s) => `<option value="${escapeHtml(s.objectId)}">${escapeHtml(s.objectId)}</option>`).join('')
    : '<option value="">No music players on this tile</option>';
  if (players.some((s) => s.objectId === previousValue)) {
    trackPlayerSelect.value = previousValue;
  }
  renderBuilderTrackList();
}

function renderBuilderTrackList() {
  if (!trackListEl) return;
  const objectId = trackPlayerSelect?.value;
  const tracks = objectId ? (state.builderTracks[objectId] || []) : [];
  if (tracks.length === 0) {
    trackListEl.innerHTML = '<li class="builder-empty-hint">No tracks on this player yet.</li>';
    return;
  }
  trackListEl.innerHTML = tracks.map((t) => `
    <li class="builder-object-row">
      <div class="builder-object-row-header">
        <span>${escapeHtml(t.title)}</span>
        <div class="builder-object-row-actions">
          <button type="button" class="builder-icon-btn" data-action="remove-track" data-track-id="${escapeHtml(t.trackId)}" aria-label="Remove track" title="Remove track">
            <span class="material-symbols-outlined" aria-hidden="true">delete</span>
          </button>
        </div>
      </div>
    </li>`).join('');
}

function openMediaModal(objectId, objectType) {
  state.mediaModalObjectId = objectId;
  state.mediaModalObjectType = objectType;
  state.mediaCurrentItem = null;
  mediaModal?.classList.remove('hidden');
  mediaPlaylistView?.classList.remove('hidden');
  mediaPlayerView?.classList.add('hidden');
  if (mediaModalTitle) mediaModalTitle.textContent = objectType === 'tv' ? 'TV Playlist' : 'Music Playlist';
}

function closeMediaModal() {
  mediaModal?.classList.add('hidden');
  state.mediaModalObjectId = null;
  state.mediaModalObjectType = null;
  state.mediaCurrentItem = null;
  state.mediaSyncSession = null;
  if (mediaVideoFrame) mediaVideoFrame.innerHTML = '';
}

function renderMediaPlaylist(objectType, items) {
  if (!mediaPlaylistList) return;
  if (!items.length) {
    mediaPlaylistList.innerHTML = `<li class="builder-empty-hint">No ${objectType === 'tv' ? 'videos' : 'tracks'} yet.</li>`;
    return;
  }
  mediaPlaylistList.innerHTML = items.map((item) => {
    const itemId = objectType === 'tv' ? item.videoId : item.trackId;
    const meta = objectType === 'tv'
      ? (item.description ? truncateSummary(item.description) : '')
      : [item.artist, formatDuration(item.durationSeconds)].filter(Boolean).join(' \u00b7 ');
    return `
      <li class="reader-book-list-item" data-item-id="${escapeHtml(itemId)}">
        <div>
          <div class="reader-book-list-item-title">${escapeHtml(item.title)}</div>
          ${meta ? `<div class="reader-book-list-item-meta">${escapeHtml(meta)}</div>` : ''}
        </div>
      </li>`;
  }).join('');
}

function openMediaPlayerView(objectId, objectType, item, syncSession) {
  state.mediaModalObjectId = objectId;
  state.mediaModalObjectType = objectType;
  state.mediaCurrentItem = item;
  mediaModal?.classList.remove('hidden');
  mediaPlaylistView?.classList.add('hidden');
  mediaPlayerView?.classList.remove('hidden');
  if (mediaModalTitle) mediaModalTitle.textContent = objectType === 'tv' ? 'TV' : 'Music Player';

  if (!item) {
    if (mediaItemTitle) mediaItemTitle.textContent = objectType === 'tv' ? 'No videos yet' : 'No tracks yet';
    if (mediaItemMeta) mediaItemMeta.textContent = '';
    if (mediaVideoFrame) mediaVideoFrame.innerHTML = '';
    updateMediaSyncUi(null);
    return;
  }

  if (mediaItemTitle) mediaItemTitle.textContent = item.title;
  if (mediaItemMeta) {
    mediaItemMeta.textContent = objectType === 'tv'
      ? (item.description ? truncateSummary(item.description) : '')
      : [item.artist, formatDuration(item.durationSeconds)].filter(Boolean).join(' \u00b7 ');
  }
  if (mediaVideoFrame) {
    mediaVideoFrame.innerHTML = `<iframe src="https://www.youtube.com/embed/${encodeURIComponent(item.youtubeVideoId)}" title="${escapeHtml(item.title)}" allow="autoplay; encrypted-media" allowfullscreen></iframe>`;
  }
  updateMediaSyncUi(syncSession);
}

function updateMediaSyncUi(session) {
  const currentItemId = state.mediaCurrentItem
    ? (state.mediaModalObjectType === 'tv' ? state.mediaCurrentItem.videoId : state.mediaCurrentItem.trackId)
    : null;
  const applicableSession = sessionAppliesToItem(session, currentItemId) ? session : null;
  state.mediaSyncSession = applicableSession;
  if (!mediaSyncStatus || !mediaSyncToggleBtn) return;

  if (!applicableSession) {
    mediaSyncStatus.textContent = '';
    mediaSyncToggleBtn.textContent = 'Watch Together';
    mediaSyncToggleBtn.classList.remove('active');
    mediaSyncToggleBtn.dataset.mode = 'start';
    mediaSyncToggleBtn.disabled = !state.mediaCurrentItem;
    return;
  }

  const myId = state.playerId;
  const isHost = applicableSession.hostId === myId;
  const isParticipant = applicableSession.participants.includes(myId);
  const others = applicableSession.participants.filter((id) => id !== myId).length;
  const position = formatDuration(computeSyncPosition(applicableSession, Date.now()));

  mediaSyncStatus.textContent = isParticipant
    ? `${applicableSession.isPlaying ? 'Playing' : 'Paused'} together \u00b7 ${position}${others > 0 ? ` \u00b7 ${others} other${others === 1 ? '' : 's'}` : ''}`
    : `${applicableSession.participants.length} watching together \u00b7 ${position}`;

  mediaSyncToggleBtn.disabled = false;
  mediaSyncToggleBtn.classList.toggle('active', isParticipant);
  if (isParticipant) {
    mediaSyncToggleBtn.textContent = isHost ? 'End for Everyone' : 'Leave';
    mediaSyncToggleBtn.dataset.mode = isHost ? 'end' : 'leave';
  } else {
    mediaSyncToggleBtn.textContent = 'Join Watch Together';
    mediaSyncToggleBtn.dataset.mode = 'join';
  }
}

// ─── Phase H: AI story characters ──────────────────────────────────────────

function renderModerationPanel() {
  if (!moderationSection) return;
  const canMod = canModerate(state.myRoomRole);
  moderationSection.classList.toggle('hidden', !canMod);
  if (!canMod) return;

  const canAssign = canAssignRoles(state.myRoomRole);
  if (externalLinksField) externalLinksField.classList.toggle('hidden', !canAssign);

  if (!moderationPlayerListEl) return;
  const rows = [];
  for (const [id, player] of state.players) {
    if (id === state.playerId) continue;
    const role = id === state.roomHostId ? 'owner' : (state.playerRoles.get(id) || 'participant');
    const muted = state.mutedPlayers.has(id);
    const username = escapeHtml(player.avatar?.username || id);
    const roleControls = canAssign && role !== 'owner'
      ? `<select class="mod-role-select" data-player-id="${id}">
          ${ASSIGNABLE_ROLES.map((r) => `<option value="${r}" ${r === role ? 'selected' : ''}>${formatRoleLabel(r)}</option>`).join('')}
        </select>`
      : `<span class="builder-object-chip">${formatRoleLabel(role)}</span>`;
    const actionButtons = role === 'owner' ? '' : `
        <button type="button" class="builder-primary-btn mod-mute-btn" data-player-id="${id}">${muted ? 'Unmute' : 'Mute'}</button>
        <button type="button" class="builder-primary-btn mod-kick-btn" data-player-id="${id}">Kick</button>
        <button type="button" class="builder-primary-btn mod-ban-btn" data-player-id="${id}">Ban</button>`;
    rows.push(`
      <li class="builder-object-row">
        <div class="builder-object-row-meta"><strong>${username}</strong>${roleControls}</div>
        <div class="builder-object-row-meta">${actionButtons}</div>
      </li>`);
  }
  moderationPlayerListEl.innerHTML = rows.join('') || '<li>No other players in this room.</li>';
}

function renderCharacterNpcSelect() {
  if (!characterNpcSelect) return;
  const currentKey = tileKey(state.currentTile);
  const npcs = state.builderState.objects.filter(
    (obj) => tileKey(obj.tile) === currentKey && obj.objectType === 'ai_character',
  );
  const previousValue = characterNpcSelect.value;
  characterNpcSelect.innerHTML = npcs.length
    ? npcs.map((s) => `<option value="${escapeHtml(s.objectId)}">${escapeHtml(s.objectId)}</option>`).join('')
    : '<option value="">No AI characters on this tile</option>';
  if (npcs.some((s) => s.objectId === previousValue)) {
    characterNpcSelect.value = previousValue;
  }
  renderCharacterConfigFields();
  renderBuilderStoryNodeList();
}

function renderCharacterConfigFields() {
  const objectId = characterNpcSelect?.value;
  const character = objectId ? state.builderCharacters[objectId] : null;
  if (characterNameInput) characterNameInput.value = character?.name || '';
  if (characterRoleSelect) characterRoleSelect.value = character?.role || 'guide';
  if (characterStartNodeInput) characterStartNodeInput.value = character?.startNodeId || '';
  if (characterPortraitInput) characterPortraitInput.value = character?.portraitUrl || '';
  if (characterKnowledgeBaseInput) characterKnowledgeBaseInput.value = character?.knowledgeBase || '';
  if (characterApiUrlInput) characterApiUrlInput.value = character?.apiBaseUrl || '';
}

function renderBuilderStoryNodeList() {
  if (!storyNodeListEl) return;
  const objectId = characterNpcSelect?.value;
  const nodes = objectId ? (state.builderStoryNodes[objectId] || []) : [];
  if (nodes.length === 0) {
    storyNodeListEl.innerHTML = '<li class="builder-empty-hint">No story nodes yet.</li>';
    return;
  }
  storyNodeListEl.innerHTML = nodes.map((n) => `
    <li class="builder-object-row">
      <div class="builder-object-row-header">
        <span>${escapeHtml(n.nodeId)}</span>
      </div>
      <div class="builder-object-row-meta">${escapeHtml(n.characterLine)}</div>
    </li>`).join('');
}

function openDialogueModal(objectId, character, node, mode) {
  state.dialogueModalObjectId = objectId;
  dialogueModal?.classList.remove('hidden');
  if (dialogueModalTitle) dialogueModalTitle.textContent = character?.name || 'Character';
  if (dialogueAnswer) dialogueAnswer.textContent = '';
  if (dialogueAskInput) dialogueAskInput.value = '';
  renderDialogueNode(node, mode);
}

function closeDialogueModal() {
  dialogueModal?.classList.add('hidden');
  state.dialogueModalObjectId = null;
  state.dialogueCurrentNode = null;
}

function renderDialogueNode(node, mode) {
  state.dialogueCurrentNode = node || null;
  if (dialogueModeIndicator) {
    dialogueModeIndicator.textContent = formatModeLabel(mode);
    dialogueModeIndicator.classList.toggle('generative', mode === 'generative');
  }
  if (dialogueCharacterLine) {
    dialogueCharacterLine.textContent = node?.characterLine || 'Ask me a question and I\'ll do my best to help!';
  }
  if (!dialogueChoiceList) return;
  const choices = node?.choices || [];
  dialogueChoiceList.innerHTML = choices.length
    ? choices.map((choice, index) => `
        <li>
          <button type="button" class="builder-primary-btn" data-choice-index="${index}">${escapeHtml(choice.text)}</button>
        </li>`).join('')
    : '';
}

function handleObjectInteractionResult(result) {
  if (!result) return;
  if (result.interactionType === 'browse_books') {
    state.builderBooks[result.objectId] = result.payload.books;
    if (bookShelfSelect?.value === result.objectId) renderBuilderBookList();
    if (state.suppressReaderModalForBrowse) {
      state.suppressReaderModalForBrowse = false;
      return;
    }
    openReaderModal(result.objectId);
    renderReaderBookList(result.objectId, result.payload.books);
    return;
  }
  if (result.interactionType === 'resume_reading') {
    openReaderWithResume(result.objectId, result.payload);
    return;
  }
  if (result.interactionType === 'open_playlist') {
    state.builderVideos[result.objectId] = result.payload.videos;
    if (videoTvSelect?.value === result.objectId) renderBuilderVideoList();
    if (state.suppressMediaModalForBrowse) {
      state.suppressMediaModalForBrowse = false;
      return;
    }
    openMediaModal(result.objectId, 'tv');
    renderMediaPlaylist('tv', result.payload.videos);
    return;
  }
  if (result.interactionType === 'watch_video') {
    openMediaPlayerView(result.objectId, 'tv', result.payload.video, result.payload.syncSession);
    return;
  }
  if (result.interactionType === 'view_playlist') {
    state.builderTracks[result.objectId] = result.payload.tracks;
    if (trackPlayerSelect?.value === result.objectId) renderBuilderTrackList();
    if (state.suppressMediaModalForBrowse) {
      state.suppressMediaModalForBrowse = false;
      return;
    }
    openMediaModal(result.objectId, 'music_player');
    renderMediaPlaylist('music_player', result.payload.tracks);
    return;
  }
  if (result.interactionType === 'play_track') {
    openMediaPlayerView(result.objectId, 'music_player', result.payload.track, result.payload.syncSession);
    return;
  }
  if (result.interactionType === 'talk' || result.interactionType === 'start_mission') {
    openDialogueModal(result.objectId, result.payload.character, result.payload.node, result.payload.mode);
    return;
  }
  if (result.interactionType === 'ask_hint') {
    openDialogueModal(result.objectId, result.payload.character, null, resolveCharacterMode(result.payload.character));
    return;
  }
  addSystemMessage(`${result.label || 'Interaction'} triggered.`);
}

function renderBuilderZoneList() {
  if (!zoneListEl) return;
  const currentKey = tileKey(state.currentTile);
  const zones = state.builderState.zones.filter((zone) => tileKey(zone.tile) === currentKey);

  if (zones.length === 0) {
    zoneListEl.innerHTML = '<li class="builder-empty-hint">No zones on this tile yet.</li>';
  } else {
    zoneListEl.innerHTML = zones.map((zone) => `
      <li class="builder-object-row" data-zone-id="${escapeHtml(zone.zoneId)}">
        <div class="builder-object-row-header">
          <span>${escapeHtml(zone.zoneType)} (${zone.minX}, ${zone.minY} → ${zone.maxX}, ${zone.maxY})</span>
          <button type="button" class="builder-icon-btn" data-action="delete" data-zone-id="${escapeHtml(zone.zoneId)}" aria-label="Delete zone" title="Delete zone">
            <span class="material-symbols-outlined" aria-hidden="true">delete</span>
          </button>
        </div>
      </li>`).join('');
  }

  if (triggerZoneSelect) {
    const previous = triggerZoneSelect.value;
    triggerZoneSelect.innerHTML = zones.map((zone) =>
      `<option value="${escapeHtml(zone.zoneId)}">${escapeHtml(zone.zoneId)} (${escapeHtml(zone.zoneType)})</option>`
    ).join('');
    if (zones.some((zone) => zone.zoneId === previous)) {
      triggerZoneSelect.value = previous;
    }
  }
}

function renderBuilderTriggerList() {
  if (!triggerListEl) return;
  const currentKey = tileKey(state.currentTile);
  const triggers = state.builderState.triggers.filter((trigger) => tileKey(trigger.tile) === currentKey);

  if (triggers.length === 0) {
    triggerListEl.innerHTML = '<li class="builder-empty-hint">No triggers on this tile yet.</li>';
    return;
  }

  triggerListEl.innerHTML = triggers.map((trigger) => `
    <li class="builder-object-row" data-trigger-id="${escapeHtml(trigger.triggerId)}">
      <div class="builder-object-row-header">
        <span>${escapeHtml(trigger.eventType)} · zone ${escapeHtml(trigger.zoneId)}${trigger.repeatable ? ' (repeatable)' : ''}</span>
        <button type="button" class="builder-icon-btn" data-action="delete" data-trigger-id="${escapeHtml(trigger.triggerId)}" aria-label="Delete trigger" title="Delete trigger">
          <span class="material-symbols-outlined" aria-hidden="true">delete</span>
        </button>
      </div>
    </li>`).join('');
}

function renderBuilderVersionList() {
  if (!versionListEl) return;
  if (state.builderVersions.length === 0) {
    versionListEl.innerHTML = '<li class="builder-empty-hint">No saved drafts yet.</li>';
    return;
  }

  versionListEl.innerHTML = state.builderVersions.map((version) => `
    <li class="builder-version-row ${version.isActive ? 'is-active' : ''}">
      <span>v${version.versionNumber}${version.isActive ? ' · published' : ''}</span>
      <button type="button" data-action="rollback" data-version="${version.versionNumber}">Rollback</button>
    </li>`).join('');
}

function renderMiniMap() {
  if (!miniMapEl) return;
  const cells = buildMiniMapCells(state.roomTiles, state.currentTile);
  miniMapEl.innerHTML = '';
  cells.forEach((cell) => {
    const node = document.createElement('span');
    node.className = 'mini-map-cell';
    if (cell.active) node.classList.add('active');
    if (cell.current) node.classList.add('current');
    node.title = `(${cell.x}, ${cell.y})`;
    miniMapEl.appendChild(node);
  });
}

function renderRoomList() {
  if (!roomListEl) return;
  if (!state.roomList.length) {
    roomListEl.innerHTML = '<div class="room-card"><p>No rooms yet. Create the first one.</p></div>';
    return;
  }

  roomListEl.innerHTML = '';
  state.roomList.forEach((room) => {
    const card = document.createElement('div');
    card.className = 'room-card';
    const isCurrent = room.id === state.currentRoomId;
    const joinable = canJoinRoom(room);
    const joinDisabled = isCurrent || !joinable;
    const joinLabel = isCurrent ? 'Current Room' : (joinable ? 'Join Room' : 'Room Full');
    const inviteHint = room.access === 'invite' ? 'Invite code required' : '';
    card.innerHTML = `
      <h4>${escapeHtml(room.name)}</h4>
      <p>${escapeHtml(buildRoomMetaLine(room))}</p>
      ${inviteHint ? `<p>${escapeHtml(inviteHint)}</p>` : ''}
      <div class="room-card-actions">
        <button class="room-join-btn" data-room-id="${escapeHtml(room.id)}" ${joinDisabled ? 'disabled' : ''}>${joinLabel}</button>
      </div>
    `;

    const joinBtn = card.querySelector('.room-join-btn');
    if (!joinDisabled) {
      joinBtn.addEventListener('click', () => {
        const inviteCode = room.access === 'invite' ? (roomInviteCode?.value.trim() || undefined) : undefined;
        state.socket?.emit('room:join', { roomId: room.id, inviteCode });
      });
    }

    roomListEl.appendChild(card);
  });
}

function getRoomFiltersFromUi() {
  return normalizeRoomFilters({
    topic: roomFilterTopic?.value,
    access: roomFilterAccess?.value,
    sort: roomFilterSort?.value,
  });
}

function requestRoomList() {
  if (!state.socket) return;
  state.roomFilters = getRoomFiltersFromUi();
  state.socket.emit('room:list', state.roomFilters);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

const THEME_STORAGE_KEY = 'hobboverse-theme';

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);

  const meta = document.querySelector('meta[name="theme-color"]');
  meta?.setAttribute('content', theme === 'light' ? '#fffbff' : '#16111c');

  if (!themeToggleBtn) return;
  const icon = themeToggleBtn.querySelector('.material-symbols-outlined');
  if (icon) icon.textContent = theme === 'light' ? 'dark_mode' : 'light_mode';
  themeToggleBtn.setAttribute('aria-pressed', String(theme === 'light'));
  themeToggleBtn.setAttribute('aria-label', theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode');
}

function initTheme() {
  let stored = null;
  try {
    stored = localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    stored = null;
  }

  const prefersLight = window.matchMedia?.('(prefers-color-scheme: light)').matches;
  const theme = stored === 'light' || stored === 'dark' ? stored : (prefersLight ? 'light' : 'dark');
  applyTheme(theme);

  themeToggleBtn?.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // ignore storage failures (e.g. private browsing)
    }
    applyTheme(next);
  });
}

initTheme();
initCreator();
