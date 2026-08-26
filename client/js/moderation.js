export const ASSIGNABLE_ROLES = ['co_editor', 'moderator', 'participant'];

const ROLE_LABELS = {
  owner: 'Owner',
  co_editor: 'Co-Editor',
  moderator: 'Moderator',
  participant: 'Participant',
};

export function formatRoleLabel(role) {
  return ROLE_LABELS[role] || role;
}

export function canAssignRoles(role) {
  return role === 'owner';
}

export function canModerate(role) {
  return role === 'owner' || role === 'moderator';
}

export function canManageAiSettings(role) {
  return role === 'owner';
}
