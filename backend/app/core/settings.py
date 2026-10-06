from datetime import time

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Database ---
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "lifeops"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""

    # --- Working window ---
    WORK_START: time = time(8, 0)
    WORK_END: time = time(22, 0)

    # --- AI provider ---
    # Set AI_PROVIDER="watsonx" in production .env to enable real calls.
    # Default is "mock" so the app runs without credentials in development.
    AI_PROVIDER: str = "mock"

    # --- IBM watsonx credentials (never hardcoded — always from .env) ---
    WATSONX_API_KEY: str = ""
    WATSONX_PROJECT_ID: str = ""
    WATSONX_URL: str = "https://us-south.ml.cloud.ibm.com"
    # Model identifier is configurable so it can be changed without code changes.
    WATSONX_MODEL_ID: str = "granite-4-1-8b"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    model_config = {"env_file": ".env"}


settings = Settings()
