"""Phase G: TV video / music track domain logic.

Pure, in-memory media library for `tv` and `music_player` room objects:
YouTube-backed video/track catalog entries (server-side validated so a
malicious client can never smuggle an arbitrary embed source past the
UI), plus an opt-in "watch/listen together" sync session per object.
Personal (non-synced) playback is the default and requires no session at
all — sync is purely an additive, opt-in layer.
"""

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _validate_youtube_id(value: str) -> str:
    if not _YOUTUBE_ID_RE.match(value):
        raise ValueError("youtube_video_id must be exactly 11 URL-safe characters")
    return value


class VideoModel(BaseModel):
    video_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    youtube_video_id: str
    description: str | None = None

    @field_validator("youtube_video_id")
    @classmethod
    def _check_youtube_id(cls, value: str) -> str:
        return _validate_youtube_id(value)


class TrackModel(BaseModel):
    track_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    youtube_video_id: str
    artist: str | None = None
    duration_seconds: int | None = Field(default=None, gt=0)

    @field_validator("youtube_video_id")
    @classmethod
    def _check_youtube_id(cls, value: str) -> str:
        return _validate_youtube_id(value)


class MediaLibrary:
    """In-memory per-object video/track catalogs plus opt-in sync sessions."""

    def __init__(self) -> None:
        self._videos: dict[str, dict[str, dict[str, Any]]] = {}
        self._tracks: dict[str, dict[str, dict[str, Any]]] = {}
        self._sync_sessions: dict[str, dict[str, Any]] = {}

    # ─── Videos (tv) ────────────────────────────────────────────────────

    def add_video(
        self, object_id: str, video_id: str, title: str, youtube_video_id: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        shelf = self._videos.setdefault(object_id, {})
        if video_id in shelf:
            raise ValueError(f"video id already exists on this object: {video_id}")
        validated = VideoModel(
            video_id=video_id, title=title, youtube_video_id=youtube_video_id, description=description,
        )
        record = {
            "videoId": validated.video_id,
            "title": validated.title,
            "youtubeVideoId": validated.youtube_video_id,
            "description": validated.description,
        }
        shelf[video_id] = record
        return dict(record)

    def list_videos(self, object_id: str) -> list[dict[str, Any]]:
        return [dict(v) for v in self._videos.get(object_id, {}).values()]

    def get_video(self, object_id: str, video_id: str) -> dict[str, Any] | None:
        record = self._videos.get(object_id, {}).get(video_id)
        return dict(record) if record else None

    def remove_video(self, object_id: str, video_id: str) -> bool:
        shelf = self._videos.get(object_id, {})
        if video_id not in shelf:
            return False
        del shelf[video_id]
        return True

    # ─── Tracks (music_player) ──────────────────────────────────────────

    def add_track(
        self, object_id: str, track_id: str, title: str, youtube_video_id: str,
        artist: str | None = None, duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        shelf = self._tracks.setdefault(object_id, {})
        if track_id in shelf:
            raise ValueError(f"track id already exists on this object: {track_id}")
        validated = TrackModel(
            track_id=track_id, title=title, youtube_video_id=youtube_video_id,
            artist=artist, duration_seconds=duration_seconds,
        )
        record = {
            "trackId": validated.track_id,
            "title": validated.title,
            "youtubeVideoId": validated.youtube_video_id,
            "artist": validated.artist,
            "durationSeconds": validated.duration_seconds,
        }
        shelf[track_id] = record
        return dict(record)

    def list_tracks(self, object_id: str) -> list[dict[str, Any]]:
        return [dict(t) for t in self._tracks.get(object_id, {}).values()]

    def get_track(self, object_id: str, track_id: str) -> dict[str, Any] | None:
        record = self._tracks.get(object_id, {}).get(track_id)
        return dict(record) if record else None

    def remove_track(self, object_id: str, track_id: str) -> bool:
        shelf = self._tracks.get(object_id, {})
        if track_id not in shelf:
            return False
        del shelf[track_id]
        return True

    # ─── Opt-in watch/listen-together sync sessions ────────────────────

    def start_sync_session(self, object_id: str, host_id: str, item_id: str, now_ms: float) -> dict[str, Any]:
        session = {
            "hostId": host_id,
            "itemId": item_id,
            "isPlaying": True,
            "positionSeconds": 0,
            "lastUpdateMs": now_ms,
            "participants": [host_id],
        }
        self._sync_sessions[object_id] = session
        return self._public_session(session, now_ms)

    def join_sync_session(self, object_id: str, user_id: str) -> dict[str, Any]:
        session = self._sync_sessions.get(object_id)
        if session is None:
            raise KeyError(f"no active sync session for {object_id}")
        if user_id not in session["participants"]:
            session["participants"].append(user_id)
        return self._public_session(session, session["lastUpdateMs"])

    def leave_sync_session(self, object_id: str, user_id: str) -> None:
        session = self._sync_sessions.get(object_id)
        if session is None:
            return
        if user_id == session["hostId"]:
            del self._sync_sessions[object_id]
            return
        if user_id in session["participants"]:
            session["participants"].remove(user_id)

    def update_playback(
        self, object_id: str, requester_id: str, is_playing: bool, position_seconds: float, now_ms: float,
    ) -> dict[str, Any]:
        session = self._sync_sessions.get(object_id)
        if session is None:
            raise KeyError(f"no active sync session for {object_id}")
        if requester_id != session["hostId"]:
            raise PermissionError("only the host can update sync playback")
        session["isPlaying"] = is_playing
        session["positionSeconds"] = position_seconds
        session["lastUpdateMs"] = now_ms
        return self._public_session(session, now_ms)

    def end_sync_session(self, object_id: str, requester_id: str) -> bool:
        session = self._sync_sessions.get(object_id)
        if session is None:
            return False
        if requester_id != session["hostId"]:
            raise PermissionError("only the host can end the sync session")
        del self._sync_sessions[object_id]
        return True

    def get_sync_session(self, object_id: str, now_ms: float) -> dict[str, Any] | None:
        session = self._sync_sessions.get(object_id)
        if session is None:
            return None
        return self._public_session(session, now_ms)

    def _public_session(self, session: dict[str, Any], now_ms: float) -> dict[str, Any]:
        position = session["positionSeconds"]
        if session["isPlaying"]:
            elapsed_seconds = max(0.0, (now_ms - session["lastUpdateMs"]) / 1000)
            position = session["positionSeconds"] + elapsed_seconds
        return {
            "hostId": session["hostId"],
            "itemId": session["itemId"],
            "isPlaying": session["isPlaying"],
            "positionSeconds": position,
            "participants": list(session["participants"]),
            "asOfMs": now_ms,
        }
