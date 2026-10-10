"""Books and Presales repositories.

Same shape as the other backends: a subclass for the queries that are
specific to the table, then one instance per table at import time.
"""

from typing import Any

from config import settings
from table_repository import AlreadyExists, NotFound, TableRepository

__all__ = ["AlreadyExists", "NotFound", "books_repository", "presales_repository"]


class BooksRepository(TableRepository):
    """Books, keyed by id."""

    def by_author(self, author_id: str) -> list[dict[str, Any]]:
        """Return the books for this author id, ordered by publishedAt."""
        return self.search({"authorId": author_id}, index="byAuthor", paginate=False)

    def by_author_name(self, author_name: str) -> list[dict[str, Any]]:
        """Return the books with this author name, ordered by publishedAt."""
        return self.search({"authorName": author_name}, index="byAuthorName", paginate=False)


class PresalesRepository(TableRepository):
    """Presales, keyed by userId and bookId."""

    def by_user(self, user_id: str) -> list[dict[str, Any]]:
        """Return the reservations for this user."""
        return self.search({"userId": user_id}, paginate=False)

    def by_book(self, book_id: str) -> list[dict[str, Any]]:
        """Return the reservations for this book."""
        return self.search({"bookId": book_id}, index="byBook", paginate=False)

    def mark_arrived(self, book_id: str) -> None:
        """Set every waiting reservation for this book to ARRIVED."""
        for reservation in self.by_book(book_id):
            if reservation["status"] == "ARRIVED":
                continue
            self.update(
                {"status": "ARRIVED"},
                userId=reservation["userId"],
                bookId=book_id,
            )


books_repository = BooksRepository(
    table_name=settings.BOOKS_TABLE_NAME,
    pk_attr="id",
)

presales_repository = PresalesRepository(
    table_name=settings.PRESALES_TABLE_NAME,
    pk_attr="userId",
)
