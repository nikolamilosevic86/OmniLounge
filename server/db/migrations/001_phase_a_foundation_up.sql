CREATE TABLE IF NOT EXISTS rooms (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    host_id VARCHAR(64) NOT NULL,
    access VARCHAR(10) NOT NULL DEFAULT 'public',
    topic_tags TEXT[] NOT NULL DEFAULT '{}',
    max_users INTEGER NOT NULL DEFAULT 30,
    state VARCHAR(12) NOT NULL DEFAULT 'draft',
    spawn_tile_x INTEGER NOT NULL DEFAULT 0,
    spawn_tile_y INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    CONSTRAINT chk_rooms_access CHECK (access IN ('public', 'invite')),
    CONSTRAINT chk_rooms_state CHECK (state IN ('draft', 'published', 'archived')),
    CONSTRAINT chk_rooms_max_users CHECK (max_users > 0)
);

CREATE TABLE IF NOT EXISTS room_tiles (
    id BIGSERIAL PRIMARY KEY,
    room_id VARCHAR(64) NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    tile_x INTEGER NOT NULL,
    tile_y INTEGER NOT NULL,
    label VARCHAR(80),
    purpose_tag VARCHAR(30),
    background_style VARCHAR(40),
    ambiance_style VARCHAR(40),
    is_spawn BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_room_tiles_coordinate UNIQUE (room_id, tile_x, tile_y)
);

CREATE TABLE IF NOT EXISTS room_objects (
    id VARCHAR(64) PRIMARY KEY,
    room_id VARCHAR(64) NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    tile_x INTEGER NOT NULL,
    tile_y INTEGER NOT NULL,
    object_type VARCHAR(40) NOT NULL,
    x DOUBLE PRECISION NOT NULL,
    y DOUBLE PRECISION NOT NULL,
    width DOUBLE PRECISION NOT NULL,
    height DOUBLE PRECISION NOT NULL,
    rotation DOUBLE PRECISION NOT NULL DEFAULT 0,
    z_index INTEGER NOT NULL DEFAULT 0,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    interaction_radius DOUBLE PRECISION NOT NULL DEFAULT 20,
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_room_objects_size CHECK (width > 0 AND height > 0),
    CONSTRAINT chk_room_objects_interaction_radius CHECK (interaction_radius > 0)
);

CREATE TABLE IF NOT EXISTS content_resources (
    id VARCHAR(64) PRIMARY KEY,
    room_id VARCHAR(64) NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    object_id VARCHAR(64) REFERENCES room_objects(id) ON DELETE SET NULL,
    resource_type VARCHAR(40) NOT NULL,
    content_type VARCHAR(20) NOT NULL,
    title VARCHAR(120) NOT NULL,
    author VARCHAR(120),
    summary TEXT,
    body_markdown TEXT,
    external_url TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_content_resources_type CHECK (content_type IN ('inline', 'markdown', 'external', 'video', 'audio'))
);

CREATE TABLE IF NOT EXISTS story_nodes (
    id VARCHAR(64) PRIMARY KEY,
    room_id VARCHAR(64) NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    character_id VARCHAR(64) NOT NULL,
    node_key VARCHAR(64) NOT NULL,
    character_line TEXT NOT NULL,
    user_choices_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    next_routes_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    completion_flag VARCHAR(64),
    knowledge_check_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_story_nodes_room_key UNIQUE (room_id, node_key)
);

CREATE TABLE IF NOT EXISTS room_role_mappings (
    id BIGSERIAL PRIMARY KEY,
    room_id VARCHAR(64) NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL,
    role VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_room_role_mappings_role CHECK (role IN ('owner', 'editor', 'moderator', 'viewer')),
    CONSTRAINT uq_room_role_mappings UNIQUE (room_id, user_id, role)
);

CREATE TABLE IF NOT EXISTS room_versions (
    id BIGSERIAL PRIMARY KEY,
    room_id VARCHAR(64) NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    snapshot_json JSONB NOT NULL,
    change_notes TEXT,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_room_versions UNIQUE (room_id, version_number)
);

CREATE TABLE IF NOT EXISTS room_publish_snapshots (
    id BIGSERIAL PRIMARY KEY,
    room_id VARCHAR(64) NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    version_id BIGINT NOT NULL REFERENCES room_versions(id) ON DELETE CASCADE,
    published_by VARCHAR(64) NOT NULL,
    published_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS room_admin_secrets (
    id BIGSERIAL PRIMARY KEY,
    room_id VARCHAR(64) NOT NULL UNIQUE REFERENCES rooms(id) ON DELETE CASCADE,
    provider VARCHAR(30) NOT NULL,
    api_base_url TEXT,
    api_key_encrypted TEXT NOT NULL,
    key_hint VARCHAR(16),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_room_tiles_room ON room_tiles(room_id);
CREATE INDEX IF NOT EXISTS idx_room_objects_room_tile ON room_objects(room_id, tile_x, tile_y);
CREATE INDEX IF NOT EXISTS idx_content_resources_room ON content_resources(room_id);
CREATE INDEX IF NOT EXISTS idx_story_nodes_room_character ON story_nodes(room_id, character_id);
CREATE INDEX IF NOT EXISTS idx_room_versions_room ON room_versions(room_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_room_publish_room_active ON room_publish_snapshots(room_id, is_active);
