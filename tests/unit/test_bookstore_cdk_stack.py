import aws_cdk as core
import aws_cdk.assertions as assertions

from bookstore_cdk.bookstore_cdk_stack import BookstoreCdkStack


def _template() -> assertions.Template:
    app = core.App()
    stack = BookstoreCdkStack(app, "bookstore-cdk")
    return assertions.Template.from_stack(stack)


def test_books_table_and_author_indexes():
    template = _template()
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "Books",
            "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
            "KeySchema": [{"AttributeName": "id", "KeyType": "HASH"}],
            "GlobalSecondaryIndexes": assertions.Match.array_with(
                [
                    assertions.Match.object_like(
                        {
                            "IndexName": "byAuthor",
                            "KeySchema": [
                                {"AttributeName": "authorId", "KeyType": "HASH"},
                                {"AttributeName": "publishedAt", "KeyType": "RANGE"},
                            ],
                            "ProvisionedThroughput": {
                                "ReadCapacityUnits": 1,
                                "WriteCapacityUnits": 1,
                            },
                        }
                    ),
                    assertions.Match.object_like(
                        {
                            "IndexName": "byAuthorName",
                            "KeySchema": [
                                {"AttributeName": "authorName", "KeyType": "HASH"},
                                {"AttributeName": "publishedAt", "KeyType": "RANGE"},
                            ],
                            "ProvisionedThroughput": {
                                "ReadCapacityUnits": 1,
                                "WriteCapacityUnits": 1,
                            },
                        }
                    ),
                ]
            ),
        },
    )


def test_presales_table_and_by_book_index():
    template = _template()
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "Presales",
            "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
            "KeySchema": [
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "bookId", "KeyType": "RANGE"},
            ],
            "GlobalSecondaryIndexes": assertions.Match.array_with(
                [
                    assertions.Match.object_like(
                        {
                            "IndexName": "byBook",
                            "KeySchema": [{"AttributeName": "bookId", "KeyType": "HASH"}],
                            "ProvisionedThroughput": {
                                "ReadCapacityUnits": 1,
                                "WriteCapacityUnits": 1,
                            },
                        }
                    )
                ]
            ),
        },
    )


def test_one_lambda_behind_api_gateway():
    template = _template()
    template.resource_count_is("AWS::Lambda::Function", 1)
    template.resource_count_is("AWS::ApiGateway::RestApi", 1)
    template.resource_count_is("AWS::ApiGateway::Method", 2)
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "handler.handler",
            "Runtime": "python3.12",
            "Environment": {
                "Variables": assertions.Match.object_like(
                        {
                            "BOOKS_TABLE_NAME": assertions.Match.any_value(),
                            "PRESALES_TABLE_NAME": assertions.Match.any_value(),
                            "POWERTOOLS_SERVICE_NAME": "bookstore",
                        }
                )
            },
        },
    )
    template.has_resource_properties(
        "AWS::ApiGateway::Resource",
        {"PathPart": "{proxy+}"},
    )
    template.has_resource_properties(
        "AWS::ApiGateway::Method",
        {"HttpMethod": "ANY"},
    )

    template.resource_count_is("AWS::Lambda::LayerVersion", 1)
    template.has_resource_properties(
        "AWS::Lambda::LayerVersion",
        {
            "CompatibleRuntimes": ["python3.12"],
            "CompatibleArchitectures": ["x86_64"],
            "Description": "TableRepository and Powertools, mounted at /opt/python.",
        },
    )
    functions = [
        resource
        for resource in template.to_json()["Resources"].values()
        if resource["Type"] == "AWS::Lambda::Function"
    ]
    assert len(functions[0]["Properties"]["Layers"]) == 1
