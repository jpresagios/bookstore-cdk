"""Copy Books and Presales into Bookstore.

A row that already has the same pk and sk is left as it is, so the
script can be run again. It does not delete the old tables.
"""

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from keys import book_item, presale_item


def migrate(books: Any, presales: Any, bookstore: Any) -> dict[str, int]:
    """Copy every legacy row. Return how many were written and skipped."""
    copied = 0
    skipped = 0
    for source, build in (
        (books, _book_row),
        (presales, _presale_row),
    ):
        for legacy in _scan(source):
            if _put_new(bookstore, build(legacy)):
                copied += 1
            else:
                skipped += 1
    return {"copied": copied, "skipped": skipped}


def main() -> None:
    """Read the three table names from the environment and copy."""
    dynamodb = boto3.resource("dynamodb")
    result = migrate(
        dynamodb.Table(os.environ.get("BOOKS_TABLE_NAME", "Books")),
        dynamodb.Table(os.environ.get("PRESALES_TABLE_NAME", "Presales")),
        dynamodb.Table(os.environ.get("BOOKSTORE_TABLE_NAME", "Bookstore")),
    )
    print(f"copied {result['copied']}, skipped {result['skipped']}")


def _book_row(item: dict[str, Any]) -> dict[str, Any]:
    return book_item(item["id"], item)


def _presale_row(item: dict[str, Any]) -> dict[str, Any]:
    return presale_item(item["userId"], item["bookId"], item["status"])


def _scan(table: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {}
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            return items
        kwargs["ExclusiveStartKey"] = last_key


def _put_new(table: Any, item: dict[str, Any]) -> bool:
    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
    return True
