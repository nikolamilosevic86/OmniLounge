export function normalizeRooms(rooms = []) {
  return [...rooms]
    .map((room) => ({
      ...room,
      topicTags: Array.isArray(room.topicTags) ? room.topicTags : [],
      access: room.access || 'public',
      activeUsers: Number.isFinite(room.activeUsers) ? room.activeUsers : 0,
      maxUsers: Number.isFinite(room.maxUsers) ? room.maxUsers : 30,
      createdAtMs: Number.isFinite(room.createdAtMs) ? room.createdAtMs : 0,
    }))
    .sort((a, b) => {
      if (b.activeUsers !== a.activeUsers) return b.activeUsers - a.activeUsers;
      return b.createdAtMs - a.createdAtMs;
    });
}

export function buildRoomMetaLine(room) {
  const access = room.access === 'invite' ? 'Invite' : 'Public';
  const users = `${room.activeUsers}/${room.maxUsers} online`;
  const tags = room.topicTags.length > 0 ? room.topicTags.join(', ') : 'no tags';
  return `${access} · ${users} · ${tags}`;
}

export function canJoinRoom(room) {
  return (room.activeUsers ?? 0) < (room.maxUsers ?? 0);
}

export function normalizeRoomFilters(rawFilters = {}) {
  const topic = (rawFilters.topic || '').trim().toLowerCase();
  const access = rawFilters.access === 'public' || rawFilters.access === 'invite'
    ? rawFilters.access
    : 'all';
  const sort = rawFilters.sort === 'active' ? 'active' : 'newest';

  return {
    topic,
    access,
    sort,
  };
}
