/**
 * Radial (pie/circle) context menu.
 *
 * Items pop outward from a centre point with staggered spring animations,
 * like a Habbo Hotel-style action wheel.
 *
 * Usage:
 *   import { showRadialMenu, dismissRadialMenu } from './radial-menu.js';
 *   showRadialMenu(container, roomX, roomY, roomObject, onSelect);
 */

const RADIUS = 72;       // px from centre to item midpoint
const ITEM_SIZE = 52;    // px diameter of each button

let _activeMenu = null;
let _dismissListener = null;

/**
 * @param {HTMLElement} container  — element to append the menu to (players-layer)
 * @param {number}      x          — room-space X coordinate for menu centre
 * @param {number}      y          — room-space Y coordinate
 * @param {object}      obj        — ROOM_OBJECTS entry
 * @param {function}    onSelect   — called with the chosen action object
 */
export function showRadialMenu(container, x, y, obj, onSelect) {
  dismissRadialMenu();

  const menu = document.createElement('div');
  menu.className = 'radial-menu';
  menu.style.left = `${x}px`;
  menu.style.top  = `${y}px`;

  // ── Centre badge ──────────────────────────────────────────────────────────
  const centre = document.createElement('div');
  centre.className = 'radial-centre';
  centre.innerHTML =
    `<span class="radial-obj-icon">${obj.icon}</span>` +
    `<span class="radial-obj-label">${obj.label}</span>`;
  menu.appendChild(centre);

  // ── Action items ──────────────────────────────────────────────────────────
  const actions = obj.actions;
  const n = actions.length;

  actions.forEach((action, i) => {
    // Spread evenly, starting from the top (−π/2)
    const angle  = (i / n) * Math.PI * 2 - Math.PI / 2;
    const ix     = Math.round(Math.cos(angle) * RADIUS);
    const iy     = Math.round(Math.sin(angle) * RADIUS);
    const delay  = i * 45;

    const btn = document.createElement('button');
    btn.className = 'radial-item';
    btn.style.setProperty('--ix', `${ix}px`);
    btn.style.setProperty('--iy', `${iy}px`);
    btn.style.setProperty('--delay', `${delay}ms`);
    btn.setAttribute('aria-label', action.label);
    btn.innerHTML =
      `<span class="radial-icon">${action.icon}</span>` +
      `<span class="radial-label">${action.label}</span>`;

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      dismissRadialMenu();
      onSelect(action);
    });

    menu.appendChild(btn);
  });

  container.appendChild(menu);
  _activeMenu = menu;

  // Dismiss when clicking outside
  _dismissListener = (e) => {
    if (_activeMenu && !_activeMenu.contains(e.target)) {
      dismissRadialMenu();
    }
  };
  // Slight delay so the current click doesn't immediately dismiss it
  setTimeout(() => window.addEventListener('click', _dismissListener), 50);
}

export function dismissRadialMenu() {
  if (_activeMenu) {
    _activeMenu.classList.add('radial-menu--out');
    const el = _activeMenu;
    setTimeout(() => el.remove(), 220);
    _activeMenu = null;
  }
  if (_dismissListener) {
    window.removeEventListener('click', _dismissListener);
    _dismissListener = null;
  }
}

export function hasActiveMenu() {
  return _activeMenu !== null;
}
