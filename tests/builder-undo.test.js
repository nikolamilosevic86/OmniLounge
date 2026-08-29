import { describe, it, expect } from 'vitest';
import {
  captureUndoableAction,
  buildUndoEmission,
} from '../src/builder-undo.js';

describe('captureUndoableAction (design doc build_mode_ui_redesign_feature_design.md section 8.6)', () => {
  it('captures the prior x/y before a move', () => {
    const action = captureUndoableAction('move', { objectId: 'o1', x: 10, y: 20, width: 40, height: 40 });
    expect(action).toEqual({ type: 'move', objectId: 'o1', prior: { x: 10, y: 20 } });
  });

  it('captures the prior width/height before a resize', () => {
    const action = captureUndoableAction('resize', { objectId: 'o1', width: 40, height: 60 });
    expect(action).toEqual({ type: 'resize', objectId: 'o1', prior: { width: 40, height: 60 } });
  });

  it('captures the prior rotation before a rotate', () => {
    const action = captureUndoableAction('rotate', { objectId: 'o1', rotation: 45 });
    expect(action).toEqual({ type: 'rotate', objectId: 'o1', prior: { rotation: 45 } });
  });

  it('captures the prior color/material before a style change', () => {
    const action = captureUndoableAction('style', { objectId: 'o1', color: 'navy', material: 'wood' });
    expect(action).toEqual({ type: 'style', objectId: 'o1', prior: { color: 'navy', material: 'wood' } });
  });

  it('captures the entire object record before a delete', () => {
    const obj = { objectId: 'o1', objectType: 'chair', x: 1, y: 2, width: 3, height: 4, rotation: 0, color: 'navy', material: 'wood' };
    const action = captureUndoableAction('delete', obj);
    expect(action).toEqual({ type: 'delete', objectId: 'o1', prior: obj });
  });

  it('returns null for an unknown action type', () => {
    expect(captureUndoableAction('unknown', { objectId: 'o1' })).toBeNull();
  });
});

describe('buildUndoEmission', () => {
  it('returns null when there is no cached action', () => {
    expect(buildUndoEmission(null)).toBeNull();
  });

  it('builds an inverse room:object:move emission', () => {
    const action = { type: 'move', objectId: 'o1', prior: { x: 10, y: 20 } };
    expect(buildUndoEmission(action)).toEqual({
      event: 'room:object:move',
      payload: { objectId: 'o1', x: 10, y: 20 },
    });
  });

  it('builds an inverse room:object:resize emission', () => {
    const action = { type: 'resize', objectId: 'o1', prior: { width: 40, height: 60 } };
    expect(buildUndoEmission(action)).toEqual({
      event: 'room:object:resize',
      payload: { objectId: 'o1', width: 40, height: 60 },
    });
  });

  it('builds an inverse room:object:rotate emission', () => {
    const action = { type: 'rotate', objectId: 'o1', prior: { rotation: 45 } };
    expect(buildUndoEmission(action)).toEqual({
      event: 'room:object:rotate',
      payload: { objectId: 'o1', rotation: 45 },
    });
  });

  it('builds an inverse room:object:style emission', () => {
    const action = { type: 'style', objectId: 'o1', prior: { color: 'navy', material: 'wood' } };
    expect(buildUndoEmission(action)).toEqual({
      event: 'room:object:style',
      payload: { objectId: 'o1', color: 'navy', material: 'wood' },
    });
  });

  it('builds an inverse re-creation emission for a delete, preserving the original objectId', () => {
    const obj = { objectId: 'o1', objectType: 'chair', x: 1, y: 2, width: 3, height: 4, rotation: 0, color: 'navy', material: 'wood' };
    const action = { type: 'delete', objectId: 'o1', prior: obj };
    expect(buildUndoEmission(action)).toEqual({
      event: 'room:object:create',
      payload: { ...obj, objectId: 'o1' },
    });
  });
});
