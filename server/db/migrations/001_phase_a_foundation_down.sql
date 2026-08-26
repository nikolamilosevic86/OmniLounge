DROP INDEX IF EXISTS idx_room_publish_room_active;
DROP INDEX IF EXISTS idx_room_versions_room;
DROP INDEX IF EXISTS idx_story_nodes_room_character;
DROP INDEX IF EXISTS idx_content_resources_room;
DROP INDEX IF EXISTS idx_room_objects_room_tile;
DROP INDEX IF EXISTS idx_room_tiles_room;

DROP TABLE IF EXISTS room_admin_secrets;
DROP TABLE IF EXISTS room_publish_snapshots;
DROP TABLE IF EXISTS room_versions;
DROP TABLE IF EXISTS room_role_mappings;
DROP TABLE IF EXISTS story_nodes;
DROP TABLE IF EXISTS content_resources;
DROP TABLE IF EXISTS room_objects;
DROP TABLE IF EXISTS room_tiles;
DROP TABLE IF EXISTS rooms;
