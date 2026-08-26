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
