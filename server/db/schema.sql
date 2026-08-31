CREATE TABLE IF NOT EXISTS avatars (
    id SERIAL PRIMARY KEY,
    username VARCHAR(16) UNIQUE NOT NULL,
    skin_color VARCHAR(7) NOT NULL,
    gender VARCHAR(20) NOT NULL DEFAULT 'neutral',
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
    reading_level VARCHAR(30),
    est_read_minutes INTEGER,
    cover_url TEXT,
    body_markdown TEXT,
    external_url TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_content_resources_type CHECK (content_type IN ('inline', 'markdown', 'external', 'video', 'audio')),
    CONSTRAINT chk_content_resources_est_read_minutes CHECK (est_read_minutes IS NULL OR est_read_minutes > 0)
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

CREATE TABLE IF NOT EXISTS reading_progress (
    id BIGSERIAL PRIMARY KEY,
    resource_id VARCHAR(64) NOT NULL REFERENCES content_resources(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL,
    progress DOUBLE PRECISION NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_reading_progress UNIQUE (resource_id, user_id),
    CONSTRAINT chk_reading_progress_range CHECK (progress >= 0 AND progress <= 1)
);

CREATE INDEX IF NOT EXISTS idx_room_tiles_room ON room_tiles(room_id);
CREATE INDEX IF NOT EXISTS idx_room_objects_room_tile ON room_objects(room_id, tile_x, tile_y);
CREATE INDEX IF NOT EXISTS idx_content_resources_room ON content_resources(room_id);
CREATE INDEX IF NOT EXISTS idx_story_nodes_room_character ON story_nodes(room_id, character_id);
CREATE INDEX IF NOT EXISTS idx_room_versions_room ON room_versions(room_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_room_publish_room_active ON room_publish_snapshots(room_id, is_active);
CREATE INDEX IF NOT EXISTS idx_reading_progress_user ON reading_progress(user_id);

-- ── Authentication (feature_designs/authentication_registration_feature_design.md) ──
-- IDs are app-generated VARCHAR(36) uuid4 strings rather than native UUID
-- columns with gen_random_uuid(), matching every other table in this schema
-- (rooms.id, messages.id, etc.) and avoiding a dependency on the pgcrypto
-- extension being enabled on the target Postgres instance.

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255),

    entra_id_sub VARCHAR(255) UNIQUE,
    oauth2_sub VARCHAR(255),
    oauth2_provider VARCHAR(50),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    is_moderator BOOLEAN NOT NULL DEFAULT FALSE,
    role VARCHAR(50) NOT NULL DEFAULT 'learner',

    bio TEXT,
    avatar_customization JSONB,
    preferred_topics TEXT[],

    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    email_verified_at TIMESTAMPTZ,

    password_changed_at TIMESTAMPTZ,
    requires_password_change BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at TIMESTAMPTZ,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(36) REFERENCES users(id),
    deleted_at TIMESTAMPTZ,

    CONSTRAINT chk_users_role CHECK (role IN ('learner', 'educator', 'moderator', 'admin'))
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_users_entra_id_sub ON users(entra_id_sub) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

CREATE TABLE IF NOT EXISTS user_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    access_token_hash VARCHAR(64) NOT NULL UNIQUE,
    refresh_token_hash VARCHAR(64) UNIQUE,
    access_token_expires_at TIMESTAMPTZ NOT NULL,
    refresh_token_expires_at TIMESTAMPTZ,

    device_name VARCHAR(255),
    user_agent VARCHAR(500),
    ip_address VARCHAR(45),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    revoked_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_refresh_token_hash ON user_sessions(refresh_token_hash);

CREATE TABLE IF NOT EXISTS oauth2_identities (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    provider_user_id VARCHAR(255) NOT NULL,
    profile_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_synced_at TIMESTAMPTZ,
    CONSTRAINT uq_oauth2_identities UNIQUE (provider, provider_user_id)
);

CREATE INDEX IF NOT EXISTS idx_oauth2_identities_user_id ON oauth2_identities(user_id);

-- design doc Phase 7 T7.3: "password history (don't allow recent passwords)".
CREATE TABLE IF NOT EXISTS password_history (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_password_history_user_id ON password_history(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_verification_tokens_user_id ON email_verification_tokens(user_id);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON password_reset_tokens(user_id);

CREATE TABLE IF NOT EXISTS auth_audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    event_type VARCHAR(100) NOT NULL,
    event_status VARCHAR(50) NOT NULL,
    event_message TEXT,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_auth_audit_log_status CHECK (event_status IN ('success', 'failure'))
);

CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON auth_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON auth_audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON auth_audit_log(created_at DESC);

