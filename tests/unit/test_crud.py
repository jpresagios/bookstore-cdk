import json
from typing import Any

import pytest

import repository
from bookstore_cdk.crud import handler


@pytest.fixture(autouse=True)
def _empty_tables():
    _wipe(repository.books_repository.table, ("pk", "sk"))
    yield


def _wipe(table: Any, keys: tuple[str, ...]) -> None:
    response = table.scan()
    for item in response.get("Items", []):
        table.delete_item(Key={key: item[key] for key in keys})


class _Context:
    function_name = "bookstore"
    memory_limit_in_mb = 128
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:bookstore"
    aws_request_id = "test-request"

    def get_remaining_time_in_millis(self) -> int:
        return 10_000


def _call(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
) -> tuple[int, Any]:
    event = {
        "resource": "/{proxy+}",
        "path": path,
        "httpMethod": method,
        "headers": {"Content-Type": "application/json"},
        "queryStringParameters": query,
        "pathParameters": {"proxy": path.lstrip("/")},
        "requestContext": {
            "resourcePath": "/{proxy+}",
            "httpMethod": method,
            "path": path,
            "requestId": "test-request",
            "stage": "prod",
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }
    result = handler.handler(event, _Context())
    status = result["statusCode"]
    payload = json.loads(result["body"]) if result.get("body") else None
    return status, payload


def _book(**overrides: Any) -> dict[str, Any]:
    item = {
        "authorId": "author-1",
        "authorName": "Ana García",
        "title": "North Wind",
        "status": "PRESALE",
        "publishedAt": "2026-01-01T00:00:00Z",
    }
    item.update(overrides)
    return item


def test_author_id_keeps_people_with_the_same_name_apart():
    first = _call("POST", "/books", _book(authorId="ana-1", title="First", publishedAt="2026-01-01T00:00:00Z"))
    second = _call(
        "POST",
        "/books",
        _book(authorId="ana-2", title="Second", publishedAt="2026-06-01T00:00:00Z"),
    )
    assert first[0] == 201
    assert second[0] == 201
    stored = repository.books_repository.table.get_item(
        Key={"pk": f"BOOK#{first[1]['id']}", "sk": f"BOOK#{first[1]['id']}"}
    )["Item"]
    assert stored["entity"] == "BOOK"
    assert stored["gsi1pk"] == "AUTHOR#ana-1"
    assert stored["gsi1sk"] == "2026-01-01T00:00:00Z"
    assert stored["gsi2pk"] == "AUTHORNAME#Ana García"

    by_name, books = _call("GET", "/books", query={"authorName": "Ana García"})
    assert by_name == 200
    assert {book["title"] for book in books["items"]} == {"First", "Second"}

    by_id, only_first = _call("GET", "/books", query={"authorId": "ana-1"})
    assert by_id == 200
    assert [book["title"] for book in only_first["items"]] == ["First"]


def test_presale_waits_until_the_book_arrives():
    _, book = _call("POST", "/books", _book(authorId="author-arrive", title="Coming"))
    created, presale = _call(
        "POST",
        "/presales",
        {"userEmail": "ana@example.com", "bookId": book["id"]},
    )
    assert created == 201
    assert presale["status"] == "WAITING"
    stored = repository.presales_repository.table.get_item(
        Key={"pk": "USER#ana@example.com", "sk": f"BOOK#{book['id']}"}
    )["Item"]
    assert stored["entity"] == "PRESALE"
    assert stored["userEmail"] == "ana@example.com"
    assert stored["gsi1pk"] == f"BOOK#{book['id']}"
    assert stored["gsi1sk"] == "USER#ana@example.com"
    assert "gsi2pk" not in stored

    _, in_store = _call(
        "POST",
        "/books",
        _book(
            authorId="author-arrive",
            title="Already here",
            status="IN_STORE",
            publishedAt="2026-02-01T00:00:00Z",
        ),
    )
    rejected, error = _call(
        "POST",
        "/presales",
        {"userEmail": "ana@example.com", "bookId": in_store["id"]},
    )
    assert rejected == 400
    assert "PRESALE" in error["message"]

    updated, arrived_book = _call("PUT", f"/books/{book['id']}", {"status": "IN_STORE"})
    assert updated == 200
    assert arrived_book["status"] == "IN_STORE"

    status, reservation = _call("GET", f"/presales/ana@example.com/{book['id']}")
    assert status == 200
    assert reservation["status"] == "ARRIVED"

    listed, who = _call("GET", "/presales", query={"bookId": book["id"]})
    assert listed == 200
    assert who["items"] == [{"userEmail": "ana@example.com", "bookId": book["id"], "status": "ARRIVED"}]


def test_a_user_favorites_an_author_without_marking_the_book():
    _, book = _call("POST", "/books", _book(authorId="garcia-marquez", title="Cien años"))
    missing_author, missing_error = _call(
        "POST",
        "/favorites",
        {"userEmail": "Ana@Example.com", "authorId": "nobody"},
    )
    assert missing_author == 404
    assert "nobody" in missing_error["message"]

    created, favorite = _call(
        "POST",
        "/favorites",
        {"userEmail": "Ana@Example.com", "authorId": "garcia-marquez"},
    )
    assert created == 201
    assert favorite == {"userEmail": "ana@example.com", "authorId": "garcia-marquez"}
    stored = repository.favorites_repository.table.get_item(
        Key={"pk": "USER#ana@example.com", "sk": "AUTHOR#garcia-marquez"}
    )["Item"]
    assert stored["entity"] == "FAVORITE"
    assert stored["gsi1pk"] == "FAVORITE#garcia-marquez"
    assert stored["gsi1sk"] == "USER#ana@example.com"
    assert "gsi2pk" not in stored
    assert "isFavorite" not in repository.books_repository.get_book(book["id"])

    conflict, error = _call(
        "POST",
        "/favorites",
        {"userEmail": "ana@example.com", "authorId": "garcia-marquez"},
    )
    assert conflict == 409
    assert "already favorited" in error["message"]

    _, reservation = _call(
        "POST",
        "/presales",
        {"userEmail": "ana@example.com", "bookId": book["id"]},
    )
    assert reservation["status"] == "WAITING"
    listed_presales, presales = _call("GET", "/presales", query={"userEmail": "ana@example.com"})
    assert listed_presales == 200
    assert presales["items"] == [
        {"userEmail": "ana@example.com", "bookId": book["id"], "status": "WAITING"}
    ]

    by_user, mine = _call("GET", "/favorites", query={"userEmail": "ana@example.com"})
    by_author, fans = _call("GET", "/favorites", query={"authorId": "garcia-marquez"})
    assert by_user == 200
    assert by_author == 200
    assert mine["items"] == fans["items"] == [favorite]

    deleted, empty = _call("DELETE", "/favorites/ana@example.com/garcia-marquez")
    assert deleted == 204
    assert empty is None
    assert _call("GET", "/favorites/ana@example.com/garcia-marquez")[0] == 404


def test_duplicate_reservation_conflicts_and_delete_removes_the_book():
    _, book = _call("POST", "/books", _book(authorId="author-9", title="Once"))
    assert _call("POST", "/presales", {"userEmail": "ana@example.com", "bookId": book["id"]})[0] == 201
    conflict, error = _call("POST", "/presales", {"userEmail": "ana@example.com", "bookId": book["id"]})
    assert conflict == 409
    assert "already reserved" in error["message"]

    missing, _ = _call("GET", "/books/does-not-exist")
    assert missing == 404

    deleted, empty = _call("DELETE", f"/books/{book['id']}")
    assert deleted == 204
    assert empty is None
    assert _call("GET", f"/books/{book['id']}")[0] == 404
