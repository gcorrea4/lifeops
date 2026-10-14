from datetime import time

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Database ---
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "lifeops"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    # Optional path to a CA certificate. Managed MySQL services (Azure, Aiven, ...) require TLS;
    # when set, the connection is encrypted and the server is verified against this CA.
    # Empty keeps the plain local connection used with Docker Compose.
    DB_SSL_CA: str = ""

    # --- Public demo protection (all off by default, so local development is unchanged) ---
    # Refuse requests that carry no X-Session-Id header instead of sharing the default user.
    REQUIRE_SESSION: bool = False
    # Max real AI calls per 24 hours across all visitors; beyond it the deterministic fallback is
    # used without calling the model. 0 = no cap.
    AI_DAILY_CAP: int = 0
    # Max tasks and commitments per visitor (the default user is exempt). 0 = unlimited.
    MAX_TASKS_PER_VISITOR: int = 0
    MAX_BLOCKS_PER_VISITOR: int = 0

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
