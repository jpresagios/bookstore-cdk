import pytest
import aws_cdk as core
import aws_cdk.assertions as assertions

from bookstore_cdk.bookstore_cdk_stack import BookstoreCdkStack


def _template() -> assertions.Template:
    app = core.App(context={"notifyEmail": "reader@example.com"})
    stack = BookstoreCdkStack(app, "bookstore-cdk")
    return assertions.Template.from_stack(stack)


def test_bookstore_table_and_indexes():
    template = _template()
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "Bookstore",
            "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
            "KeySchema": [
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            "StreamSpecification": {"StreamViewType": "NEW_AND_OLD_IMAGES"},
            "GlobalSecondaryIndexes": assertions.Match.array_with(
                [
                    assertions.Match.object_like(
                        {
                            "IndexName": "byAuthor",
                            "KeySchema": [
                                {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                                {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
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
                                {"AttributeName": "gsi2pk", "KeyType": "HASH"},
                                {"AttributeName": "gsi2sk", "KeyType": "RANGE"},
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


def test_legacy_tables_are_gone():
    template = _template()
    template.resource_count_is("AWS::DynamoDB::Table", 1)
    names = [
        resource["Properties"].get("TableName")
        for resource in template.to_json()["Resources"].values()
        if resource["Type"] == "AWS::DynamoDB::Table"
    ]
    assert names == ["Bookstore"]


def test_notify_email_is_required():
    with pytest.raises(ValueError, match="notifyEmail"):
        BookstoreCdkStack(core.App(), "bookstore-cdk")


def test_one_lambda_behind_api_gateway():
    template = _template()
    template.resource_count_is("AWS::Lambda::Function", 3)
    template.resource_count_is("AWS::Lambda::EventSourceMapping", 2)
    template.resource_count_is("AWS::SES::EmailIdentity", 1)
    template.has_resource_properties(
        "AWS::SES::EmailIdentity",
        {"EmailIdentity": "reader@example.com"},
    )
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"Handler": "handler.on_favorite_presale"},
    )
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"Handler": "handler.on_book_arrived"},
    )
    template.has_resource_properties(
        "AWS::Lambda::EventSourceMapping",
        {"StartingPosition": "LATEST"},
    )
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
                                "BOOKSTORE_TABLE_NAME": assertions.Match.any_value(),
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
    template.resource_count_is("AWS::Logs::LogGroup", 1)
    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {"LogGroupName": "/aws/apigateway/bookstore"},
    )
    template.has_resource_properties(
        "AWS::ApiGateway::Stage",
        {
            "AccessLogSetting": assertions.Match.object_like(
                {"DestinationArn": assertions.Match.any_value()}
            ),
            "MethodSettings": assertions.Match.array_with(
                [
                    assertions.Match.object_like(
                        {
                            "LoggingLevel": "INFO",
                            "DataTraceEnabled": True,
                        }
                    )
                ]
            ),
        },
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
    assert all(len(function["Properties"]["Layers"]) == 1 for function in functions)
