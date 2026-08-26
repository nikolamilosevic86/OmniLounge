"""Phase F: Bookshelf learning system domain logic.

Pure, in-memory library of books attached to bookshelf-type room objects,
plus per-user reading progress tracking and "resume reading" selection.
Kept independent of persistence/network code so it is independently unit
testable, mirroring the pattern used by `room_builder.py` and
`room_object_catalog.py`.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class BookModel(BaseModel):
    book_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    content_body: str = Field(min_length=1)
    author: str | None = None
    summary: str | None = None
    reading_level: str | None = None
    content_type: Literal["inline", "markdown"] = "inline"
    est_read_minutes: int | None = Field(default=None, gt=0)
    cover_url: str | None = None


class BookshelfLibrary:
    """In-memory per-bookshelf-object book collections and per-user
    reading progress."""

    def __init__(self) -> None:
        self._books: dict[str, dict[str, dict[str, Any]]] = {}
        self._progress: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add_book(
        self,
        object_id: str,
        book_id: str,
        title: str,
        content_body: str,
        author: str | None = None,
        summary: str | None = None,
        reading_level: str | None = None,
        content_type: str = "inline",
        est_read_minutes: int | None = None,
        cover_url: str | None = None,
    ) -> dict[str, Any]:
        shelf = self._books.setdefault(object_id, {})
        if book_id in shelf:
            raise ValueError(f"book id already exists on this shelf: {book_id}")

        validated = BookModel(
            book_id=book_id,
            title=title,
            content_body=content_body,
            author=author,
            summary=summary,
            reading_level=reading_level,
            content_type=content_type,
            est_read_minutes=est_read_minutes,
            cover_url=cover_url,
        )
        record = {
            "bookId": validated.book_id,
            "title": validated.title,
            "author": validated.author,
            "summary": validated.summary,
            "readingLevel": validated.reading_level,
            "contentType": validated.content_type,
            "contentBody": validated.content_body,
            "estReadMinutes": validated.est_read_minutes,
            "coverUrl": validated.cover_url,
        }
        shelf[book_id] = record
        return dict(record)

    def list_books(self, object_id: str) -> list[dict[str, Any]]:
        return [dict(b) for b in self._books.get(object_id, {}).values()]

    def get_book(self, object_id: str, book_id: str) -> dict[str, Any] | None:
        record = self._books.get(object_id, {}).get(book_id)
        return dict(record) if record else None

    def remove_book(self, object_id: str, book_id: str) -> bool:
        shelf = self._books.get(object_id, {})
        if book_id not in shelf:
            return False
        del shelf[book_id]
        return True

    def save_progress(
        self, object_id: str, book_id: str, user_id: str, progress: float, now_ms: float
    ) -> dict[str, Any]:
        if self.get_book(object_id, book_id) is None:
            raise KeyError(f"unknown book: {book_id}")
        if progress < 0 or progress > 1:
            raise ValueError("progress must be between 0 and 1")
        record = {"progress": progress, "updatedAtMs": now_ms}
        self._progress[(object_id, book_id, user_id)] = record
        return dict(record)

    def get_progress(self, object_id: str, book_id: str, user_id: str) -> dict[str, Any] | None:
        record = self._progress.get((object_id, book_id, user_id))
        return dict(record) if record else None

    def get_resume_book(self, object_id: str, user_id: str) -> dict[str, Any] | None:
        candidates = [
            (key[1], record)
            for key, record in self._progress.items()
            if key[0] == object_id and key[2] == user_id and record["progress"] < 1.0
        ]
        if not candidates:
            return None
        book_id, record = max(candidates, key=lambda item: item[1]["updatedAtMs"])
        return {
            "book": self.get_book(object_id, book_id),
            "progress": record["progress"],
            "updatedAtMs": record["updatedAtMs"],
        }
