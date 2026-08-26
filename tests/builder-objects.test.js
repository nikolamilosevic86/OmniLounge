import { describe, it, expect } from 'vitest';
import {
  getBuilderObjectAtPoint,
  resolveObjectColor,
  objectTypeIcon,
  buildInteractionActions,
} from '../src/builder-objects.js';

describe('getBuilderObjectAtPoint', () => {
  const objects = [
    { objectId: 'a', x: 10, y: 10, width: 40, height: 40, zIndex: 0 },
    { objectId: 'b', x: 20, y: 20, width: 40, height: 40, zIndex: 1 },
  ];

  it('returns null when no object contains the point', () => {
    expect(getBuilderObjectAtPoint(objects, 500, 500)).toBeNull();
  });

  it('returns null for an empty object list', () => {
    expect(getBuilderObjectAtPoint([], 15, 15)).toBeNull();
  });

  it('returns the object whose bounds contain the point', () => {
    const hit = getBuilderObjectAtPoint(objects, 15, 15);
    expect(hit.objectId).toBe('a');
  });

  it('returns the topmost (highest zIndex) object when rects overlap', () => {
    const hit = getBuilderObjectAtPoint(objects, 25, 25);
    expect(hit.objectId).toBe('b');
  });

  it('treats bounds as inclusive at the edges', () => {
    const hit = getBuilderObjectAtPoint(objects, 10, 10);
    expect(hit.objectId).toBe('a');
  });
});

describe('resolveObjectColor', () => {
  it('returns a hex color for a known preset', () => {
    expect(resolveObjectColor('navy')).toBe('#1f3a5f');
  });

  it('returns a fallback color for null/undefined', () => {
    expect(resolveObjectColor(null)).toMatch(/^#/);
    expect(resolveObjectColor(undefined)).toMatch(/^#/);
  });

  it('returns a fallback color for an unknown preset', () => {
    expect(resolveObjectColor('mystery')).toMatch(/^#/);
  });
});

describe('objectTypeIcon', () => {
  it('returns a distinct icon for each known object type', () => {
    const types = ['table', 'chair', 'bar', 'sofa', 'bookshelf', 'tv', 'music_player', 'ai_character'];
    const icons = types.map(objectTypeIcon);
    expect(new Set(icons).size).toBe(types.length);
    expect(objectTypeIcon('ai_character')).not.toBe(objectTypeIcon('unknown-thing'));
  });

  it('returns a fallback icon for an unknown type', () => {
    expect(objectTypeIcon('unknown-thing')).toBeTruthy();
  });
});

describe('buildInteractionActions', () => {
  it('returns an empty array when there are no interactions', () => {
    expect(buildInteractionActions([])).toEqual([]);
  });

  it('maps each interaction to an action with icon, label, and interactionType', () => {
    const interactions = [
      { interactionType: 'sit', label: 'Sit down', actionState: 'sitting' },
      { interactionType: 'watch_video', label: 'Watch Lesson', actionState: null },
    ];
    const actions = buildInteractionActions(interactions);
    expect(actions).toHaveLength(2);
    for (const action of actions) {
      expect(action).toHaveProperty('icon');
      expect(action).toHaveProperty('label');
      expect(action).toHaveProperty('interactionType');
    }
    expect(actions[0].interactionType).toBe('sit');
    expect(actions[0].label).toBe('Sit down');
  });
});
