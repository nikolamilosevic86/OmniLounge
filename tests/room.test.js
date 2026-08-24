import { describe, it, expect, beforeEach } from 'vitest';
import { Room } from '../src/room.js';
import { createDefaultAvatar } from '../src/avatar.js';
import { createMessage } from '../src/chat.js';

describe('Room', () => {
  let room;

  beforeEach(() => {
    room = new Room('lobby');
  });

  describe('addPlayer', () => {
    it('adds a player to the room', () => {
      const avatar = createDefaultAvatar('Alice');
      const player = room.addPlayer('p1', avatar);

      expect(player.id).toBe('p1');
      expect(player.avatar.username).toBe('Alice');
      expect(room.getPlayerCount()).toBe(1);
    });

    it('assigns starting position to new player', () => {
      const avatar = createDefaultAvatar('Bob');
      const player = room.addPlayer('p2', avatar);

      expect(player.position).toBeDefined();
      expect(player.position.x).toBeTypeOf('number');
      expect(player.position.y).toBeTypeOf('number');
    });
  });

  describe('removePlayer', () => {
    it('removes a player from the room', () => {
      room.addPlayer('p1', createDefaultAvatar('Alice'));
      room.removePlayer('p1');

      expect(room.getPlayerCount()).toBe(0);
      expect(room.getPlayer('p1')).toBeUndefined();
    });
  });

  describe('updatePlayerPosition', () => {
    it('updates player position within bounds', () => {
      room.addPlayer('p1', createDefaultAvatar('Alice'));
      const updated = room.updatePlayerPosition('p1', { x: 200, y: 150 });

      expect(updated.position.x).toBe(200);
      expect(updated.position.y).toBe(150);
    });

    it('clamps position to room bounds', () => {
      room.addPlayer('p1', createDefaultAvatar('Alice'));
      const updated = room.updatePlayerPosition('p1', { x: -100, y: 9999 });

      expect(updated.position.x).toBeGreaterThanOrEqual(0);
    });
  });

  describe('getAllPlayers', () => {
    it('returns all players in the room', () => {
      room.addPlayer('p1', createDefaultAvatar('Alice'));
      room.addPlayer('p2', createDefaultAvatar('Bob'));

      const players = room.getAllPlayers();
      expect(players).toHaveLength(2);
    });
  });

  describe('addMessage', () => {
    it('stores a public message', () => {
      const msg = createMessage({
        senderId: 'p1',
        senderName: 'Alice',
        text: 'Hello!',
        type: 'public',
      });

      room.addMessage(msg);
      expect(room.getMessages()).toHaveLength(1);
    });
  });

  describe('getMessagesForPlayer', () => {
    it('returns messages visible to a specific player', () => {
      room.addPlayer('p1', createDefaultAvatar('Alice'));
      room.addPlayer('p2', createDefaultAvatar('Bob'));

      room.addMessage(createMessage({
        senderId: 'p1', senderName: 'Alice', text: 'Public msg', type: 'public',
      }));
      room.addMessage(createMessage({
        senderId: 'p1', senderName: 'Alice', text: 'Private msg', type: 'private', recipientId: 'p2',
      }));

      const forP2 = room.getMessagesForPlayer('p2');
      expect(forP2).toHaveLength(2);

      const forP3 = room.getMessagesForPlayer('p3');
      expect(forP3).toHaveLength(1);
      expect(forP3[0].text).toBe('Public msg');
    });
  });

  describe('getActiveBubbles', () => {
    it('returns recent messages as speech bubbles', () => {
      room.addPlayer('p1', createDefaultAvatar('Alice'));

      const msg = createMessage({
        senderId: 'p1', senderName: 'Alice', text: 'Bubble test', type: 'public',
      });
      room.addMessage(msg);

      const bubbles = room.getActiveBubbles('p2');
      expect(bubbles).toHaveLength(1);
      expect(bubbles[0].text).toBe('Bubble test');
      expect(bubbles[0].senderId).toBe('p1');
    });

    it('hides private bubbles from non-participants', () => {
      room.addPlayer('p1', createDefaultAvatar('Alice'));
      room.addPlayer('p2', createDefaultAvatar('Bob'));

      room.addMessage(createMessage({
        senderId: 'p1', senderName: 'Alice', text: 'Secret', type: 'private', recipientId: 'p2',
      }));

      const bubblesForP3 = room.getActiveBubbles('p3');
      expect(bubblesForP3).toHaveLength(0);

      const bubblesForP2 = room.getActiveBubbles('p2');
      expect(bubblesForP2).toHaveLength(1);
    });
  });
});
