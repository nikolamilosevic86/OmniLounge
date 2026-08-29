"""Security regression tests for the static-file catch-all route.

Background: the production build is served by a FastAPI catch-all that took an
arbitrary client-supplied path and joined it straight onto DIST_DIR. Because
``Path("/app/dist") / "../../etc/passwd"`` happily escapes the build directory,
that route was an unauthenticated arbitrary file read -- ``GET /../../etc/passwd``
returned the real file. These tests pin the containment check.
"""
from pathlib import Path

import pytest

import server.main as main_module
from server.main import resolve_dist_file


@pytest.fixture
def dist(tmp_path, monkeypatch):
    """Point DIST_DIR at a throwaway build directory with one real asset."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<!DOCTYPE html>")
    (dist_dir / "help.html").write_text("<!DOCTYPE html>")
    nested = dist_dir / "assets"
    nested.mkdir()
    (nested / "main.js").write_text("console.log(1);")

    (tmp_path / "secret.env").write_text("DATABASE_URL=postgresql://u:p@db/x")

    monkeypatch.setattr(main_module, "DIST_DIR", dist_dir)
    return tmp_path


@pytest.mark.parametrize(
    "path",
    ["index.html", "help.html", "assets/main.js", "./help.html", "assets/../help.html"],
)
def test_serves_real_files_inside_the_build_directory(dist, path):
    resolved = resolve_dist_file(path)
    assert resolved is not None
    assert resolved.is_file()
    assert (dist / "dist").resolve() in resolved.parents


@pytest.mark.parametrize(
    "path",
    [
        "../secret.env",
        "../../secret.env",
        "../../../../etc/passwd",
        "assets/../../secret.env",
        "/etc/passwd",
        "..",
        "../",
    ],
)
def test_rejects_paths_that_escape_the_build_directory(dist, path):
    assert resolve_dist_file(path) is None


def test_rejects_directories(dist):
    assert resolve_dist_file("assets") is None


def test_rejects_missing_files(dist):
    assert resolve_dist_file("nope.html") is None


def test_rejects_symlink_pointing_outside_the_build_directory(dist):
    """Resolution collapses symlinks, so a link planted in dist cannot leak."""
    link = dist / "dist" / "escape.env"
    try:
        link.symlink_to(dist / "secret.env")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    assert resolve_dist_file("escape.env") is None
