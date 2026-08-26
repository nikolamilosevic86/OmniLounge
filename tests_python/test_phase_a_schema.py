from pathlib import Path


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "server" / "db" / "schema.sql"


def _read_schema() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def test_phase_a_core_tables_exist_in_schema():
    schema = _read_schema().lower()
    required_tables = [
        "create table if not exists rooms",
        "create table if not exists room_tiles",
        "create table if not exists room_objects",
        "create table if not exists content_resources",
        "create table if not exists story_nodes",
        "create table if not exists room_role_mappings",
    ]
    for table_sql in required_tables:
        assert table_sql in schema


def test_phase_a_versioning_and_secret_tables_exist_in_schema():
    schema = _read_schema().lower()
    required_tables = [
        "create table if not exists room_versions",
        "create table if not exists room_publish_snapshots",
        "create table if not exists room_admin_secrets",
    ]
    for table_sql in required_tables:
        assert table_sql in schema


def test_phase_a_schema_has_mvp_coordinate_and_object_columns():
    schema = _read_schema().lower()
    assert "tile_x" in schema
    assert "tile_y" in schema
    assert "x" in schema
    assert "y" in schema
    assert "z_index" in schema
    assert "interaction_radius" in schema
