"""Start DynamoDB local stand-in before the CRUD module creates its clients."""

import os
import sys
from pathlib import Path

# Lambda loads crud/ as the package root and the layer from /opt/python.
_root = Path(__file__).resolve().parents[2] / "bookstore_cdk"
sys.path.insert(0, str(_root / "layer" / "python"))
sys.path.insert(0, str(_root / "crud"))

os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["BOOKSTORE_TABLE_NAME"] = "Bookstore"
os.environ["NOTIFY_FROM_EMAIL"] = "reader@example.com"
os.environ["POWERTOOLS_SERVICE_NAME"] = "bookstore"
os.environ["POWERTOOLS_LOG_LEVEL"] = "ERROR"

from moto import mock_aws

mock_aws().start()

import boto3

from bookstore_cdk.crud import handler  # noqa: E402,F401


def _create_tables() -> None:
    client = boto3.client("dynamodb", region_name="us-east-1")
    client.create_table(
        TableName="Bookstore",
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
            {"AttributeName": "gsi1pk", "AttributeType": "S"},
            {"AttributeName": "gsi1sk", "AttributeType": "S"},
            {"AttributeName": "gsi2pk", "AttributeType": "S"},
            {"AttributeName": "gsi2sk", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "byAuthor",
                "KeySchema": [
                    {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                    {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "byAuthorName",
                "KeySchema": [
                    {"AttributeName": "gsi2pk", "KeyType": "HASH"},
                    {"AttributeName": "gsi2sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    )
    client.create_table(
        TableName="Books",
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "id", "AttributeType": "S"},
            {"AttributeName": "authorId", "AttributeType": "S"},
            {"AttributeName": "authorName", "AttributeType": "S"},
            {"AttributeName": "publishedAt", "AttributeType": "S"},
        ],
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "byAuthor",
                "KeySchema": [
                    {"AttributeName": "authorId", "KeyType": "HASH"},
                    {"AttributeName": "publishedAt", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "byAuthorName",
                "KeySchema": [
                    {"AttributeName": "authorName", "KeyType": "HASH"},
                    {"AttributeName": "publishedAt", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    )
    client.create_table(
        TableName="Presales",
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "userId", "AttributeType": "S"},
            {"AttributeName": "bookId", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "userId", "KeyType": "HASH"},
            {"AttributeName": "bookId", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "byBook",
                "KeySchema": [{"AttributeName": "bookId", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    )


_create_tables()
