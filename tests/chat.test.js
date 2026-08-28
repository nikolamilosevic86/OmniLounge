import { describe, it, expect } from 'vitest';
import {
  createMessage,
  shouldShowBubble,
  getVisibleMessages,
  filterMessagesForUser,
  canSendChatMessage,
  whisperRecipientOptions,
  recipientOptionsChanged,
  resolveRecipientSelection,
} from '../src/chat.js';

describe('Chat', () => {
  describe('createMessage', () => {
    it('creates a public message', () => {
      const msg = createMessage({
        senderId: 'user1',
        senderName: 'Alice',
        text: 'Hello everyone!',
        type: 'public',
      });

      expect(msg.senderId).toBe('user1');
      expect(msg.senderName).toBe('Alice');
      expect(msg.text).toBe('Hello everyone!');
      expect(msg.type).toBe('public');
      expect(msg.recipientId).toBeNull();
      expect(msg.timestamp).toBeTypeOf('number');
      expect(msg.id).toBeTypeOf('string');
    });

    it('creates a private message with recipient', () => {
      const msg = createMessage({
        senderId: 'user1',
        senderName: 'Alice',
        text: 'Secret!',
        type: 'private',
        recipientId: 'user2',
      });

      expect(msg.type).toBe('private');
      expect(msg.recipientId).toBe('user2');
    });
  });

  describe('shouldShowBubble', () => {
    const publicMsg = createMessage({
      senderId: 'user1',
      senderName: 'Alice',
      text: 'Hi!',
      type: 'public',
    });

    const privateMsg = createMessage({
      senderId: 'user1',
      senderName: 'Alice',
      text: 'Secret',
      type: 'private',
      recipientId: 'user2',
    });

    it('shows public bubble to all users', () => {
      expect(shouldShowBubble(publicMsg, 'user1')).toBe(true);
      expect(shouldShowBubble(publicMsg, 'user2')).toBe(true);
      expect(shouldShowBubble(publicMsg, 'user3')).toBe(true);
    });

    it('shows private bubble only to sender and recipient', () => {
      expect(shouldShowBubble(privateMsg, 'user1')).toBe(true);
      expect(shouldShowBubble(privateMsg, 'user2')).toBe(true);
      expect(shouldShowBubble(privateMsg, 'user3')).toBe(false);
    });
  });

  describe('getVisibleMessages', () => {
    const messages = [
      createMessage({ senderId: 'u1', senderName: 'A', text: 'Public', type: 'public' }),
      createMessage({ senderId: 'u1', senderName: 'A', text: 'Private to B', type: 'private', recipientId: 'u2' }),
      createMessage({ senderId: 'u2', senderName: 'B', text: 'Private to A', type: 'private', recipientId: 'u1' }),
    ];

    it('returns all public messages for any user', () => {
      const visible = getVisibleMessages(messages, 'u3');
      expect(visible.some(m => m.text === 'Public')).toBe(true);
    });

    it('returns private messages only for involved parties', () => {
      const forU1 = getVisibleMessages(messages, 'u1');
      expect(forU1.some(m => m.text === 'Private to B')).toBe(true);
      expect(forU1.some(m => m.text === 'Private to A')).toBe(true);

      const forU3 = getVisibleMessages(messages, 'u3');
      expect(forU3.some(m => m.text === 'Private to B')).toBe(false);
      expect(forU3.some(m => m.text === 'Private to A')).toBe(false);
    });
  });

  describe('filterMessagesForUser', () => {
    it('filters chat log for a specific user', () => {
      const messages = [
        createMessage({ senderId: 'u1', senderName: 'A', text: 'Hey all', type: 'public' }),
        createMessage({ senderId: 'u1', senderName: 'A', text: 'Psst', type: 'private', recipientId: 'u2' }),
      ];

      const filtered = filterMessagesForUser(messages, 'u2');
      expect(filtered).toHaveLength(2);
    });

    it('excludes private messages not meant for user', () => {
      const messages = [
        createMessage({ senderId: 'u1', senderName: 'A', text: 'Psst', type: 'private', recipientId: 'u2' }),
      ];

      const filtered = filterMessagesForUser(messages, 'u3');
      expect(filtered).toHaveLength(0);
    });
  });

  describe('canSendChatMessage', () => {
    it('allows sending when the user is not muted', () => {
      const muted = new Set(['u2']);
      expect(canSendChatMessage(muted, 'u1')).toBe(true);
    });

    it('blocks sending when the user is muted', () => {
      const muted = new Set(['u1']);
      expect(canSendChatMessage(muted, 'u1')).toBe(false);
    });

    it('allows sending when the muted set is empty', () => {
      expect(canSendChatMessage(new Set(), 'u1')).toBe(true);
    });
  });
});

describe('whisper recipient list', () => {
  const roster = (...entries) => new Map(
    entries.map(([id, username]) => [id, { avatar: { username } }]),
  );

  describe('whisperRecipientOptions', () => {
    it('lists every other player as an id/label pair', () => {
      const options = whisperRecipientOptions(roster(['p1', 'Alice'], ['p2', 'Bob']), 'p1');
      expect(options).toEqual([{ id: 'p2', label: 'Bob' }]);
    });

    it('excludes the viewer so you cannot whisper yourself', () => {
      const options = whisperRecipientOptions(roster(['p1', 'Alice'], ['p2', 'Bob']), 'p1');
      expect(options.some(o => o.id === 'p1')).toBe(false);
    });

    it('returns an empty list when the viewer is alone', () => {
      expect(whisperRecipientOptions(roster(['p1', 'Alice']), 'p1')).toEqual([]);
    });

    it('falls back to the player id when a username is missing', () => {
      const players = new Map([['p2', { avatar: {} }]]);
      expect(whisperRecipientOptions(players, 'p1')).toEqual([{ id: 'p2', label: 'p2' }]);
    });

    it('tolerates a player record with no avatar at all', () => {
      const players = new Map([['p2', {}]]);
      expect(whisperRecipientOptions(players, 'p1')).toEqual([{ id: 'p2', label: 'p2' }]);
    });
  });

  describe('recipientOptionsChanged', () => {
    // The room:state broadcast fires on every tick in which anyone moved, so
    // rebuilding the <select> unconditionally both churns the DOM and wipes
    // the user's current selection mid-whisper.
    it('is false for identical option lists', () => {
      const a = [{ id: 'p2', label: 'Bob' }];
      const b = [{ id: 'p2', label: 'Bob' }];
      expect(recipientOptionsChanged(a, b)).toBe(false);
    });

    it('is true when a player joins', () => {
      const a = [{ id: 'p2', label: 'Bob' }];
      const b = [{ id: 'p2', label: 'Bob' }, { id: 'p3', label: 'Cara' }];
      expect(recipientOptionsChanged(a, b)).toBe(true);
    });

    it('is true when a player leaves', () => {
      const a = [{ id: 'p2', label: 'Bob' }, { id: 'p3', label: 'Cara' }];
      const b = [{ id: 'p3', label: 'Cara' }];
      expect(recipientOptionsChanged(a, b)).toBe(true);
    });

    it('is true when a player renames', () => {
      const a = [{ id: 'p2', label: 'Bob' }];
      const b = [{ id: 'p2', label: 'Bobby' }];
      expect(recipientOptionsChanged(a, b)).toBe(true);
    });

    it('is true when order changes, since the rendered list would differ', () => {
      const a = [{ id: 'p2', label: 'Bob' }, { id: 'p3', label: 'Cara' }];
      const b = [{ id: 'p3', label: 'Cara' }, { id: 'p2', label: 'Bob' }];
      expect(recipientOptionsChanged(a, b)).toBe(true);
    });

    it('is false for two empty lists', () => {
      expect(recipientOptionsChanged([], [])).toBe(false);
    });
  });

  describe('resolveRecipientSelection', () => {
    it('keeps the current selection when that player is still present', () => {
      const options = [{ id: 'p2', label: 'Bob' }, { id: 'p3', label: 'Cara' }];
      expect(resolveRecipientSelection(options, 'p3')).toBe('p3');
    });

    it('clears the selection when that player has left', () => {
      const options = [{ id: 'p2', label: 'Bob' }];
      expect(resolveRecipientSelection(options, 'p3')).toBe('');
    });

    it('keeps an empty selection empty', () => {
      expect(resolveRecipientSelection([{ id: 'p2', label: 'Bob' }], '')).toBe('');
    });

    it('clears the selection when nobody else is left', () => {
      expect(resolveRecipientSelection([], 'p3')).toBe('');
    });
  });
});
