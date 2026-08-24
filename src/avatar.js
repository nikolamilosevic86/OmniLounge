export const AVATAR_OPTIONS = {
  skinColors: ['#FFDBAC', '#F1C27D', '#E0AC69', '#C68642', '#8D5524', '#5C3D2E'],
  hair: ['short', 'long', 'curly', 'mohawk', 'bald', 'ponytail'],
  beards: ['none', 'stubble', 'goatee', 'full'],
  glasses: ['none', 'round', 'square', 'sunglasses'],
  clothes: ['tshirt', 'hoodie', 'suit', 'dress', 'jacket'],
  accessories: ['none', 'hat', 'backpack', 'scarf', 'headphones'],
};

export function createDefaultAvatar(username) {
  return createAvatar({ username });
}

export function createAvatar(options = {}) {
  return {
    username: options.username ?? 'Guest',
    skinColor: options.skinColor ?? AVATAR_OPTIONS.skinColors[0],
    hair: options.hair ?? AVATAR_OPTIONS.hair[0],
    beard: options.beard ?? 'none',
    glasses: options.glasses ?? 'none',
    clothes: options.clothes ?? AVATAR_OPTIONS.clothes[0],
    accessory: options.accessory ?? 'none',
  };
}

export function validateAvatar(avatar) {
  if (!avatar.username || avatar.username.trim().length === 0) {
    return false;
  }
  if (!AVATAR_OPTIONS.skinColors.includes(avatar.skinColor)) {
    return false;
  }
  if (!AVATAR_OPTIONS.hair.includes(avatar.hair)) {
    return false;
  }
  if (!AVATAR_OPTIONS.beards.includes(avatar.beard)) {
    return false;
  }
  if (!AVATAR_OPTIONS.glasses.includes(avatar.glasses)) {
    return false;
  }
  if (!AVATAR_OPTIONS.clothes.includes(avatar.clothes)) {
    return false;
  }
  if (!AVATAR_OPTIONS.accessories.includes(avatar.accessory)) {
    return false;
  }
  return true;
}

export function serializeAvatar(avatar) {
  return JSON.stringify(avatar);
}

export function deserializeAvatar(json) {
  return JSON.parse(json);
}
