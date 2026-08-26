"""Tests for Phase F bookshelf domain logic: Book validation, BookshelfLibrary
CRUD, per-user reading progress, and resume-book selection."""

import pytest
from pydantic import ValidationError

from server.game.bookshelf import BookshelfLibrary


class TestAddBook:
    def setup_method(self):
        self.library = BookshelfLibrary()

    def test_add_book_returns_record_with_all_fields(self):
        book = self.library.add_book(
            "shelf-1", "book-1", title="Intro to Physics", content_body="Once upon a time...",
            author="Jane Doe", summary="A gentle intro.", reading_level="beginner",
            content_type="markdown", est_read_minutes=12, cover_url="https://example.com/cover.png",
        )
        assert book["bookId"] == "book-1"
        assert book["title"] == "Intro to Physics"
        assert book["author"] == "Jane Doe"
        assert book["summary"] == "A gentle intro."
        assert book["readingLevel"] == "beginner"
        assert book["contentType"] == "markdown"
        assert book["contentBody"] == "Once upon a time..."
        assert book["estReadMinutes"] == 12
        assert book["coverUrl"] == "https://example.com/cover.png"

    def test_add_book_defaults_content_type_to_inline(self):
        book = self.library.add_book("shelf-1", "book-1", title="T", content_body="body")
        assert book["contentType"] == "inline"

    def test_add_book_rejects_empty_content_body(self):
        with pytest.raises(ValidationError):
            self.library.add_book("shelf-1", "book-1", title="T", content_body="")

    def test_add_book_rejects_unknown_content_type(self):
        with pytest.raises(ValidationError):
            self.library.add_book("shelf-1", "book-1", title="T", content_body="body", content_type="external")

    def test_add_book_rejects_non_positive_est_read_minutes(self):
        with pytest.raises(ValidationError):
            self.library.add_book("shelf-1", "book-1", title="T", content_body="body", est_read_minutes=0)

    def test_add_book_rejects_duplicate_book_id_on_same_shelf(self):
        self.library.add_book("shelf-1", "book-1", title="T", content_body="body")
        with pytest.raises(ValueError):
            self.library.add_book("shelf-1", "book-1", title="T2", content_body="body2")

    def test_add_book_allows_same_book_id_on_different_shelves(self):
        self.library.add_book("shelf-1", "book-1", title="T", content_body="body")
        book = self.library.add_book("shelf-2", "book-1", title="T2", content_body="body2")
        assert book["bookId"] == "book-1"


class TestListAndGetBooks:
    def setup_method(self):
        self.library = BookshelfLibrary()
        self.library.add_book("shelf-1", "book-1", title="First", content_body="a")
        self.library.add_book("shelf-1", "book-2", title="Second", content_body="b")

    def test_list_books_returns_all_books_on_shelf(self):
        books = self.library.list_books("shelf-1")
        assert {b["bookId"] for b in books} == {"book-1", "book-2"}

    def test_list_books_returns_empty_for_unknown_shelf(self):
        assert self.library.list_books("unknown-shelf") == []

    def test_get_book_returns_matching_record(self):
        book = self.library.get_book("shelf-1", "book-2")
        assert book["title"] == "Second"

    def test_get_book_returns_none_for_unknown_book(self):
        assert self.library.get_book("shelf-1", "unknown") is None

    def test_get_book_returns_none_for_unknown_shelf(self):
        assert self.library.get_book("unknown-shelf", "book-1") is None


class TestRemoveBook:
    def setup_method(self):
        self.library = BookshelfLibrary()
        self.library.add_book("shelf-1", "book-1", title="First", content_body="a")

    def test_remove_book_returns_true_and_removes_it(self):
        assert self.library.remove_book("shelf-1", "book-1") is True
        assert self.library.get_book("shelf-1", "book-1") is None

    def test_remove_unknown_book_returns_false(self):
        assert self.library.remove_book("shelf-1", "unknown") is False


class TestReadingProgress:
    def setup_method(self):
        self.library = BookshelfLibrary()
        self.library.add_book("shelf-1", "book-1", title="First", content_body="a")
        self.library.add_book("shelf-1", "book-2", title="Second", content_body="b")

    def test_save_progress_then_get_progress_roundtrips(self):
        self.library.save_progress("shelf-1", "book-1", "user-1", 0.4, now_ms=1000)
        progress = self.library.get_progress("shelf-1", "book-1", "user-1")
        assert progress["progress"] == 0.4
        assert progress["updatedAtMs"] == 1000

    def test_get_progress_returns_none_when_never_saved(self):
        assert self.library.get_progress("shelf-1", "book-1", "user-1") is None

    def test_save_progress_rejects_out_of_range_values(self):
        with pytest.raises(ValueError):
            self.library.save_progress("shelf-1", "book-1", "user-1", 1.5, now_ms=1000)
        with pytest.raises(ValueError):
            self.library.save_progress("shelf-1", "book-1", "user-1", -0.1, now_ms=1000)

    def test_save_progress_rejects_unknown_book(self):
        with pytest.raises(KeyError):
            self.library.save_progress("shelf-1", "unknown", "user-1", 0.5, now_ms=1000)

    def test_progress_is_scoped_per_user(self):
        self.library.save_progress("shelf-1", "book-1", "user-1", 0.4, now_ms=1000)
        assert self.library.get_progress("shelf-1", "book-1", "user-2") is None

    def test_save_progress_overwrites_previous_value(self):
        self.library.save_progress("shelf-1", "book-1", "user-1", 0.2, now_ms=1000)
        self.library.save_progress("shelf-1", "book-1", "user-1", 0.9, now_ms=2000)
        progress = self.library.get_progress("shelf-1", "book-1", "user-1")
        assert progress["progress"] == 0.9
        assert progress["updatedAtMs"] == 2000


class TestResumeBook:
    def setup_method(self):
        self.library = BookshelfLibrary()
        self.library.add_book("shelf-1", "book-1", title="First", content_body="a")
        self.library.add_book("shelf-1", "book-2", title="Second", content_body="b")

    def test_resume_book_returns_none_when_no_progress(self):
        assert self.library.get_resume_book("shelf-1", "user-1") is None

    def test_resume_book_returns_most_recently_updated_unfinished_book(self):
        self.library.save_progress("shelf-1", "book-1", "user-1", 0.3, now_ms=1000)
        self.library.save_progress("shelf-1", "book-2", "user-1", 0.5, now_ms=2000)
        resume = self.library.get_resume_book("shelf-1", "user-1")
        assert resume["book"]["bookId"] == "book-2"
        assert resume["progress"] == 0.5

    def test_resume_book_skips_fully_finished_books(self):
        self.library.save_progress("shelf-1", "book-1", "user-1", 0.3, now_ms=1000)
        self.library.save_progress("shelf-1", "book-2", "user-1", 1.0, now_ms=2000)
        resume = self.library.get_resume_book("shelf-1", "user-1")
        assert resume["book"]["bookId"] == "book-1"

    def test_resume_book_returns_none_when_all_books_finished(self):
        self.library.save_progress("shelf-1", "book-1", "user-1", 1.0, now_ms=1000)
        self.library.save_progress("shelf-1", "book-2", "user-1", 1.0, now_ms=2000)
        assert self.library.get_resume_book("shelf-1", "user-1") is None

    def test_resume_book_is_scoped_per_user(self):
        self.library.save_progress("shelf-1", "book-1", "user-1", 0.3, now_ms=1000)
        assert self.library.get_resume_book("shelf-1", "user-2") is None
