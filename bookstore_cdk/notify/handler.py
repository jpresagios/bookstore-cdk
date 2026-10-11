"""Email notices for Bookstore stream records.

on_favorite_presale runs when a PRESALE book is inserted. It emails
every address that already reserved a book by that author, when the
author is marked favorite.

on_book_arrived runs when that book moves from PRESALE to IN_STORE.
It emails each reservation's userEmail.
"""

import os
from typing import Any

import boto3
from aws_lambda_powertools import Logger
from boto3.dynamodb.types import TypeDeserializer
from table_repository import TableRepository

logger = Logger()
_ses = boto3.client("ses")
_deser = TypeDeserializer()
_table = TableRepository(os.environ["BOOKSTORE_TABLE_NAME"], pk_attr="pk")
_from = os.environ["NOTIFY_FROM_EMAIL"]


@logger.inject_lambda_context
def on_favorite_presale(event: dict[str, Any], context: Any) -> None:
    """Email readers when a favorite author publishes a presale book."""
    for record in event["Records"]:
        book = _image(record["dynamodb"]["NewImage"])
        if not _author_is_favorite(book):
            logger.info("author is not a favorite", extra={"authorId": book["authorId"]})
            continue
        emails = _emails_for_author(book["authorId"])
        if not emails:
            logger.info("favorite author has no reservations", extra={"authorId": book["authorId"]})
            continue
        for email in emails:
            _send(
                email,
                f"Favorite author published a presale: {book['title']}",
                f"{book['authorName']} published {book['title']} as a presale.",
            )


@logger.inject_lambda_context
def on_book_arrived(event: dict[str, Any], context: Any) -> None:
    """Email each address that reserved a book when it arrives."""
    for record in event["Records"]:
        book = _image(record["dynamodb"]["NewImage"])
        book_id = book["pk"].removeprefix("BOOK#")
        reservations = _table.search(
            {"gsi1pk": f"BOOK#{book_id}"},
            index="byAuthor",
            paginate=False,
        )
        emails = [item["userEmail"] for item in reservations if item.get("userEmail")]
        if not emails:
            logger.info("book arrived with no reservations", extra={"bookId": book_id})
            continue
        for email in emails:
            _send(
                email,
                f"Reserved book arrived: {book['title']}",
                f"{book['title']} is in the store. Your reservation is ready.",
            )


def _author_is_favorite(book: dict[str, Any]) -> bool:
    """An author is favorite when any of their books has isFavorite set."""
    books = _table.search(
        {"gsi1pk": f"AUTHOR#{book['authorId']}"},
        index="byAuthor",
        paginate=False,
    )
    return any(item.get("isFavorite") for item in books)


def _emails_for_author(author_id: str) -> list[str]:
    """Return each address that reserved a book by this author."""
    emails: list[str] = []
    books = _table.search(
        {"gsi1pk": f"AUTHOR#{author_id}"},
        index="byAuthor",
        paginate=False,
    )
    for book in books:
        book_id = book["pk"].removeprefix("BOOK#")
        for reservation in _table.search(
            {"gsi1pk": f"BOOK#{book_id}"},
            index="byAuthor",
            paginate=False,
        ):
            email = reservation.get("userEmail")
            if email and email not in emails:
                emails.append(email)
    return emails


def _image(raw: dict[str, Any]) -> dict[str, Any]:
    return {key: _deser.deserialize(value) for key, value in raw.items()}


def _send(to: str, subject: str, body: str) -> None:
    _ses.send_email(
        Source=_from,
        Destination={"ToAddresses": [to]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": body}},
        },
    )
    logger.info("sent notification", extra={"subject": subject, "to": to})
