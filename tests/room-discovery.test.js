import { describe, it, expect } from 'vitest';
import {
  normalizeRooms,
  buildRoomMetaLine,
  canJoinRoom,
  normalizeRoomFilters,
} from '../src/room-discovery.js';

describe('normalizeRooms', () => {
  it('sorts rooms by active users desc, then createdAt desc', () => {
    const rooms = [
      { id: 'b', name: 'B', activeUsers: 3, createdAtMs: 10 },
      { id: 'c', name: 'C', activeUsers: 3, createdAtMs: 20 },
      { id: 'a', name: 'A', activeUsers: 1, createdAtMs: 30 },
    ];
    const result = normalizeRooms(rooms);
    expect(result.map(r => r.id)).toEqual(['c', 'b', 'a']);
  });

  it('normalizes missing optional fields', () => {
    const result = normalizeRooms([{ id: 'x', name: 'X' }]);
    expect(result[0].topicTags).toEqual([]);
    expect(result[0].access).toBe('public');
    expect(result[0].activeUsers).toBe(0);
    expect(result[0].maxUsers).toBe(30);
  });
});

describe('buildRoomMetaLine', () => {
  it('builds readable meta text from room summary fields', () => {
    const line = buildRoomMetaLine({
      access: 'invite',
      activeUsers: 5,
      maxUsers: 20,
      topicTags: ['history', 'museum'],
    });
    expect(line).toContain('Invite');
    expect(line).toContain('5/20 online');
    expect(line).toContain('history');
    expect(line).toContain('museum');
  });
});

describe('canJoinRoom', () => {
  it('returns false if room is full', () => {
    expect(canJoinRoom({ activeUsers: 10, maxUsers: 10 })).toBe(false);
  });

  it('returns true if room has capacity', () => {
    expect(canJoinRoom({ activeUsers: 9, maxUsers: 10 })).toBe(true);
  });
});

describe('normalizeRoomFilters', () => {
  it('applies defaults for missing fields', () => {
    expect(normalizeRoomFilters()).toEqual({
      topic: '',
      access: 'all',
      sort: 'newest',
    });
  });

  it('normalizes topic/access/sort values', () => {
    expect(
      normalizeRoomFilters({
        topic: '  HISTORY ',
        access: 'invite',
        sort: 'active',
      })
    ).toEqual({
      topic: 'history',
      access: 'invite',
      sort: 'active',
    });
  });

  it('falls back to safe values for unsupported access/sort', () => {
    expect(
      normalizeRoomFilters({
        topic: 'science',
        access: 'private',
        sort: 'popular',
      })
    ).toEqual({
      topic: 'science',
      access: 'all',
      sort: 'newest',
    });
  });
});
