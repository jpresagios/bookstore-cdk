import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import jsii
from aws_cdk import BundlingOptions, DockerImage, Duration, ILocalBundling, RemovalPolicy, Stack
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as eventsources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_ses as ses
from constructs import Construct

# Free tier is 25 reads and 25 writes per second for the whole account in this
# region, shared by every provisioned table and index. One each stays inside it.
FREE_TIER_CAPACITY = 1
CRUD_DIR = Path(__file__).resolve().parent / "crud"
NOTIFY_DIR = Path(__file__).resolve().parent / "notify"
LAYER_DIR = Path(__file__).resolve().parent / "layer"
_layer_bundle: Path | None = None


@jsii.implements(ILocalBundling)
class _SharedLayerBundle:
    """Build the layer zip: python/table_repository.py plus Powertools."""

    def try_bundle(self, output_dir: str, *, image: DockerImage, **_kwargs: object) -> bool:
        shutil.copytree(_layer_output(), output_dir, dirs_exist_ok=True)
        return True


def _layer_output() -> Path:
    """Build the layer directory once per process.

    Lambda adds /opt/python to the import path, so the zip root must
    contain a python/ folder.
    """
    global _layer_bundle
    if _layer_bundle is not None:
        return _layer_bundle
    cache = Path(tempfile.mkdtemp(prefix="bookstore-layer-"))
    python_dir = cache / "python"
    python_dir.mkdir()
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--platform",
            "manylinux2014_x86_64",
            "--implementation",
            "cp",
            "--python-version",
            "3.12",
            "--only-binary=:all:",
            "-r",
            str(LAYER_DIR / "requirements.txt"),
            "-t",
            str(python_dir),
        ]
    )
    shutil.copy2(LAYER_DIR / "python" / "table_repository.py", python_dir / "table_repository.py")
    _layer_bundle = cache
    return cache


def _notify_functions(stack: Stack, bookstore, shared, identity, notify_email: str) -> None:
    """Attach the two stream Lambdas that send mail through SES."""
    environment = {
        "BOOKSTORE_TABLE_NAME": bookstore.table_name,
        "NOTIFY_FROM_EMAIL": notify_email,
        "POWERTOOLS_SERVICE_NAME": "bookstore",
    }
    favorite = lambda_.Function(
        stack,
        "FavoriteAuthorPresale",
        runtime=lambda_.Runtime.PYTHON_3_12,
        architecture=lambda_.Architecture.X86_64,
        handler="handler.on_favorite_presale",
        code=lambda_.Code.from_asset(str(NOTIFY_DIR)),
        layers=[shared],
        timeout=Duration.seconds(10),
        environment=environment,
        description="Emails users who favorited an author when that author publishes a presale.",
    )
    arrived = lambda_.Function(
        stack,
        "BookArrived",
        runtime=lambda_.Runtime.PYTHON_3_12,
        architecture=lambda_.Architecture.X86_64,
        handler="handler.on_book_arrived",
        code=lambda_.Code.from_asset(str(NOTIFY_DIR)),
        layers=[shared],
        timeout=Duration.seconds(10),
        environment=environment,
        description="Emails when a reserved book arrives in the store.",
    )
    for function in (favorite, arrived):
        bookstore.grant_read_data(function)
        identity.grant_send_email(function)
    favorite.add_event_source(
        eventsources.DynamoEventSource(
            bookstore,
            starting_position=lambda_.StartingPosition.LATEST,
            batch_size=1,
            filters=[
                lambda_.FilterCriteria.filter(
                    {
                        "eventName": lambda_.FilterRule.is_equal("INSERT"),
                        "dynamodb": {
                            "NewImage": {
                                "entity": {"S": lambda_.FilterRule.is_equal("BOOK")},
                                "status": {"S": lambda_.FilterRule.is_equal("PRESALE")},
                            }
                        },
                    }
                )
            ],
        )
    )
    arrived.add_event_source(
        eventsources.DynamoEventSource(
            bookstore,
            starting_position=lambda_.StartingPosition.LATEST,
            batch_size=1,
            filters=[
                lambda_.FilterCriteria.filter(
                    {
                        "eventName": lambda_.FilterRule.is_equal("MODIFY"),
                        "dynamodb": {
                            "OldImage": {
                                "status": {"S": lambda_.FilterRule.is_equal("PRESALE")},
                            },
                            "NewImage": {
                                "entity": {"S": lambda_.FilterRule.is_equal("BOOK")},
                                "status": {"S": lambda_.FilterRule.is_equal("IN_STORE")},
                            },
                        },
                    }
                )
            ],
        )
    )


class BookstoreCdkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        notify_email = self.node.try_get_context("notifyEmail")
        if not isinstance(notify_email, str) or "@" not in notify_email:
            raise ValueError(
                "Pass the verified sender: cdk deploy -c notifyEmail=you@example.com"
            )
        identity = ses.EmailIdentity(
            self,
            "NotifyIdentity",
            identity=ses.Identity.email(notify_email),
        )

        bookstore = dynamodb.Table(
            self,
            "Bookstore",
            table_name="Bookstore",
            partition_key=dynamodb.Attribute(
                name="pk",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="sk",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PROVISIONED,
            read_capacity=FREE_TIER_CAPACITY,
            write_capacity=FREE_TIER_CAPACITY,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            removal_policy=RemovalPolicy.DESTROY,
        )
        bookstore.add_global_secondary_index(
            index_name="byAuthor",
            partition_key=dynamodb.Attribute(
                name="gsi1pk",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="gsi1sk",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
            read_capacity=FREE_TIER_CAPACITY,
            write_capacity=FREE_TIER_CAPACITY,
        )
        bookstore.add_global_secondary_index(
            index_name="byAuthorName",
            partition_key=dynamodb.Attribute(
                name="gsi2pk",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="gsi2sk",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
            read_capacity=FREE_TIER_CAPACITY,
            write_capacity=FREE_TIER_CAPACITY,
        )

        shared = lambda_.LayerVersion(
            self,
            "Shared",
            code=lambda_.Code.from_asset(
                str(LAYER_DIR),
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output/python && cp python/table_repository.py /asset-output/python/",
                    ],
                    local=_SharedLayerBundle(),
                ),
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            compatible_architectures=[lambda_.Architecture.X86_64],
            description="TableRepository and Powertools, mounted at /opt/python.",
        )
        crud = lambda_.Function(
            self,
            "Crud",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.X86_64,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                str(CRUD_DIR),
                exclude=["**/__pycache__", "**/*.pyc", "migrate.py"],
            ),
            layers=[shared],
            timeout=Duration.seconds(10),
            environment={
                "BOOKSTORE_TABLE_NAME": bookstore.table_name,
                "POWERTOOLS_SERVICE_NAME": "bookstore",
            },
            description="Routes every bookstore request to the Bookstore table.",
        )
        bookstore.grant_read_write_data(crud)
        _notify_functions(self, bookstore, shared, identity, notify_email)

        access_logs = logs.LogGroup(
            self,
            "ApiAccessLogs",
            log_group_name="/aws/apigateway/bookstore",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        api = apigateway.RestApi(
            self,
            "BookstoreApi",
            rest_api_name="Bookstore",
            description="Forwards every request to the bookstore CRUD Lambda.",
            cloud_watch_role=True,
            cloud_watch_role_removal_policy=RemovalPolicy.DESTROY,
            deploy_options=apigateway.StageOptions(
                access_log_destination=apigateway.LogGroupLogDestination(access_logs),
                access_log_format=apigateway.AccessLogFormat.custom(
                    json.dumps(
                        {
                            "requestId": apigateway.AccessLogField.context_request_id(),
                            "ip": apigateway.AccessLogField.context_identity_source_ip(),
                            "method": apigateway.AccessLogField.context_http_method(),
                            "path": apigateway.AccessLogField.context_path(),
                            "status": apigateway.AccessLogField.context_status(),
                            "responseLength": apigateway.AccessLogField.context_response_length(),
                            "responseLatencyMs": apigateway.AccessLogField.context_response_latency(),
                            "integrationLatencyMs": apigateway.AccessLogField.context_integration_latency(),
                        }
                    )
                ),
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
            ),
        )
        integration = apigateway.LambdaIntegration(crud, proxy=True)
        api.root.add_method("ANY", integration)
        api.root.add_resource("{proxy+}").add_method("ANY", integration)
