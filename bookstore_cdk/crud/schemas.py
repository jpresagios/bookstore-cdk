"""Request and response models for the bookstore CRUD routes.

Python fields are snake_case. The API and DynamoDB use camelCase, so
model_dump(by_alias=True) is the write to the table.
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


def _camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part.capitalize() for part in rest)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel,
        populate_by_name=True,
        extra="forbid",
        use_enum_values=True,
    )


class BookStatus(str, Enum):
    PRESALE = "PRESALE"
    IN_STORE = "IN_STORE"


class PresaleStatus(str, Enum):
    WAITING = "WAITING"
    ARRIVED = "ARRIVED"


def _text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be blank")
    return stripped


def _published_at(value: str) -> str:
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ValueError("publishedAt must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError("publishedAt must include a timezone")
    utc = parsed.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


class BookCreateRequest(CamelModel):
    """Body for POST /books."""

    author_id: str
    author_name: str
    title: str
    status: BookStatus
    published_at: str
    is_favorite: bool = False

    @field_validator("author_id", "author_name", "title")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _text(value)

    @field_validator("published_at")
    @classmethod
    def normalize_published_at(cls, value: str) -> str:
        return _published_at(value)


class BookUpdateRequest(CamelModel):
    """Body for PUT /books/{id}. Send only the fields that change."""

    author_id: str | None = None
    author_name: str | None = None
    title: str | None = None
    status: BookStatus | None = None
    published_at: str | None = None
    is_favorite: bool | None = None

    @field_validator("author_id", "author_name", "title")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _text(value)

    @field_validator("published_at")
    @classmethod
    def normalize_published_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _published_at(value)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "BookUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Provide at least one book field to update")
        return self


class Book(CamelModel):
    """A book row."""

    id: str
    author_id: str
    author_name: str
    title: str
    status: BookStatus
    published_at: str
    is_favorite: bool


class BookList(CamelModel):
    """Books returned by byAuthor or byAuthorName."""

    items: list[Book]


class PresaleCreateRequest(CamelModel):
    """Body for POST /presales."""

    user_id: str
    book_id: str

    @field_validator("user_id", "book_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _text(value)


class PresaleUpdateRequest(CamelModel):
    """Body for PUT /presales/{userId}/{bookId}."""

    status: PresaleStatus


class Presale(CamelModel):
    """One user's reservation for a book."""

    user_id: str
    book_id: str
    status: PresaleStatus


class PresaleList(CamelModel):
    """Reservations for a user or for a book."""

    items: list[Presale]
