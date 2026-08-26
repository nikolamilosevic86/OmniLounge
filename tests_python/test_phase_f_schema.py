from pathlib import Path


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "server" / "db" / "schema.sql"


def _read_schema() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def test_phase_f_reading_progress_table_exists_in_schema():
    schema = _read_schema().lower()
    assert "create table if not exists reading_progress" in schema


def test_phase_f_reading_progress_has_required_columns_and_constraints():
    schema = _read_schema().lower()
    assert "resource_id" in schema
    assert "reading_progress" in schema
    assert "chk_reading_progress_range" in schema
    assert "uq_reading_progress" in schema
