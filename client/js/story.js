export const CHARACTER_ROLES = ['guide', 'quiz_master', 'narrator', 'historical_persona', 'mentor'];

export function isValidCharacterRole(role) {
  return CHARACTER_ROLES.includes(role);
}

export function formatModeLabel(mode) {
  return mode === 'generative' ? 'Generative Mode' : 'Predefined Mode';
}

export function resolveCharacterMode(character) {
  return character?.generativeEnabled ? 'generative' : 'predefined';
}

export function parseChoicesInput(input) {
  if (!input) return [];
  return input
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      const [text, nextNodeId] = line.split('|').map((part) => part.trim());
      return { text, nextNodeId: nextNodeId || null };
    });
}
