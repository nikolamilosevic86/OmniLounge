import { createPosition, clampPosition } from './movement.js';
import { getVisibleMessages, shouldShowBubble } from './chat.js';

const BUBBLE_DURATION_MS = 5000;
const MAX_MESSAGES = 100;

export class Room {
  constructor(id) {
    this.id = id;
    this.players = new Map();
    this.messages = [];
  }

  addPlayer(playerId, avatar) {
    const player = {
      id: playerId,
      avatar,
      position: createPosition(),
      targetPosition: null,
    };
    this.players.set(playerId, player);
    return player;
  }

  removePlayer(playerId) {
    this.players.delete(playerId);
  }

  getPlayer(playerId) {
    return this.players.get(playerId);
  }

  getPlayerCount() {
    return this.players.size;
  }

  getAllPlayers() {
    return Array.from(this.players.values());
  }

  updatePlayerPosition(playerId, position) {
    const player = this.players.get(playerId);
    if (!player) return null;

    player.position = clampPosition(position);
    return player;
  }

  setPlayerTarget(playerId, target) {
    const player = this.players.get(playerId);
    if (!player) return null;

    player.targetPosition = clampPosition(target);
    return player;
  }

  addMessage(message) {
    this.messages.push(message);
    if (this.messages.length > MAX_MESSAGES) {
      this.messages.shift();
    }
  }

  getMessages() {
    return [...this.messages];
  }

  getMessagesForPlayer(playerId) {
    return getVisibleMessages(this.messages, playerId);
  }

  getActiveBubbles(viewerId) {
    const now = Date.now();
    return this.messages
      .filter(msg => now - msg.timestamp < BUBBLE_DURATION_MS)
      .filter(msg => shouldShowBubble(msg, viewerId))
      .map(msg => ({
        senderId: msg.senderId,
        senderName: msg.senderName,
        text: msg.text,
        type: msg.type,
        timestamp: msg.timestamp,
      }));
  }
}
