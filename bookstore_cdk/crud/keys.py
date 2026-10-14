"""Build the Bookstore item shape from a book, a presale, or a favorite.

pk and sk are the table key. gsi1pk and gsi1sk feed the byAuthor index.
gsi2pk and gsi2sk feed byAuthorName. A presale or a favorite leaves gsi2
empty, so that index only contains books.
"""

from typing import Any


def book_item(book_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Return the Bookstore row for a book."""
    published_at = fields["publishedAt"]
    key = f"BOOK#{book_id}"
    return {
        "pk": key,
        "sk": key,
        "entity": "BOOK",
        "authorId": fields["authorId"],
        "authorName": fields["authorName"],
        "title": fields["title"],
        "status": fields["status"],
        "publishedAt": published_at,
        "gsi1pk": f"AUTHOR#{fields['authorId']}",
        "gsi1sk": published_at,
        "gsi2pk": f"AUTHORNAME#{fields['authorName']}",
        "gsi2sk": published_at,
    }


def presale_item(user_email: str, book_id: str, status: str) -> dict[str, Any]:
    """Return the Bookstore row for a reservation."""
    return {
        "pk": f"USER#{user_email}",
        "sk": f"BOOK#{book_id}",
        "entity": "PRESALE",
        "userEmail": user_email,
        "bookId": book_id,
        "status": status,
        "gsi1pk": f"BOOK#{book_id}",
        "gsi1sk": f"USER#{user_email}",
    }


def favorite_item(user_email: str, author_id: str) -> dict[str, Any]:
    """Return the Bookstore row for one user favoring one author."""
    return {
        "pk": f"USER#{user_email}",
        "sk": f"AUTHOR#{author_id}",
        "entity": "FAVORITE",
        "userEmail": user_email,
        "authorId": author_id,
        "gsi1pk": f"FAVORITE#{author_id}",
        "gsi1sk": f"USER#{user_email}",
    }


def public_book(item: dict[str, Any]) -> dict[str, Any]:
    """Return the book fields the API exposes."""
    return {
        "id": item["pk"].removeprefix("BOOK#"),
        "authorId": item["authorId"],
        "authorName": item["authorName"],
        "title": item["title"],
        "status": item["status"],
        "publishedAt": item["publishedAt"],
    }


def public_favorite(item: dict[str, Any]) -> dict[str, Any]:
    """Return the favorite fields the API exposes."""
    return {
        "userEmail": item["userEmail"],
        "authorId": item["authorId"],
    }


def public_presale(item: dict[str, Any]) -> dict[str, Any]:
    """Return the reservation fields the API exposes."""
    return {
        "userEmail": item["userEmail"],
        "bookId": item["bookId"],
        "status": item["status"],
    }
