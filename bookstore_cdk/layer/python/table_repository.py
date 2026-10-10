"""Small DynamoDB table access, shipped in a Lambda layer.

AWS mounts this file at /opt/python, so a function imports it with
`from table_repository import TableRepository`.

get(**keys), create(item), update(updates, **keys), delete(**keys),
and search(query, index=..., paginate=False).
"""

from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

_dynamodb = boto3.resource("dynamodb")


class AlreadyExists(Exception):
    """The item is already stored under that key."""


class NotFound(Exception):
    """The item is not stored under that key."""


class TableRepository:
    """Read and write one DynamoDB table."""

    def __init__(self, table_name: str, pk_attr: str = "id", **kwargs: Any) -> None:
        self.table = _dynamodb.Table(table_name)
        self.pk_attr = pk_attr

    def get(self, **keys: str) -> dict[str, Any] | None:
        """Return the item for these keys, or None when it is missing."""
        return self.table.get_item(Key=keys).get("Item")

    def create(self, item: dict[str, Any]) -> dict[str, Any]:
        """Insert an item. Fail when the partition key is already present."""
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression=f"attribute_not_exists({self.pk_attr})",
            )
        except ClientError as exc:
            if _condition_failed(exc):
                raise AlreadyExists(self.pk_attr) from exc
            raise
        return item

    def update(self, updates: dict[str, Any], **keys: str) -> dict[str, Any]:
        """Set the given fields and return the stored item."""
        names = {f"#vname{index}": name for index, name in enumerate(updates)}
        values = {f":val{index}": value for index, value in enumerate(updates.values())}
        assignment = ", ".join(f"#vname{index}=:val{index}" for index in range(len(updates)))
        try:
            response = self.table.update_item(
                Key=keys,
                UpdateExpression=f"SET {assignment}",
                ConditionExpression=f"attribute_exists({self.pk_attr})",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if _condition_failed(exc):
                raise NotFound(self.pk_attr) from exc
            raise
        return response["Attributes"]

    def delete(self, **keys: str) -> None:
        """Delete an item. Fail when the partition key is missing."""
        try:
            self.table.delete_item(
                Key=keys,
                ConditionExpression=f"attribute_exists({self.pk_attr})",
            )
        except ClientError as exc:
            if _condition_failed(exc):
                raise NotFound(self.pk_attr) from exc
            raise

    def search(
        self,
        query: dict[str, Any],
        *,
        index: str | None = None,
        paginate: bool = False,
    ) -> list[dict[str, Any]]:
        """Return the items whose key matches this query.

        paginate is accepted so call sites match the other backends.
        This table is small, so every page is returned either way.
        """
        condition = None
        for name, value in query.items():
            part = Key(name).eq(value)
            condition = part if condition is None else condition & part
        kwargs: dict[str, Any] = {"KeyConditionExpression": condition}
        if index:
            kwargs["IndexName"] = index
        items: list[dict[str, Any]] = []
        while True:
            response = self.table.query(**kwargs)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if paginate or not last_key:
                return items
            kwargs["ExclusiveStartKey"] = last_key


def _condition_failed(error: ClientError) -> bool:
    return error.response["Error"]["Code"] == "ConditionalCheckFailedException"
