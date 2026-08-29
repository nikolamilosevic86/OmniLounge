/**
 * "More" accordion expand/collapse persistence (design doc
 * feature_designs/build_mode_ui_redesign_feature_design.md Decision D6). The
 * More tab's 5 rows (Zones, Triggers, Escape Room, Room Admin, Versions) are
 * collapsed by default; whichever the user expands should stay expanded
 * across a page reload. `storage` is passed in explicitly (rather than read
 * from a module-level `localStorage` global) so this stays a pure, testable
 * module -- callers pass `window.localStorage` in the browser.
 */

const ACCORDION_STORAGE_KEY = 'hobboverse-build-accordion-expanded';

/** Reads the list of currently-expanded row ids, tolerating missing/corrupt storage. */
export function loadExpandedAccordionRows(storage) {
  if (!storage) return [];
  try {
    const raw = storage.getItem(ACCORDION_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === 'string') : [];
  } catch {
    return [];
  }
}

/** Persists the list of currently-expanded row ids, silently ignoring storage failures. */
export function saveExpandedAccordionRows(storage, rowIds) {
  if (!storage) return;
  try {
    storage.setItem(ACCORDION_STORAGE_KEY, JSON.stringify(rowIds));
  } catch {
    // ignore storage failures (e.g. private browsing quota)
  }
}

/** Returns a new expanded-row-id list with `rowId` toggled in/out. */
export function toggleAccordionRow(expandedRowIds, rowId) {
  return expandedRowIds.includes(rowId)
    ? expandedRowIds.filter((id) => id !== rowId)
    : [...expandedRowIds, rowId];
}
