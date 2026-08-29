/**
 * Single-level undo (design doc feature_designs/build_mode_ui_redesign_feature_design.md
 * section 8.6, Decision D5). Before emitting a mutating builder-object event,
 * the caller captures the object's prior value with `captureUndoableAction`;
 * pressing Ctrl+Z re-emits the inverse via `buildUndoEmission`. Only a single
 * action is cached at a time (no multi-level undo stack), matching D5.
 */

const PRIOR_FIELDS = {
  move: ['x', 'y'],
  resize: ['width', 'height'],
  rotate: ['rotation'],
  style: ['color', 'material'],
};

/** Builds a cache-able undo record for `type`, snapshotting the relevant fields off `obj`. */
export function captureUndoableAction(type, obj) {
  if (type === 'delete') {
    return { type, objectId: obj.objectId, prior: obj };
  }
  const fields = PRIOR_FIELDS[type];
  if (!fields) return null;
  const prior = {};
  for (const field of fields) prior[field] = obj[field];
  return { type, objectId: obj.objectId, prior };
}

/** Builds the {event, payload} to re-emit in order to undo a cached action, or null if there is none. */
export function buildUndoEmission(action) {
  if (!action) return null;
  switch (action.type) {
    case 'move':
      return { event: 'room:object:move', payload: { objectId: action.objectId, ...action.prior } };
    case 'resize':
      return { event: 'room:object:resize', payload: { objectId: action.objectId, ...action.prior } };
    case 'rotate':
      return { event: 'room:object:rotate', payload: { objectId: action.objectId, ...action.prior } };
    case 'style':
      return { event: 'room:object:style', payload: { objectId: action.objectId, ...action.prior } };
    case 'delete':
      return { event: 'room:object:create', payload: { ...action.prior, objectId: action.objectId } };
    default:
      return null;
  }
}
