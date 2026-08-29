import { describe, it, expect } from 'vitest';
import {
  loadExpandedAccordionRows,
  saveExpandedAccordionRows,
  toggleAccordionRow,
} from '../src/builder-preferences.js';

function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => { data[key] = String(value); },
    _data: data,
  };
}

describe('loadExpandedAccordionRows (design doc build_mode_ui_redesign_feature_design.md Decision D6)', () => {
  it('returns an empty array when nothing has been stored', () => {
    expect(loadExpandedAccordionRows(fakeStorage())).toEqual([]);
  });

  it('returns the stored row ids', () => {
    const storage = fakeStorage({ 'hobboverse-build-accordion-expanded': '["escape-room","versions"]' });
    expect(loadExpandedAccordionRows(storage)).toEqual(['escape-room', 'versions']);
  });

  it('returns an empty array for malformed stored JSON', () => {
    const storage = fakeStorage({ 'hobboverse-build-accordion-expanded': 'not-json' });
    expect(loadExpandedAccordionRows(storage)).toEqual([]);
  });

  it('returns an empty array when storage is unavailable', () => {
    expect(loadExpandedAccordionRows(null)).toEqual([]);
    expect(loadExpandedAccordionRows(undefined)).toEqual([]);
  });

  it('filters out non-string entries from malformed stored data', () => {
    const storage = fakeStorage({ 'hobboverse-build-accordion-expanded': '["ok", 5, null, "also-ok"]' });
    expect(loadExpandedAccordionRows(storage)).toEqual(['ok', 'also-ok']);
  });
});

describe('saveExpandedAccordionRows', () => {
  it('persists the row ids as JSON', () => {
    const storage = fakeStorage();
    saveExpandedAccordionRows(storage, ['zones', 'triggers']);
    expect(storage._data['hobboverse-build-accordion-expanded']).toBe('["zones","triggers"]');
  });

  it('does not throw when storage is unavailable', () => {
    expect(() => saveExpandedAccordionRows(null, ['zones'])).not.toThrow();
  });
});

describe('toggleAccordionRow', () => {
  it('adds a row id that is not currently expanded', () => {
    expect(toggleAccordionRow(['a'], 'b')).toEqual(['a', 'b']);
  });

  it('removes a row id that is currently expanded', () => {
    expect(toggleAccordionRow(['a', 'b'], 'b')).toEqual(['a']);
  });
});
