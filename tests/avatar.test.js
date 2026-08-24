import { describe, it, expect } from 'vitest';
import {
  createDefaultAvatar,
  createAvatar,
  AVATAR_OPTIONS,
  validateAvatar,
  serializeAvatar,
  deserializeAvatar,
} from '../src/avatar.js';

describe('Avatar', () => {
  describe('createDefaultAvatar', () => {
    it('creates an avatar with default appearance', () => {
      const avatar = createDefaultAvatar('Player1');

      expect(avatar.username).toBe('Player1');
      expect(avatar.skinColor).toBe(AVATAR_OPTIONS.skinColors[0]);
      expect(avatar.hair).toBe(AVATAR_OPTIONS.hair[0]);
      expect(avatar.beard).toBe('none');
      expect(avatar.glasses).toBe('none');
      expect(avatar.clothes).toBe(AVATAR_OPTIONS.clothes[0]);
      expect(avatar.accessory).toBe('none');
    });
  });

  describe('createAvatar', () => {
    it('creates a custom avatar with all options', () => {
      const avatar = createAvatar({
        username: 'CoolUser',
        skinColor: '#8D5524',
        hair: 'mohawk',
        beard: 'full',
        glasses: 'round',
        clothes: 'suit',
        accessory: 'hat',
      });

      expect(avatar.username).toBe('CoolUser');
      expect(avatar.skinColor).toBe('#8D5524');
      expect(avatar.hair).toBe('mohawk');
      expect(avatar.beard).toBe('full');
      expect(avatar.glasses).toBe('round');
      expect(avatar.clothes).toBe('suit');
      expect(avatar.accessory).toBe('hat');
    });

    it('falls back to defaults for missing optional fields', () => {
      const avatar = createAvatar({ username: 'Minimal' });

      expect(avatar.skinColor).toBe(AVATAR_OPTIONS.skinColors[0]);
      expect(avatar.hair).toBe(AVATAR_OPTIONS.hair[0]);
    });
  });

  describe('validateAvatar', () => {
    it('returns true for a valid avatar', () => {
      const avatar = createDefaultAvatar('ValidUser');
      expect(validateAvatar(avatar)).toBe(true);
    });

    it('returns false for empty username', () => {
      const avatar = createDefaultAvatar('');
      expect(validateAvatar(avatar)).toBe(false);
    });

    it('returns false for invalid skin color', () => {
      const avatar = createAvatar({ username: 'Test', skinColor: '#INVALID' });
      expect(validateAvatar(avatar)).toBe(false);
    });

    it('returns false for invalid hair option', () => {
      const avatar = createAvatar({ username: 'Test', hair: 'unicorn' });
      expect(validateAvatar(avatar)).toBe(false);
    });
  });

  describe('serialization', () => {
    it('round-trips avatar through serialize/deserialize', () => {
      const original = createAvatar({
        username: 'SerializeTest',
        skinColor: '#C68642',
        hair: 'curly',
        beard: 'goatee',
        glasses: 'square',
        clothes: 'hoodie',
        accessory: 'backpack',
      });

      const json = serializeAvatar(original);
      const restored = deserializeAvatar(json);

      expect(restored).toEqual(original);
    });
  });
});
