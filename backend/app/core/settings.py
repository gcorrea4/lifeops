from datetime import time

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "lifeops"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    WORK_START: time = time(8, 0)
    WORK_END: time = time(22, 0)

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    model_config = {"env_file": ".env"}


settings = Settings()
