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
