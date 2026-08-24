CREATE TABLE IF NOT EXISTS avatars (
    id SERIAL PRIMARY KEY,
    username VARCHAR(16) UNIQUE NOT NULL,
    skin_color VARCHAR(7) NOT NULL,
    hair VARCHAR(20) NOT NULL,
    beard VARCHAR(20) NOT NULL DEFAULT 'none',
    glasses VARCHAR(20) NOT NULL DEFAULT 'none',
    clothes VARCHAR(20) NOT NULL,
    accessory VARCHAR(20) NOT NULL DEFAULT 'none',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id VARCHAR(64) PRIMARY KEY,
    room_id VARCHAR(50) NOT NULL DEFAULT 'lobby',
    sender_id VARCHAR(64) NOT NULL,
    sender_name VARCHAR(16) NOT NULL,
    text TEXT NOT NULL,
    type VARCHAR(10) NOT NULL DEFAULT 'public',
    recipient_id VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    timestamp_ms BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id, timestamp_ms DESC);
CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id) WHERE recipient_id IS NOT NULL;
