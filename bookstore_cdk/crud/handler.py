"""Bookstore CRUD. API Gateway sends every request here.

Powertools picks the function from the path and method. Books and
presales are rows in the Bookstore table.
"""

from http import HTTPStatus
from typing import Annotated, Any
from uuid import uuid4

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.exceptions import (
    BadRequestError,
    NotFoundError,
    ServiceError,
)
from aws_lambda_powertools.event_handler.openapi.params import Query
from repository import AlreadyExists, NotFound, books_repository, presales_repository
from schemas import (
    Book,
    BookCreateRequest,
    BookList,
    BookUpdateRequest,
    Presale,
    PresaleCreateRequest,
    PresaleList,
    PresaleUpdateRequest,
)

logger = Logger()
app = APIGatewayRestResolver(enable_validation=True)


@app.post("/books", status_code=HTTPStatus.CREATED)
def create_book(data: BookCreateRequest) -> Book:
    """Create a book. status is PRESALE or IN_STORE."""
    book_id = str(uuid4())
    try:
        item = books_repository.create_book(book_id, data.model_dump(by_alias=True))
    except AlreadyExists as exc:
        raise ServiceError(HTTPStatus.CONFLICT, f"Book {book_id} already exists") from exc
    logger.info("created book", extra={"bookId": item["id"], "status": item["status"]})
    return Book.model_validate(item)


@app.get("/books/<book_id>")
def get_book(book_id: str) -> Book:
    """Return one book by id."""
    item = books_repository.get_book(book_id)
    if item is None:
        raise NotFoundError(f"Book {book_id} not found")
    return Book.model_validate(item)


@app.get("/books")
def list_books(
    author_id: Annotated[str | None, Query(alias="authorId")] = None,
    author_name: Annotated[str | None, Query(alias="authorName")] = None,
) -> BookList:
    """List books by authorId (byAuthor) or authorName (byAuthorName)."""
    if bool(author_id) == bool(author_name):
        raise BadRequestError("Pass authorId or authorName, not both")
    if author_id:
        items = books_repository.by_author(author_id)
    else:
        items = books_repository.by_author_name(author_name or "")
    return BookList(items=[Book.model_validate(item) for item in items])


@app.put("/books/<book_id>")
def update_book(book_id: str, data: BookUpdateRequest) -> Book:
    """Update book fields. Moving status to IN_STORE marks reservations ARRIVED."""
    fields = data.model_dump(by_alias=True, exclude_unset=True)
    try:
        item = books_repository.update_book(book_id, fields)
    except NotFound as exc:
        raise NotFoundError(f"Book {book_id} not found") from exc
    if item["status"] == "IN_STORE":
        presales_repository.mark_arrived(book_id)
    return Book.model_validate(item)


@app.delete("/books/<book_id>")
def delete_book(book_id: str):
    """Delete a book."""
    try:
        books_repository.delete_book(book_id)
    except NotFound as exc:
        raise NotFoundError(f"Book {book_id} not found") from exc
    return Response(status_code=HTTPStatus.NO_CONTENT)


@app.post("/presales", status_code=HTTPStatus.CREATED)
def create_presale(data: PresaleCreateRequest) -> Presale:
    """Reserve a PRESALE book. The reservation starts as WAITING."""
    book = books_repository.get_book(data.book_id)
    if book is None:
        raise NotFoundError(f"Book {data.book_id} not found")
    if book["status"] != "PRESALE":
        raise BadRequestError("A user can reserve a book only while it is PRESALE")
    try:
        item = presales_repository.create_presale(data.user_email, data.book_id)
    except AlreadyExists as exc:
        raise ServiceError(
            HTTPStatus.CONFLICT,
            f"{data.user_email} already reserved book {data.book_id}",
        ) from exc
    logger.info("created presale", extra={"userEmail": data.user_email, "bookId": data.book_id})
    return Presale.model_validate(item)


@app.get("/presales/<user_email>/<book_id>")
def get_presale(user_email: str, book_id: str) -> Presale:
    """Return one user's reservation for a book."""
    item = presales_repository.get_presale(user_email, book_id)
    if item is None:
        raise NotFoundError(f"Presale for {user_email} and book {book_id} not found")
    return Presale.model_validate(item)


@app.get("/presales")
def list_presales(
    user_email: Annotated[str | None, Query(alias="userEmail")] = None,
    book_id: Annotated[str | None, Query(alias="bookId")] = None,
) -> PresaleList:
    """List reservations for a userEmail, or for a bookId via byAuthor."""
    if bool(user_email) == bool(book_id):
        raise BadRequestError("Pass userEmail or bookId, not both")
    if user_email:
        items = presales_repository.by_user(user_email)
    else:
        items = presales_repository.by_book(book_id or "")
    return PresaleList(items=[Presale.model_validate(item) for item in items])


@app.put("/presales/<user_email>/<book_id>")
def update_presale(user_email: str, book_id: str, data: PresaleUpdateRequest) -> Presale:
    """Set a reservation to WAITING or ARRIVED."""
    status = data.model_dump(by_alias=True)["status"]
    try:
        item = presales_repository.update_presale(user_email, book_id, status)
    except NotFound as exc:
        raise NotFoundError(f"Presale for {user_email} and book {book_id} not found") from exc
    return Presale.model_validate(item)


@app.delete("/presales/<user_email>/<book_id>")
def delete_presale(user_email: str, book_id: str):
    """Delete one reservation."""
    try:
        presales_repository.delete_presale(user_email, book_id)
    except NotFound as exc:
        raise NotFoundError(f"Presale for {user_email} and book {book_id} not found") from exc
    return Response(status_code=HTTPStatus.NO_CONTENT)


@logger.inject_lambda_context
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return app.resolve(event, context)
