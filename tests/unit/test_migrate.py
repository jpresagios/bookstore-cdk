"""Copy legacy Books and Presales rows into Bookstore."""

import boto3

from migrate import migrate


def _table(name: str):
    return boto3.resource("dynamodb", region_name="us-east-1").Table(name)


def _wipe(table, keys: tuple[str, ...]) -> None:
    for item in table.scan().get("Items", []):
        table.delete_item(Key={key: item[key] for key in keys})


def test_migration_copies_once_and_skips_the_second_run():
    books = _table("Books")
    presales = _table("Presales")
    bookstore = _table("Bookstore")
    _wipe(books, ("id",))
    _wipe(presales, ("userId", "bookId"))
    _wipe(bookstore, ("pk", "sk"))

    books.put_item(
        Item={
            "id": "33bb7fa9-bfeb-4810-bbb0-e3a06afd368f",
            "authorId": "garcia-marquez",
            "authorName": "Gabriel García Márquez",
            "title": "Cien años de soledad",
            "status": "PRESALE",
            "publishedAt": "1967-05-30T00:00:00Z",
            "isFavorite": False,
        }
    )
    presales.put_item(
        Item={
            "userId": "user-1",
            "bookId": "e381f50c-48f5-4997-8b04-8fbfb36e6a57",
            "status": "WAITING",
        }
    )

    first = migrate(books, presales, bookstore)
    second = migrate(books, presales, bookstore)

    assert first == {"copied": 2, "skipped": 0}
    assert second == {"copied": 0, "skipped": 2}

    book = bookstore.get_item(
        Key={
            "pk": "BOOK#33bb7fa9-bfeb-4810-bbb0-e3a06afd368f",
            "sk": "BOOK#33bb7fa9-bfeb-4810-bbb0-e3a06afd368f",
        }
    )["Item"]
    assert book["gsi1pk"] == "AUTHOR#garcia-marquez"
    assert book["gsi2pk"] == "AUTHORNAME#Gabriel García Márquez"
    assert book["title"] == "Cien años de soledad"
    assert "isFavorite" not in book

    reservation = bookstore.get_item(
        Key={
            "pk": "USER#user-1",
            "sk": "BOOK#e381f50c-48f5-4997-8b04-8fbfb36e6a57",
        }
    )["Item"]
    assert reservation["gsi1pk"] == "BOOK#e381f50c-48f5-4997-8b04-8fbfb36e6a57"
    assert reservation["status"] == "WAITING"
    assert "gsi2pk" not in reservation
