"""Environment the Lambda reads at import time."""

import os


class Settings:
    """Table names injected by the CDK stack."""

    BOOKS_TABLE_NAME: str = os.environ["BOOKS_TABLE_NAME"]
    PRESALES_TABLE_NAME: str = os.environ["PRESALES_TABLE_NAME"]


settings = Settings()
