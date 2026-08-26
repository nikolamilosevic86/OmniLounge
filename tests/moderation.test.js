import { describe, it, expect } from 'vitest';
import {
  ASSIGNABLE_ROLES,
  formatRoleLabel,
  canAssignRoles,
  canModerate,
  canManageAiSettings,
} from '../src/moderation.js';

describe('ASSIGNABLE_ROLES', () => {
  it('lists the three roles an owner can assign', () => {
    expect(ASSIGNABLE_ROLES).toEqual(['co_editor', 'moderator', 'participant']);
  });
});

describe('formatRoleLabel', () => {
  it('formats owner', () => {
    expect(formatRoleLabel('owner')).toBe('Owner');
  });

  it('formats co_editor with a space', () => {
    expect(formatRoleLabel('co_editor')).toBe('Co-Editor');
  });

  it('formats moderator', () => {
    expect(formatRoleLabel('moderator')).toBe('Moderator');
  });

  it('formats participant', () => {
    expect(formatRoleLabel('participant')).toBe('Participant');
  });

  it('falls back to the raw value for an unknown role', () => {
    expect(formatRoleLabel('mystery')).toBe('mystery');
  });
});

describe('canAssignRoles', () => {
  it('is true only for owner', () => {
    expect(canAssignRoles('owner')).toBe(true);
    expect(canAssignRoles('co_editor')).toBe(false);
    expect(canAssignRoles('moderator')).toBe(false);
    expect(canAssignRoles('participant')).toBe(false);
  });
});

describe('canModerate', () => {
  it('is true for owner and moderator only', () => {
    expect(canModerate('owner')).toBe(true);
    expect(canModerate('moderator')).toBe(true);
    expect(canModerate('co_editor')).toBe(false);
    expect(canModerate('participant')).toBe(false);
  });
});

describe('canManageAiSettings', () => {
  it('is true only for owner', () => {
    expect(canManageAiSettings('owner')).toBe(true);
    expect(canManageAiSettings('co_editor')).toBe(false);
    expect(canManageAiSettings('moderator')).toBe(false);
    expect(canManageAiSettings('participant')).toBe(false);
  });
});
