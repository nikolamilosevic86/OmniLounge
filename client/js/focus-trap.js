// Phase J accessibility pass: pure helpers for trapping keyboard focus
// inside modal dialogs (reader / media / dialogue). Kept dependency-free so
// the traversal/key logic can be unit tested without a real DOM.

export const FOCUSABLE_SELECTOR =
  'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function isEscapeKey(key) {
  return key === 'Escape';
}

/**
 * Compute the next index to focus when Tab (or Shift+Tab) is pressed inside
 * a modal containing `count` focusable elements, wrapping around at the
 * ends. Returns 0 if there are no focusable elements or the current index
 * is unknown (-1).
 */
export function getNextFocusIndex(currentIndex, count, { shiftKey } = {}) {
  if (count <= 0) return 0;
  if (currentIndex < 0) return 0;
  const direction = shiftKey ? -1 : 1;
  return (currentIndex + direction + count) % count;
}

/** `<input>` types that represent real text entry, where arrow keys move a
 * caret and must NOT be hijacked for avatar movement. Everything else
 * (checkbox, radio, range, color, button-likes...) is a non-text control. */
const TEXT_ENTRY_INPUT_TYPES = new Set([
  'text', 'search', 'url', 'tel', 'email', 'password', 'number', 'date',
  'datetime-local', 'month', 'week', 'time',
]);

/**
 * True only when `element` is a genuine TEXT-ENTRY context (chat box, room
 * name filter, builder text fields, or a contenteditable region).
 *
 * Deliberately excludes non-text controls -- above all `<select>` dropdowns
 * and checkboxes. Those keep DOM focus long after the user has finished
 * with them (clicking a `<button>` does not move focus away from them on
 * macOS Safari/Firefox), so treating them as "typing" silently swallowed
 * every arrow key and made the avatar appear permanently stuck. That was
 * the real cause of both "I placed a bookshelf and got stuck" and "I walked
 * to the top edge and nothing happened": after using the build panel's
 * Object Type / Size / Color dropdowns, no `player:direction` was ever
 * emitted again, so the player never actually moved at all.
 *
 * Takes a plain `{ tagName, type, isContentEditable }` shape so it can be
 * unit tested without a real DOM.
 */
export function isTextEntryElement(element) {
  if (!element) return false;
  if (element.isContentEditable) return true;
  const tag = String(element.tagName || '').toUpperCase();
  if (tag === 'TEXTAREA') return true;
  if (tag !== 'INPUT') return false;
  return TEXT_ENTRY_INPUT_TYPES.has(String(element.type || 'text').toLowerCase());
}
