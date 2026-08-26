"""Tests for Phase G media domain logic: TV video / music track models with
YouTube ID validation, MediaLibrary CRUD, and opt-in watch/listen-together
sync sessions."""

import pytest
from pydantic import ValidationError

from server.game.media import MediaLibrary


class TestAddVideo:
    def setup_method(self):
        self.library = MediaLibrary()

    def test_add_video_returns_record_with_all_fields(self):
        video = self.library.add_video(
            "tv-1", "video-1", title="Intro to Fractions", youtube_video_id="dQw4w9WgXcQ",
            description="A gentle lesson.",
        )
        assert video["videoId"] == "video-1"
        assert video["title"] == "Intro to Fractions"
        assert video["youtubeVideoId"] == "dQw4w9WgXcQ"
        assert video["description"] == "A gentle lesson."

    def test_add_video_rejects_invalid_youtube_id_length(self):
        with pytest.raises(ValidationError):
            self.library.add_video("tv-1", "video-1", title="T", youtube_video_id="short")

    def test_add_video_rejects_youtube_id_with_invalid_characters(self):
        with pytest.raises(ValidationError):
            self.library.add_video("tv-1", "video-1", title="T", youtube_video_id="abc def!!!!")

    def test_add_video_rejects_empty_title(self):
        with pytest.raises(ValidationError):
            self.library.add_video("tv-1", "video-1", title="", youtube_video_id="dQw4w9WgXcQ")

    def test_add_video_rejects_duplicate_id_on_same_object(self):
        self.library.add_video("tv-1", "video-1", title="T", youtube_video_id="dQw4w9WgXcQ")
        with pytest.raises(ValueError):
            self.library.add_video("tv-1", "video-1", title="T2", youtube_video_id="dQw4w9WgXcQ")


class TestListAndRemoveVideo:
    def setup_method(self):
        self.library = MediaLibrary()
        self.library.add_video("tv-1", "video-1", title="First", youtube_video_id="dQw4w9WgXcQ")

    def test_list_videos_returns_all(self):
        videos = self.library.list_videos("tv-1")
        assert [v["videoId"] for v in videos] == ["video-1"]

    def test_list_videos_empty_for_unknown_object(self):
        assert self.library.list_videos("unknown") == []

    def test_get_video_returns_none_for_unknown(self):
        assert self.library.get_video("tv-1", "unknown") is None

    def test_remove_video_returns_true_and_removes(self):
        assert self.library.remove_video("tv-1", "video-1") is True
        assert self.library.get_video("tv-1", "video-1") is None

    def test_remove_unknown_video_returns_false(self):
        assert self.library.remove_video("tv-1", "unknown") is False


class TestAddTrack:
    def setup_method(self):
        self.library = MediaLibrary()

    def test_add_track_returns_record_with_all_fields(self):
        track = self.library.add_track(
            "player-1", "track-1", title="Counting Song", youtube_video_id="dQw4w9WgXcQ",
            artist="Miss Rachel", duration_seconds=180,
        )
        assert track["trackId"] == "track-1"
        assert track["title"] == "Counting Song"
        assert track["artist"] == "Miss Rachel"
        assert track["youtubeVideoId"] == "dQw4w9WgXcQ"
        assert track["durationSeconds"] == 180

    def test_add_track_rejects_non_positive_duration(self):
        with pytest.raises(ValidationError):
            self.library.add_track("player-1", "track-1", title="T", youtube_video_id="dQw4w9WgXcQ", duration_seconds=0)

    def test_add_track_rejects_invalid_youtube_id(self):
        with pytest.raises(ValidationError):
            self.library.add_track("player-1", "track-1", title="T", youtube_video_id="nope")

    def test_add_track_rejects_duplicate_id(self):
        self.library.add_track("player-1", "track-1", title="T", youtube_video_id="dQw4w9WgXcQ")
        with pytest.raises(ValueError):
            self.library.add_track("player-1", "track-1", title="T2", youtube_video_id="dQw4w9WgXcQ")


class TestListAndRemoveTrack:
    def setup_method(self):
        self.library = MediaLibrary()
        self.library.add_track("player-1", "track-1", title="First", youtube_video_id="dQw4w9WgXcQ")

    def test_list_tracks_returns_all(self):
        assert [t["trackId"] for t in self.library.list_tracks("player-1")] == ["track-1"]

    def test_get_track_returns_none_for_unknown(self):
        assert self.library.get_track("player-1", "unknown") is None

    def test_remove_track_returns_true_and_removes(self):
        assert self.library.remove_track("player-1", "track-1") is True
        assert self.library.get_track("player-1", "track-1") is None

    def test_remove_unknown_track_returns_false(self):
        assert self.library.remove_track("player-1", "unknown") is False


class TestSyncSession:
    def setup_method(self):
        self.library = MediaLibrary()

    def test_get_sync_session_returns_none_when_no_session(self):
        assert self.library.get_sync_session("tv-1", now_ms=1000) is None

    def test_start_sync_session_creates_active_session_with_host_as_participant(self):
        session = self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        assert session["hostId"] == "p1"
        assert session["itemId"] == "video-1"
        assert session["isPlaying"] is True
        assert session["positionSeconds"] == 0
        assert session["participants"] == ["p1"]

    def test_join_sync_session_adds_participant(self):
        self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        session = self.library.join_sync_session("tv-1", user_id="p2")
        assert set(session["participants"]) == {"p1", "p2"}

    def test_join_sync_session_raises_when_no_active_session(self):
        with pytest.raises(KeyError):
            self.library.join_sync_session("tv-1", user_id="p2")

    def test_join_sync_session_is_idempotent(self):
        self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        self.library.join_sync_session("tv-1", user_id="p2")
        session = self.library.join_sync_session("tv-1", user_id="p2")
        assert session["participants"].count("p2") == 1

    def test_leave_sync_session_removes_participant(self):
        self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        self.library.join_sync_session("tv-1", user_id="p2")
        self.library.leave_sync_session("tv-1", user_id="p2")
        session = self.library.get_sync_session("tv-1", now_ms=1000)
        assert "p2" not in session["participants"]

    def test_leave_sync_session_by_host_ends_the_session(self):
        self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        self.library.leave_sync_session("tv-1", user_id="p1")
        assert self.library.get_sync_session("tv-1", now_ms=1000) is None

    def test_update_playback_requires_host(self):
        self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        with pytest.raises(PermissionError):
            self.library.update_playback("tv-1", requester_id="p2", is_playing=False, position_seconds=30, now_ms=2000)

    def test_update_playback_by_host_updates_state(self):
        self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        session = self.library.update_playback(
            "tv-1", requester_id="p1", is_playing=False, position_seconds=42, now_ms=2000,
        )
        assert session["isPlaying"] is False
        assert session["positionSeconds"] == 42

    def test_get_sync_session_computes_live_position_while_playing(self):
        self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        session = self.library.get_sync_session("tv-1", now_ms=6000)
        assert session["positionSeconds"] == 5.0

    def test_get_sync_session_position_freezes_when_paused(self):
        self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        self.library.update_playback("tv-1", requester_id="p1", is_playing=False, position_seconds=10, now_ms=2000)
        session = self.library.get_sync_session("tv-1", now_ms=10000)
        assert session["positionSeconds"] == 10

    def test_end_sync_session_requires_host(self):
        self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        with pytest.raises(PermissionError):
            self.library.end_sync_session("tv-1", requester_id="p2")

    def test_end_sync_session_by_host_clears_it(self):
        self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        self.library.end_sync_session("tv-1", requester_id="p1")
        assert self.library.get_sync_session("tv-1", now_ms=1000) is None

    def test_starting_new_session_replaces_previous(self):
        self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        self.library.start_sync_session("tv-1", host_id="p2", item_id="video-2", now_ms=2000)
        session = self.library.get_sync_session("tv-1", now_ms=2000)
        assert session["hostId"] == "p2"
        assert session["itemId"] == "video-2"

    def test_sync_sessions_are_scoped_per_object(self):
        self.library.start_sync_session("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        assert self.library.get_sync_session("tv-2", now_ms=1000) is None
