"""Books, presales, and favorites on the Bookstore table.

A book is stored at pk = sk = BOOK#<id>. A presale is stored at
pk = USER#<userEmail>, sk = BOOK#<bookId>. A favorite is stored at
pk = USER#<userEmail>, sk = AUTHOR#<authorId>. byAuthor reads gsi1pk.
byAuthorName reads gsi2pk.
"""

from typing import Any

from config import settings
from keys import (
    book_item,
    favorite_item,
    presale_item,
    public_book,
    public_favorite,
    public_presale,
)
from table_repository import AlreadyExists, NotFound, TableRepository

__all__ = [
    "AlreadyExists",
    "NotFound",
    "books_repository",
    "favorites_repository",
    "presales_repository",
]


class BooksRepository(TableRepository):
    """Books inside Bookstore."""

    def create_book(self, book_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Insert a book and return the API fields."""
        item = book_item(book_id, fields)
        self.create(item)
        return public_book(item)

    def get_book(self, book_id: str) -> dict[str, Any] | None:
        """Return one book, or None when that id is missing."""
        item = self.get(pk=f"BOOK#{book_id}", sk=f"BOOK#{book_id}")
        if item is None:
            return None
        return public_book(item)

    def update_book(self, book_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Replace the given book fields and refresh its index keys."""
        current = self.get(pk=f"BOOK#{book_id}", sk=f"BOOK#{book_id}")
        if current is None:
            raise NotFound("pk")
        merged = public_book(current)
        merged.pop("id")
        merged.update(fields)
        stored = book_item(book_id, merged)
        updated = self.update(
            {name: value for name, value in stored.items() if name not in ("pk", "sk")},
            pk=stored["pk"],
            sk=stored["sk"],
        )
        return public_book(updated)

    def delete_book(self, book_id: str) -> None:
        """Delete the book row."""
        self.delete(pk=f"BOOK#{book_id}", sk=f"BOOK#{book_id}")

    def by_author(self, author_id: str) -> list[dict[str, Any]]:
        """Return this author's books, oldest publishedAt first."""
        items = self.search(
            {"gsi1pk": f"AUTHOR#{author_id}"},
            index="byAuthor",
            paginate=False,
        )
        return [public_book(item) for item in items]

    def by_author_name(self, author_name: str) -> list[dict[str, Any]]:
        """Return books with this author name, oldest publishedAt first."""
        items = self.search(
            {"gsi2pk": f"AUTHORNAME#{author_name}"},
            index="byAuthorName",
            paginate=False,
        )
        return [public_book(item) for item in items]


class PresalesRepository(TableRepository):
    """Presales inside Bookstore."""

    def create_presale(self, user_email: str, book_id: str) -> dict[str, Any]:
        """Insert a WAITING reservation and return the API fields."""
        item = presale_item(user_email, book_id, "WAITING")
        self.create(item)
        return public_presale(item)

    def get_presale(self, user_email: str, book_id: str) -> dict[str, Any] | None:
        """Return one reservation, or None when it is missing."""
        item = self.get(pk=f"USER#{user_email}", sk=f"BOOK#{book_id}")
        if item is None:
            return None
        return public_presale(item)

    def update_presale(self, user_email: str, book_id: str, status: str) -> dict[str, Any]:
        """Set the reservation status."""
        item = self.update(
            {"status": status},
            pk=f"USER#{user_email}",
            sk=f"BOOK#{book_id}",
        )
        return public_presale(item)

    def delete_presale(self, user_email: str, book_id: str) -> None:
        """Delete one reservation."""
        self.delete(pk=f"USER#{user_email}", sk=f"BOOK#{book_id}")

    def by_user(self, user_email: str) -> list[dict[str, Any]]:
        """Return the reservations stored under this email."""
        items = self.search({"pk": f"USER#{user_email}"}, paginate=False)
        return [public_presale(item) for item in items if item.get("entity") == "PRESALE"]

    def by_book(self, book_id: str) -> list[dict[str, Any]]:
        """Return who reserved this book, via byAuthor."""
        items = self.search(
            {"gsi1pk": f"BOOK#{book_id}"},
            index="byAuthor",
            paginate=False,
        )
        return [public_presale(item) for item in items]

    def mark_arrived(self, book_id: str) -> None:
        """Set every waiting reservation for this book to ARRIVED."""
        for reservation in self.search(
            {"gsi1pk": f"BOOK#{book_id}"},
            index="byAuthor",
            paginate=False,
        ):
            if reservation["status"] == "ARRIVED":
                continue
            self.update(
                {"status": "ARRIVED"},
                pk=reservation["pk"],
                sk=reservation["sk"],
            )


class FavoritesRepository(TableRepository):
    """Favorites inside Bookstore."""

    def create_favorite(self, user_email: str, author_id: str) -> dict[str, Any]:
        """Insert one user's favorite author and return the API fields."""
        item = favorite_item(user_email, author_id)
        self.create(item)
        return public_favorite(item)

    def get_favorite(self, user_email: str, author_id: str) -> dict[str, Any] | None:
        """Return one favorite, or None when it is missing."""
        item = self.get(pk=f"USER#{user_email}", sk=f"AUTHOR#{author_id}")
        if item is None:
            return None
        return public_favorite(item)

    def delete_favorite(self, user_email: str, author_id: str) -> None:
        """Delete one user's favorite author."""
        self.delete(pk=f"USER#{user_email}", sk=f"AUTHOR#{author_id}")

    def by_user(self, user_email: str) -> list[dict[str, Any]]:
        """Return the authors this user favorited."""
        items = self.search({"pk": f"USER#{user_email}"}, paginate=False)
        return [public_favorite(item) for item in items if item.get("entity") == "FAVORITE"]

    def by_author(self, author_id: str) -> list[dict[str, Any]]:
        """Return who favorited this author, via byAuthor."""
        items = self.search(
            {"gsi1pk": f"FAVORITE#{author_id}"},
            index="byAuthor",
            paginate=False,
        )
        return [public_favorite(item) for item in items]


books_repository = BooksRepository(
    table_name=settings.BOOKSTORE_TABLE_NAME,
    pk_attr="pk",
)

presales_repository = PresalesRepository(
    table_name=settings.BOOKSTORE_TABLE_NAME,
    pk_attr="pk",
)

favorites_repository = FavoritesRepository(
    table_name=settings.BOOKSTORE_TABLE_NAME,
    pk_attr="pk",
)
