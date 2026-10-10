import json
from typing import Any

import pytest

import repository
from bookstore_cdk.crud import handler


@pytest.fixture(autouse=True)
def _empty_tables():
    _wipe(repository.books_repository.table, ("id",))
    _wipe(repository.presales_repository.table, ("userId", "bookId"))
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
        "isFavorite": False,
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
        {"userId": "user-1", "bookId": book["id"]},
    )
    assert created == 201
    assert presale["status"] == "WAITING"

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
        {"userId": "user-1", "bookId": in_store["id"]},
    )
    assert rejected == 400
    assert "PRESALE" in error["message"]

    updated, arrived_book = _call("PUT", f"/books/{book['id']}", {"status": "IN_STORE"})
    assert updated == 200
    assert arrived_book["status"] == "IN_STORE"

    status, reservation = _call("GET", f"/presales/user-1/{book['id']}")
    assert status == 200
    assert reservation["status"] == "ARRIVED"

    listed, who = _call("GET", "/presales", query={"bookId": book["id"]})
    assert listed == 200
    assert who["items"] == [{"userId": "user-1", "bookId": book["id"], "status": "ARRIVED"}]


def test_duplicate_reservation_conflicts_and_delete_removes_the_book():
    _, book = _call("POST", "/books", _book(authorId="author-9", title="Once"))
    assert _call("POST", "/presales", {"userId": "user-9", "bookId": book["id"]})[0] == 201
    conflict, error = _call("POST", "/presales", {"userId": "user-9", "bookId": book["id"]})
    assert conflict == 409
    assert "already reserved" in error["message"]

    missing, _ = _call("GET", "/books/does-not-exist")
    assert missing == 404

    deleted, empty = _call("DELETE", f"/books/{book['id']}")
    assert deleted == 204
    assert empty is None
    assert _call("GET", f"/books/{book['id']}")[0] == 404
