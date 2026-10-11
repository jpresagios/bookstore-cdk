"""Environment the Lambda reads at import time."""

import os


class Settings:
    """Table name injected by the CDK stack."""

    BOOKSTORE_TABLE_NAME: str = os.environ["BOOKSTORE_TABLE_NAME"]


settings = Settings()
