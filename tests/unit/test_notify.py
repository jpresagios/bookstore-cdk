"""Stream handlers send SES mail for favorite presales and arrivals."""

import importlib.util
from pathlib import Path

import boto3
from boto3.dynamodb.types import TypeSerializer

from keys import book_item, favorite_item, presale_item

_serializer = TypeSerializer()
_NOTIFY = Path(__file__).resolve().parents[2] / "bookstore_cdk" / "notify" / "handler.py"


def _load_notify():
    spec = importlib.util.spec_from_file_location("notify_handler", _NOTIFY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


notify = _load_notify()


class _Context:
    function_name = "notify"
    memory_limit_in_mb = 128
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:notify"
    aws_request_id = "test-request"


def _table():
    return boto3.resource("dynamodb", region_name="us-east-1").Table("Bookstore")


def _wipe() -> None:
    table = _table()
    for item in table.scan().get("Items", []):
        table.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})


def _verify_inbox(*addresses: str) -> None:
    client = boto3.client("ses", region_name="us-east-1")
    for address in ("reader@example.com", *addresses):
        client.verify_email_identity(EmailAddress=address)


def _sent_to() -> list[str]:
    return [message.destinations["ToAddresses"][0] for message in _mailbox().sent_messages]


def _record(image: dict) -> dict:
    return {
        "Records": [
            {
                "eventName": "INSERT",
                "dynamodb": {
                    "NewImage": {key: _serializer.serialize(value) for key, value in image.items()}
                },
            }
        ]
    }


def _mailbox():
    from moto.ses.models import ses_backends

    return ses_backends["123456789012"]["us-east-1"]


def _clear_sent() -> None:
    _mailbox().sent_messages.clear()


def _sent_subjects() -> list[str]:
    return [message.subject for message in _mailbox().sent_messages]


def test_favorite_author_presale_sends_mail_and_other_authors_do_not():
    _wipe()
    _verify_inbox("ana@example.com", "leo@example.com")
    _clear_sent()
    table = _table()
    favorite = book_item(
        "book-fav",
        {
            "authorId": "garcia-marquez",
            "authorName": "Gabriel García Márquez",
            "title": "El amor en los tiempos del cólera",
            "status": "IN_STORE",
            "publishedAt": "1985-12-05T00:00:00Z",
        },
    )
    presale = book_item(
        "book-new",
        {
            "authorId": "garcia-marquez",
            "authorName": "Gabriel García Márquez",
            "title": "Cien años de soledad",
            "status": "PRESALE",
            "publishedAt": "1967-05-30T00:00:00Z",
        },
    )
    other = book_item(
        "book-other",
        {
            "authorId": "borges",
            "authorName": "Jorge Luis Borges",
            "title": "Ficciones",
            "status": "PRESALE",
            "publishedAt": "1944-01-01T00:00:00Z",
        },
    )
    table.put_item(Item=favorite)
    table.put_item(Item=presale)
    table.put_item(Item=other)
    table.put_item(Item=favorite_item("ana@example.com", "garcia-marquez"))
    table.put_item(Item=presale_item("leo@example.com", "book-fav", "WAITING"))

    notify.on_favorite_presale(_record(presale), _Context())
    notify.on_favorite_presale(_record(other), _Context())

    assert _sent_subjects() == ["Favorite author published a presale: Cien años de soledad"]
    assert _sent_to() == ["ana@example.com"]


def test_arrival_mail_names_the_users_who_reserved_the_book():
    _wipe()
    _verify_inbox("ana@example.com")
    _clear_sent()
    table = _table()
    book = book_item(
        "book-arrived",
        {
            "authorId": "borges",
            "authorName": "Jorge Luis Borges",
            "title": "Ficciones",
            "status": "IN_STORE",
            "publishedAt": "1944-01-01T00:00:00Z",
        },
    )
    table.put_item(Item=book)
    table.put_item(Item=presale_item("ana@example.com", "book-arrived", "ARRIVED"))

    notify.on_book_arrived(_record(book), _Context())
    subjects = _sent_subjects()
    assert subjects == ["Reserved book arrived: Ficciones"]
    assert _sent_to() == ["ana@example.com"]

    notify.on_book_arrived(
        _record(
            book_item(
                "book-alone",
                {
                    "authorId": "borges",
                    "authorName": "Jorge Luis Borges",
                    "title": "El Aleph",
                    "status": "IN_STORE",
                    "publishedAt": "1949-01-01T00:00:00Z",
                },
            )
        ),
        _Context(),
    )
    assert _sent_subjects() == subjects
