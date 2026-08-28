let messageCounter = 0;

export function createMessage({ senderId, senderName, text, type, recipientId = null }) {
  return {
    id: `msg_${++messageCounter}_${Date.now()}`,
    senderId,
    senderName,
    text,
    type,
    recipientId,
    timestamp: Date.now(),
  };
}

export function shouldShowBubble(message, viewerId) {
  if (message.type === 'public') {
    return true;
  }
  if (message.type === 'private') {
    return message.senderId === viewerId || message.recipientId === viewerId;
  }
  return false;
}

export function getVisibleMessages(messages, userId) {
  return messages.filter(msg => shouldShowBubble(msg, userId));
}

export function filterMessagesForUser(messages, userId) {
  return getVisibleMessages(messages, userId);
}

export function canSendChatMessage(mutedPlayerIds, userId) {
  return !mutedPlayerIds.has(userId);
}

// ── Whisper recipient picker ───────────────────────────────────────────────
// The recipient <select> is refreshed from the `room:state` broadcast, which
// the server sends on every tick in which any player moved. Rebuilding the
// options unconditionally therefore both churns the DOM many times a second
// and resets the user's chosen recipient, silently turning their whisper into
// a no-op whenever somebody else is walking. These helpers keep that decision
// pure and testable: derive the options, compare against what is already
// rendered, and re-resolve the selection only when a rebuild is unavoidable.

export function whisperRecipientOptions(players, viewerId) {
  const options = [];
  for (const [id, player] of players) {
    if (id === viewerId) continue;
    options.push({ id, label: player?.avatar?.username || id });
  }
  return options;
}

export function recipientOptionsChanged(previous, next) {
  if (previous.length !== next.length) return true;
  return next.some((option, i) => (
    option.id !== previous[i].id || option.label !== previous[i].label
  ));
}

export function resolveRecipientSelection(options, currentSelection) {
  if (!currentSelection) return '';
  return options.some(option => option.id === currentSelection) ? currentSelection : '';
}
