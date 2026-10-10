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
from constructs import Construct

# Free tier is 25 reads and 25 writes per second for the whole account in this
# region, shared by every provisioned table and index. One each stays inside it.
FREE_TIER_CAPACITY = 1
CRUD_DIR = Path(__file__).resolve().parent / "crud"
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


class BookstoreCdkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        books = dynamodb.Table(
            self,
            "Books",
            table_name="Books",
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PROVISIONED,
            read_capacity=FREE_TIER_CAPACITY,
            write_capacity=FREE_TIER_CAPACITY,
            removal_policy=RemovalPolicy.DESTROY,
        )
        books.add_global_secondary_index(
            index_name="byAuthor",
            partition_key=dynamodb.Attribute(
                name="authorId",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="publishedAt",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
            read_capacity=FREE_TIER_CAPACITY,
            write_capacity=FREE_TIER_CAPACITY,
        )
        books.add_global_secondary_index(
            index_name="byAuthorName",
            partition_key=dynamodb.Attribute(
                name="authorName",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="publishedAt",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
            read_capacity=FREE_TIER_CAPACITY,
            write_capacity=FREE_TIER_CAPACITY,
        )

        presales = dynamodb.Table(
            self,
            "Presales",
            table_name="Presales",
            partition_key=dynamodb.Attribute(
                name="userId",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="bookId",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PROVISIONED,
            read_capacity=FREE_TIER_CAPACITY,
            write_capacity=FREE_TIER_CAPACITY,
            removal_policy=RemovalPolicy.DESTROY,
        )
        presales.add_global_secondary_index(
            index_name="byBook",
            partition_key=dynamodb.Attribute(
                name="bookId",
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
                exclude=["**/__pycache__", "**/*.pyc"],
            ),
            layers=[shared],
            timeout=Duration.seconds(10),
            environment={
                "BOOKS_TABLE_NAME": books.table_name,
                "PRESALES_TABLE_NAME": presales.table_name,
                "POWERTOOLS_SERVICE_NAME": "bookstore",
            },
            description="Routes every bookstore request to the Books and Presales tables.",
        )
        books.grant_read_write_data(crud)
        presales.grant_read_write_data(crud)

        api = apigateway.RestApi(
            self,
            "BookstoreApi",
            rest_api_name="Bookstore",
            description="Forwards every request to the bookstore CRUD Lambda.",
        )
        integration = apigateway.LambdaIntegration(crud, proxy=True)
        api.root.add_method("ANY", integration)
        api.root.add_resource("{proxy+}").add_method("ANY", integration)
